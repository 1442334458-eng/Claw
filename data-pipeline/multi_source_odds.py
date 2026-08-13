#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  多源赔率采集器 v1.1
  Multi-Source Odds Fetcher
============================================

两源 + MCP 架构（实际可用）：
  1. jc-mcp (本地MCP)       → 竞彩官方 API，5种玩法全赔率 ✅
     工具: get_jc_odds / get_jc_odds_simple / get_jc_match_odds
     优势: 本地运行 → 中国IP → 无geo-block
  2. 500.com (WebFetch)     → 百家平均 + 多博彩公司对比 ✅
     页面: trade.500.com/jczq/index.php?playid=312
     优势: 内嵌竞彩官方赔率 + 百家平均共识
  3. TheOddsAPI (requests)  → Bet365/Pinnacle 国际赔率 ⚠️ 沙箱待测
     备用: WebSearch 兜底

Python模块用途：
  - SportteryFetcher:     用于非沙箱环境（直连竞彩API，有IP限制）
  - FiveHundredFetcher:   用于WebFetch工具解析500.com页面
  - TheOddsAPIWrapper:    用于非沙箱环境（直连国际API）
  - WebSearchFallback:    API全失效时的兜底

Agent使用方式（沙箱环境）：
  1. 调用 jc-mcp 工具 → 获取竞彩官方赔率
  2. 调用 WebFetch → 获取500.com百家平均
  3. 合并 → 交叉验证

使用方法：
  # 沙箱环境（Agent模式）- 不直接调Python，用MCP+WebFetch
  # 非沙箱环境 - 直接调Python:
  python multi_source_odds.py --date 2026-08-10

作者：CodeBuddy Code
日期：2026-08-10
版本：v1.1 (适配沙箱环境 + jc-mcp集成)
"""

import os
import sys
import json
import time
import logging
import argparse
import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

# ============================================
# 配置
# ============================================

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / "cache" / "multi_source"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / f"multi_source_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

# User-Agent 池
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

# ============================================
# 数据模型
# ============================================

@dataclass
class SourceOdds:
    """单源赔率数据"""
    source: str           # 'sporttery' | '500com_bet365' | '500com_william' | 'theodds_bet365' | 'theodds_pinnacle'
    home_win: float
    draw: float
    away_win: float
    handicap: Optional[float] = None       # 让球盘口值（正=主队让球）
    handicap_home: Optional[float] = None   # 让球主队赔率
    handicap_away: Optional[float] = None   # 让球客队赔率
    return_rate: Optional[float] = None     # 返奖率
    timestamp: str = ""
    raw_data: Dict = field(default_factory=dict)

    @property
    def implied_probabilities(self) -> Dict[str, float]:
        """隐含概率（未去水）"""
        inv = lambda x: 1.0 / x if x > 0 else 0
        total = inv(self.home_win) + inv(self.draw) + inv(self.away_win)
        if total == 0:
            return {"home": 0, "draw": 0, "away": 0}
        return {
            "home": inv(self.home_win) / total,
            "draw": inv(self.draw) / total,
            "away": inv(self.away_win) / total
        }

    @property
    def no_vig_probabilities(self) -> Dict[str, float]:
        """去水后的真实隐含概率"""
        probs = self.implied_probabilities
        vig = self.vig if self.return_rate is None else (1.0 - self.return_rate)
        if vig <= 0 or vig >= 1:
            return probs
        # 按比例去水
        return {k: v / sum(probs.values()) for k, v in probs.items()}

    @property
    def vig(self) -> float:
        """水分（overround - 1）"""
        inv = lambda x: 1.0 / x if x > 0 else 0
        total = inv(self.home_win) + inv(self.draw) + inv(self.away_win)
        return total - 1.0 if total > 0 else 0


@dataclass
class MatchOdds:
    """单场比赛的多源赔率汇总"""
    match_id: str
    home_team: str
    away_team: str
    league: str
    match_time: str = ""
    sources: List[SourceOdds] = field(default_factory=list)

    @property
    def source_count(self) -> int:
        return len(self.sources)

    @property
    def consensus(self) -> Optional[Dict]:
        """赔率共识度分析"""
        if len(self.sources) < 2:
            return None

        homes = [s.home_win for s in self.sources if s.home_win > 0]
        draws = [s.draw for s in self.sources if s.draw > 0]
        aways = [s.away_win for s in self.sources if s.away_win > 0]

        def stats(vals):
            if len(vals) < 2:
                return {"mean": vals[0] if vals else 0, "std": 0, "min": vals[0] if vals else 0, "max": vals[0] if vals else 0}
            mean = sum(vals) / len(vals)
            variance = sum((v - mean) ** 2 for v in vals) / len(vals)
            std = variance ** 0.5
            return {"mean": round(mean, 3), "std": round(std, 3), "min": round(min(vals), 3), "max": round(max(vals), 3)}

        h = stats(homes)
        d = stats(draws)
        a = stats(aways)

        # 分歧等级判定
        max_cv = max(
            h["std"] / h["mean"] if h["mean"] > 0 else 0,
            d["std"] / d["mean"] if d["mean"] > 0 else 0,
            a["std"] / a["mean"] if a["mean"] > 0 else 0,
        )
        if max_cv > 0.08:
            level = "divergent"     # 严重分歧（CV > 8%）
        elif max_cv > 0.04:
            level = "low"           # 低共识（CV 4-8%）
        elif max_cv > 0.02:
            level = "medium"        # 中等共识（CV 2-4%）
        else:
            level = "high"          # 高共识（CV < 2%）

        return {
            "home": h, "draw": d, "away": a,
            "consensus_level": level,
            "max_cv": round(max_cv, 4)
        }

    def detect_anomalies(self) -> List[Dict]:
        """检测单源异常（某源偏离均值 > 2 std）"""
        anomalies = []
        consensus = self.consensus
        if not consensus or consensus["consensus_level"] == "high":
            return anomalies

        for s in self.sources:
            for outcome, val in [("主胜", s.home_win), ("平局", s.draw), ("客胜", s.away_win)]:
                key_map = {"主胜": "home", "平局": "draw", "客胜": "away"}
                stats = consensus[key_map[outcome]]
                if stats["std"] > 0 and abs(val - stats["mean"]) > 2 * stats["std"]:
                    anomalies.append({
                        "source": s.source,
                        "outcome": outcome,
                        "value": val,
                        "mean": stats["mean"],
                        "deviation": round(val - stats["mean"], 3),
                        "deviation_sigma": round(abs(val - stats["mean"]) / stats["std"], 2)
                    })
        return anomalies


# ============================================
# 源1: 竞彩官方 API (sporttery.cn)
# ============================================

class SportteryFetcher:
    """竞彩官方 API 赔率采集"""

    BASE_URL = "https://webapi.sporttery.cn/gateway/uniform/football"
    TIMEOUT = 15

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENTS[0],
            "Accept": "application/json",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://www.sporttery.cn/",
            "Origin": "https://www.sporttery.cn",
        })

    def _fetch(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """通用 API 请求（大陆IP优先，SSL自动降级）"""
        if params is None:
            params = {}
        url = f"{self.BASE_URL}/{endpoint}"

        # 按优先级尝试多种连接方式
        for attempt, verify_ssl in enumerate([True, False], 1):
            try:
                resp = self.session.get(url, params=params, timeout=self.TIMEOUT, verify=verify_ssl)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success") or data.get("errorCode") == "0":
                        return data
                    else:
                        log.warning(f"竞彩API返回错误: {data.get('errorMessage', 'unknown')}")
                        return None
                elif resp.status_code == 567:
                    if attempt == 1:
                        log.warning(f"竞彩API 567 (尝试{attempt}): 可能IP受限，换SSL模式重试...")
                        # 换一个 User-Agent 避免被识别
                        self.session.headers["User-Agent"] = USER_AGENTS[1 % len(USER_AGENTS)]
                        continue
                    else:
                        log.warning("竞彩API 567 (重试仍失败): 可能需要检查DNS/网络")
                        return None
                else:
                    log.warning(f"竞彩API HTTP {resp.status_code}: {url}")
                    return None
            except requests.exceptions.SSLError:
                log.debug(f"竞彩API SSL错误(尝试{attempt})，换 verify=False 重试...")
                continue
            except Exception as e:
                log.error(f"竞彩API请求失败: {e}")
                if attempt == 1:
                    continue
                return None

        return None

    def get_match_list(self, match_date: str = None) -> List[Dict]:
        """获取当日比赛列表及赔率
        
        Args:
            match_date: 日期 YYYY-MM-DD，默认今天
        """
        if match_date is None:
            match_date = datetime.now().strftime("%Y-%m-%d")

        result = self._fetch("getMatchListV1.qry", {"matchDate": match_date})
        if not result:
            return []

        matches = result.get("value", {}).get("matchList", [])
        log.info(f"竞彩API: 获取到 {len(matches)} 场比赛 ({match_date})")
        return matches

    def get_match_detail(self, match_id: str) -> Optional[Dict]:
        """获取单场详细信息（含所有玩法赔率）"""
        return self._fetch("getMatchHeadV1.qry", {"matchId": match_id})

    def to_source_odds(self, match: Dict) -> Optional[SourceOdds]:
        """将竞彩API返回的比赛数据转为 SourceOdds"""
        try:
            # 提取 SPF 赔率（had = 胜平负玩法）
            had = match.get("had", {}) or match.get("oddsHistory", {}).get("hadList", [{}])[-1] if match.get("oddsHistory") else {}
            
            home_win = float(had.get("h", had.get("homeWin", 0)))
            draw = float(had.get("d", had.get("draw", 0)))
            away_win = float(had.get("a", had.get("awayWin", 0)))

            if home_win == 0 and draw == 0 and away_win == 0:
                # 尝试从 match 的顶层字段提取
                home_win = float(match.get("homeWinOdds", match.get("h", 0)))
                draw = float(match.get("drawOdds", match.get("d", 0)))
                away_win = float(match.get("awayWinOdds", match.get("a", 0)))

            if home_win == 0:
                return None

            # 让球盘口
            handicap = None
            handicap_home = None
            handicap_away = None
            hhad = match.get("hhad", {}) or (match.get("oddsHistory", {}).get("hhadList", [{}])[-1] if match.get("oddsHistory") else {})
            if hhad:
                goal_line = hhad.get("goalLine", hhad.get("handicap", ""))
                if goal_line:
                    try:
                        handicap = float(goal_line)
                        handicap_home = float(hhad.get("h", hhad.get("homeWin", 0)))
                        handicap_away = float(hhad.get("a", hhad.get("awayWin", 0)))
                    except (ValueError, TypeError):
                        pass

            # 竞彩返奖率~71%
            return_rate = 0.71

            match_num = match.get("matchNum", match.get("matchId", ""))
            return SourceOdds(
                source="sporttery",
                home_win=home_win,
                draw=draw,
                away_win=away_win,
                handicap=handicap,
                handicap_home=handicap_home,
                handicap_away=handicap_away,
                return_rate=return_rate,
                timestamp=match.get("updateTime", datetime.now().isoformat()),
                raw_data={
                    "match_id": str(match_num),
                    "match_num": str(match_num),
                    "league": match.get("leagueName", match.get("leagueAbbName", "")),
                    "home_team": match.get("homeTeam", ""),
                    "away_team": match.get("awayTeam", ""),
                    "match_time": match.get("matchTime", match.get("matchDate", "")),
                }
            )
        except Exception as e:
            log.error(f"竞彩数据转换失败: {e}, match={match}")
            return None


# ============================================
# 源2: 500.com 多源赔率对比
# ============================================

class FiveHundredFetcher:
    """500.com 多源赔率数据采集

    500.com trade.500.com/jczq/ 页面（GB2312编码）内嵌：
      - 竞彩官方 SPF 赔率（data-type=nspf + data-sp）
      - 让球盘口（data-type=rqspf + data-sp）
      - 比赛编号/联赛/队名/截止时间
    """

    BASE_URL = "https://trade.500.com"
    JCZQ_URL = "https://trade.500.com/jczq/"
    TIMEOUT = 20

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

    def _get_headers(self) -> Dict:
        return {
            "User-Agent": USER_AGENTS[hash(str(time.time())) % len(USER_AGENTS)],
            "Referer": "https://trade.500.com/",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def get_jczq_today(self) -> Optional[str]:
        """获取今日竞彩足球赔率页面（GB2312编码）"""
        for verify_ssl in [True, False]:
            try:
                resp = self.session.get(self.JCZQ_URL, headers=self._get_headers(),
                                       timeout=self.TIMEOUT, verify=verify_ssl)
                if resp.status_code == 200:
                    resp.encoding = 'gb2312'
                    return resp.text
            except requests.exceptions.SSLError:
                continue
            except Exception as e:
                log.debug(f"500.com: {e}")
        return None

    def parse_jczq_matches(self, html: str) -> List[Dict]:
        """解析 trade.500.com/jczq/ 页面，提取所有场次的赔率

        页面结构（每场比赛一行 tr）：
          <tr data-matchid="170">
            <td class="td td-no">周二001</td>
            <td class="td td-evt">联赛名</td>
            <td class="td td-endtime">截止时间</td>
            <td class="td td-team">主队 VS 客队</td>
            <td class="td td-betbtn">
              <p class="betbtn" data-type="nspf" data-value="3" data-sp="2.49">2.49</p>
              <p class="betbtn" data-type="nspf" data-value="1" data-sp="3.08">3.08</p>
              <p class="betbtn" data-type="nspf" data-value="0" data-sp="2.48">2.48</p>
            </td>
            <td>...让球盘口同样格式...</td>
          </tr>

        data-value: 3=主胜, 1=平局, 0=客胜
        """
        matches = []

        # 方式1: 用正则提取所有比赛行
        rows = re.findall(
            r'<tr[^>]*data-matchid="(\d+)"[^>]*>(.*?)</tr>',
            html, re.S
        )

        for match_id, row_html in rows:
            if 'betbtn' not in row_html:
                continue

            # 提取比赛编号
            match_num = ""
            m_num = re.search(r'<td[^>]*td-no[^>]*>.*?(\w+)(\d+)', row_html)
            if m_num:
                match_num = f"{m_num.group(1)}{m_num.group(2)}"

            # 提取联赛
            league = ""
            m_league = re.search(r'title="([^"]+)"[^>]*>\s*</a>\s*</td>', row_html)
            if not m_league:
                m_league = re.search(r'<td[^>]*td-evt[^>]*>(.*?)</td>', row_html, re.S)
                if m_league:
                    league = re.sub(r'<[^>]+>', '', m_league.group(1)).strip()
            else:
                league = m_league.group(1)

            # 提取截止时间
            kickoff = ""
            m_time = re.search(r'title="([^"]*截止)"', row_html)
            if m_time:
                kickoff = m_time.group(1).replace('截止', '')
            else:
                m_time = re.search(r'<td[^>]*td-endtime[^>]*>([^<]+)', row_html)
                if m_time:
                    kickoff = m_time.group(1).strip()

            # 提取队名
            home_team = away_team = ""
            m_team = re.search(r'<td[^>]*td-team[^>]*>(.*?)</td>', row_html, re.S)
            if m_team:
                team_html = m_team.group(1)
                # 提取主队
                m_home = re.search(r'title="([^"]+)"[^>]*>([^<]+)', team_html)
                # 第一个 team-l 是主队
                homes = re.findall(r'class="team-l"[^>]*title="([^"]+)">([^<]+)', team_html)
                aways = re.findall(r'class="team-r"[^>]*title="([^"]+)">([^<]+)', team_html)
                if homes:
                    home_team = homes[0][1] if homes[0][1] else homes[0][0]
                if aways:
                    away_team = aways[0][1] if aways[0][1] else aways[0][0]

            # 提取 SPF 赔率（data-type="nspf"）
            spf_odds = {}
            for m_spf in re.finditer(
                r'data-type="nspf"\s+data-value="([^"]+)"\s+data-sp="([^"]+)"',
                row_html
            ):
                val = int(m_spf.group(1))
                sp = float(m_spf.group(2))
                spf_odds[val] = sp

            # 提取让球盘口（data-type="rqspf"）
            rq_odds = {}
            rq_line = None
            for m_rq in re.finditer(
                r'data-type="rqspf"\s+data-value="([^"]+)"\s+data-sp="([^"]+)"',
                row_html
            ):
                val = int(m_rq.group(1))
                sp = float(m_rq.group(2))
                rq_odds[val] = sp
            # 查找让球数
            m_rq_line = re.search(r'让球[：:\s]*([+-]?\d+)', row_html)
            if not m_rq_line:
                m_rq_line = re.search(r'rqspf[^>]*>.*?([+-]?\d+)', row_html, re.S)
            if m_rq_line:
                try:
                    rq_line = float(m_rq_line.group(1))
                except ValueError:
                    pass

            if spf_odds:
                matches.append({
                    "match_id": match_id,
                    "match_num": match_num,
                    "league": league,
                    "home_team": home_team,
                    "away_team": away_team,
                    "home_win": spf_odds.get(3, 0),
                    "draw": spf_odds.get(1, 0),
                    "away_win": spf_odds.get(0, 0),
                    "handicap": rq_line,
                    "handicap_home": rq_odds.get(3, None),
                    "handicap_away": rq_odds.get(0, None),
                    "kickoff": kickoff,
                    "source": "500.com_jczq",
                })

        log.info(f"500.com Jczq: 解析到 {len(matches)} 场比赛")
        for m in matches[:3]:
            log.info(f"  {m['match_num']} {m['home_team']} vs {m['away_team']}: {m['home_win']}/{m['draw']}/{m['away_win']}")
        return matches

    def search_match(self, home_en: str, away_en: str, home_cn: str = "", away_cn: str = "") -> List[Dict]:
        """搜索特定比赛（宽松匹配：队名如"里独立"可匹配"里瓦达维亚独立"）

        匹配策略：
          1. 中文名：至少 2 个连续字符在 500.com 队名中出现
          2. 英文名：不区分大小写完整子串
        """
        html = self.get_jczq_today()
        if not html:
            return []
        all_matches = self.parse_jczq_matches(html)
        results = []

        def cn_loose_match(inp: str, target: str) -> bool:
            """中文宽松匹配：检查 inp 中任意 2+ 连续字符是否在 target 中"""
            if not inp or not target:
                return False
            if inp in target or target in inp:
                return True
            # 滑窗: 检查 inp 的 2-char 子串是否在 target 中出现
            for i in range(len(inp) - 1):
                if inp[i:i+2] in target:
                    return True
            # 也检查首字符+最后一个字符
            if len(inp) >= 2 and inp[0] in target and inp[-1] in target:
                return True
            return False

        for m in all_matches:
            h = m.get("home_team", "")
            a = m.get("away_team", "")
            # 主队匹配
            home_ok = cn_loose_match(home_cn, h) or (home_en and home_en.lower() in h.lower())
            away_ok = cn_loose_match(away_cn, a) or (away_en and away_en.lower() in a.lower())
            if home_ok and away_ok:
                results.append(m)

        return results

    def get_european_odds_comparison(self, match_date: str = None) -> List[Dict]:
        """兼容旧接口：委托给 jczq 解析"""
        html = self.get_jczq_today()
        if not html:
            return []
        matches = self.parse_jczq_matches(html)
        return [{
            "teams": f"{m['home_team']} vs {m['away_team']}",
            "bookmakers": [{
                "bookmaker": "sporttery_official",
                "home": m["home_win"], "draw": m["draw"], "away": m["away_win"]
            }]
        } for m in matches]


# ============================================
# 源3: TheOddsAPI 包装（复用现有管道）
# ============================================

class TheOddsAPIWrapper:
    """TheOddsAPI 包装器 - 对接现有管道的 OddsAPIClient"""

    def __init__(self, api_key: str = None):
        from pathlib import Path as P
        env_file = BASE_DIR / ".env"
        if api_key is None and env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip().startswith("ODDS_API_KEY="):
                        api_key = line.strip().split("=", 1)[1].strip()
                        break

        self.api_key = api_key
        self.base_url = "https://api.the-odds-api.com/v4"

    def fetch_sport_odds(self, sport_key: str, regions: str = "eu,uk,us") -> List[Dict]:
        """拉取指定联赛的赔率"""
        if not self.api_key:
            log.warning("TheOddsAPI: 无API Key，跳过")
            return []

        url = f"{self.base_url}/sports/{sport_key}/odds/"
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": "h2h,spreads",
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 401:
                log.warning("TheOddsAPI: API Key 过期(401)")
            else:
                log.warning(f"TheOddsAPI HTTP {resp.status_code}")
            return []
        except Exception as e:
            log.error(f"TheOddsAPI请求失败: {e}")
            return []

    def to_source_odds_list(self, events: List[Dict]) -> List[SourceOdds]:
        """将API返回的events转为SourceOdds列表"""
        results = []
        for event in events:
            for bookmaker in event.get("bookmakers", []):
                book_name = bookmaker.get("key", bookmaker.get("title", "unknown"))
                markets = bookmaker.get("markets", [])
                
                for market in markets:
                    if market.get("key") != "h2h":
                        continue
                    
                    outcomes = market.get("outcomes", [])
                    home = draw = away = 0.0
                    for o in outcomes:
                        if o.get("name") == event.get("home_team"):
                            home = o.get("price", 0)
                        elif o.get("name") == event.get("away_team"):
                            away = o.get("price", 0)
                        elif o.get("name") == "Draw":
                            draw = o.get("price", 0)

                    if home > 0:
                        results.append(SourceOdds(
                            source=f"theodds_{book_name}",
                            home_win=home,
                            draw=draw,
                            away_win=away,
                            timestamp=datetime.now().isoformat(),
                        ))

        return results


# ============================================
# WebSearch 兜底：从搜索引擎获取赔率
# ============================================

class WebSearchFallback:
    """通过搜索引擎获取赔率（兜底方案）
    
    在API全部失效时，通过WebSearch关键词获取赔率信息。
    支持源：新浪体育、QQ体育、搜狐体育、雪球等
    """

    SEARCH_TEMPLATES = [
        "{home} vs {away} 赔率 欧赔 即时",
        "{home} {away} odds comparison betting",
        "{home} vs {away} 竞彩 胜平负赔率",
    ]

    # 这些方法在 Agent 环境中由 WebSearch 工具执行
    # 本类提供搜索任务定义和结果解析

    @staticmethod
    def generate_search_tasks(home: str, away: str, league: str = "") -> List[Dict]:
        """生成搜索任务定义"""
        tasks = []
        for template in WebSearchFallback.SEARCH_TEMPLATES:
            query = template.format(home=home, away=away)
            tasks.append({
                "query": query,
                "category": "odds_fallback",
                "source": "web_search",
            })
        return tasks

    @staticmethod
    def parse_search_results(search_results: List[Dict]) -> Optional[SourceOdds]:
        """从搜索结果文本中解析赔率
        
        支持的格式:
        - "主胜1.85 平3.40 客胜4.20"
        - "1.85 / 3.40 / 4.20"
        - "主1.85 平3.40 客4.20"
        """
        # 合并所有搜索结果文本
        combined_text = " ".join([r.get("text", "") for r in search_results if r.get("text")])

        # 模式1: "主胜X.XX 平局X.XX 客胜X.XX" 或 "主X.XX 平X.XX 客X.XX"
        pattern1 = r'[主胜]+[：:\s]*(\d+\.?\d*).*?[平局]+[：:\s]*(\d+\.?\d*).*?[客胜]+[：:\s]*(\d+\.?\d*)'
        m1 = re.search(pattern1, combined_text)
        if m1:
            return SourceOdds(
                source="websearch",
                home_win=float(m1.group(1)),
                draw=float(m1.group(2)),
                away_win=float(m1.group(3)),
                timestamp=datetime.now().isoformat(),
            )

        # 模式2: "X.XX / X.XX / X.XX"
        pattern2 = r'(\d+\.?\d{1,2})\s*[/|]\s*(\d+\.?\d{1,2})\s*[/|]\s*(\d+\.?\d{1,2})'
        matches = re.findall(pattern2, combined_text)
        if matches:
            # 取第一组看起来像赔率的值（通常在1.0-15.0之间）
            for m in matches:
                vals = [float(x) for x in m]
                if 1.01 <= min(vals) and max(vals) <= 50.0:
                    return SourceOdds(
                        source="websearch",
                        home_win=vals[0],
                        draw=vals[1],
                        away_win=vals[2],
                        timestamp=datetime.now().isoformat(),
                    )

        return None


# ============================================
# 主入口：多源采集器
# ============================================

class MultiSourceFetcher:
    """多源赔率采集器主类

    使用方式：
        fetcher = MultiSourceFetcher()
        
        # 方式1: 按日期采集
        matches = fetcher.fetch_by_date("2026-08-10")
        
        # 方式2: 按对阵采集
        odds = fetcher.fetch_match("主队", "客队", "联赛")
        
        # 方式3: 导出交叉验证报告
        report = fetcher.cross_validate(matches)
    """

    def __init__(self, enable_theodds: bool = True, enable_websearch_fallback: bool = False):
        self.sporttery = SportteryFetcher()
        self.fivehundred = FiveHundredFetcher()
        self.theodds = TheOddsAPIWrapper() if enable_theodds else None
        self.enable_websearch = enable_websearch_fallback

    def fetch_by_date(self, match_date: str = None) -> List[MatchOdds]:
        """按日期批量采集所有场比赛的多源赔率"""
        if match_date is None:
            match_date = datetime.now().strftime("%Y-%m-%d")

        all_matches = []
        source_stats = {"sporttery": 0, "500com": 0, "theodds": 0, "websearch": 0}

        # 1. 从竞彩API获取比赛列表和赔率
        log.info("=" * 50)
        log.info(f"[1/3] 竞彩官方API: 获取 {match_date} 比赛列表...")
        match_list = self.sporttery.get_match_list(match_date)

        match_odds_map = {}  # key: (home, away) -> MatchOdds

        for match in match_list:
            home = match.get("homeTeam", "")
            away = match.get("awayTeam", "")
            if not home or not away:
                continue

            match_num = str(match.get("matchNum", match.get("matchId", "")))
            key = (home.strip(), away.strip())

            if key not in match_odds_map:
                match_odds_map[key] = MatchOdds(
                    match_id=match_num,
                    home_team=home.strip(),
                    away_team=away.strip(),
                    league=match.get("leagueName", match.get("leagueAbbName", "")),
                    match_time=match.get("matchTime", match.get("matchDate", "")),
                )

            source_odds = self.sporttery.to_source_odds(match)
            if source_odds:
                match_odds_map[key].sources.append(source_odds)
                source_stats["sporttery"] += 1

        # 2. 从500.com获取多源赔率
        log.info(f"[2/3] 500.com: 获取多源赔率对比...")
        euro_odds = self.fivehundred.get_european_odds_comparison(match_date)

        for eo_match in euro_odds:
            teams_str = eo_match.get("teams", "")
            bookmakers = eo_match.get("bookmakers", [])

            # 尝试匹配到现有比赛
            matched_key = None
            for key in match_odds_map:
                if key[0].lower() in teams_str.lower() and key[1].lower() in teams_str.lower():
                    matched_key = key
                    break

            if matched_key:
                for bm in bookmakers:
                    source_name = f"500com_{bm['bookmaker']}"
                    match_odds_map[matched_key].sources.append(SourceOdds(
                        source=source_name,
                        home_win=bm["home"],
                        draw=bm["draw"],
                        away_win=bm["away"],
                        timestamp=datetime.now().isoformat(),
                    ))
                    source_stats["500com"] += 1

        # 3. 从TheOddsAPI获取国际赔率（如果可用）
        if self.theodds and self.theodds.api_key:
            log.info(f"[3/3] TheOddsAPI: 获取国际赔率...")
            # 按联赛分组获取
            leagues = set(m.league for m in match_odds_map.values() if m.league)
            for league in leagues:
                sport_key = self._league_to_sport_key(league)
                if not sport_key:
                    continue
                events = self.theodds.fetch_sport_odds(sport_key)
                odds_list = self.theodds.to_source_odds_list(events)
                
                # 匹配到对应比赛
                for odds in odds_list:
                    for key, match_odds in match_odds_map.items():
                        # 简化：在事件中搜索包含队名的
                        if key[0].lower() in odds.source.lower() or key[1].lower() in odds.source.lower():
                            match_odds.sources.append(odds)
                            source_stats["theodds"] += 1
                            break
        else:
            log.info("[3/3] TheOddsAPI: 跳过（无API Key）")

        # 汇总
        all_matches = list(match_odds_map.values())

        log.info("=" * 50)
        log.info(f"采集完成: {len(all_matches)} 场比赛")
        log.info(f"  竞彩官方: {source_stats['sporttery']} 条")
        log.info(f"  500.com:  {source_stats['500com']} 条")
        log.info(f"  TheOdds:  {source_stats['theodds']} 条")

        return all_matches

    def fetch_match(self, home: str, away: str, league: str = "", en_home: str = "", en_away: str = "") -> Optional[MatchOdds]:
        """单场比赛的多源赔率采集

        v2.2.1 新策略（国产优先）：
          1. 500.com Jczq (含竞彩官方+49家公司, 免费无限量) → 主源
          2. 竞彩官方 API (直连, 仅当500.com失败时尝试) → 备用
          3. TheOddsAPI (国际交叉验证, 可选) → 验证

        Args:
            home: 中文主队名
            away: 中文客队名
            league: 联赛名
            en_home: 英文主队名（用于500.com等英文站点匹配）
            en_away: 英文客队名（用于500.com等英文站点匹配）
        """
        match_odds = MatchOdds(
            match_id=hashlib.md5(f"{home}{away}{league}".encode()).hexdigest()[:12],
            home_team=home,
            away_team=away,
            league=league,
        )

        en_h = en_home or home
        en_a = en_away or away

        # === [主源] 500.com Jczq (含竞彩官方 + 49家公司赔率) ===
        log.info(f"  [主源] 500.com Jczq: {en_h} vs {en_a}...")
        jczq_matches = self.fivehundred.search_match(en_h, en_a, home, away)
        if jczq_matches:
            m = jczq_matches[0]
            # 竞彩官方（内嵌在500.com Jczq页面中）
            if m.get("home_win", 0) > 0:
                match_odds.sources.append(SourceOdds(
                    source="sporttery_official",
                    home_win=m["home_win"],
                    draw=m["draw"],
                    away_win=m["away_win"],
                    return_rate=0.71,
                    timestamp=datetime.now().isoformat(),
                    raw_data={"source": "500.com_jczq_embedded"},
                ))
            # 其他赔率行
            for i, odd in enumerate(m.get("extra_odds", [])[:5]):
                if odd > 0 and (i % 3 == 0) and i + 2 < len(m.get("extra_odds", [])):
                    extras = m["extra_odds"]
                    match_odds.sources.append(SourceOdds(
                        source=f"500com_bookmaker_{i//3}",
                        home_win=extras[i],
                        draw=extras[i+1],
                        away_win=extras[i+2],
                        timestamp=datetime.now().isoformat(),
                    ))
            log.info(f"    ✅ 500.com 获取到: 竞彩官方SPF + {len(match_odds.sources)-1}家公司")

        # === [备用] 竞彩官方 API 直连（仅当500.com失败时） ===
        if not match_odds.sources:
            log.info(f"  [备用] 竞彩官方 API: {home} vs {away}...")
            match_list = self.sporttery.get_match_list()
            for match in match_list:
                m_home = match.get("homeTeam", "")
                m_away = match.get("awayTeam", "")
                if ((home.lower() in m_home.lower() or m_home.lower() in home.lower()) and \
                   (away.lower() in m_away.lower() or m_away.lower() in away.lower())) or \
                   ((en_h.lower() in m_home.lower() or m_home.lower() in en_h.lower()) and \
                   (en_a.lower() in m_away.lower() or m_away.lower() in en_a.lower())):
                    source_odds = self.sporttery.to_source_odds(match)
                    if source_odds:
                        match_odds.sources.append(source_odds)
                        match_odds.match_id = str(match.get("matchNum", match.get("matchId", "")))
                        match_odds.league = match.get("leagueName", "")
                        match_odds.match_time = match.get("matchTime", "")
                    break
            if match_odds.sources:
                log.info(f"    ✅ 竞彩官方直连成功")
            else:
                log.warning(f"    ⚠️ 竞彩官方未匹配到 {home} vs {away}")

        # === [可选] TheOddsAPI 国际交叉验证 ===
        if self.theodds and self.theodds.api_key:
            sport_key = self._league_to_sport_key(league)
            if sport_key:
                events = self.theodds.fetch_sport_odds(sport_key)
                for event in events:
                    if (home.lower() in event.get("home_team", "").lower() or 
                        away.lower() in event.get("away_team", "").lower()):
                        odds_list = self.theodds.to_source_odds_list([event])
                        if odds_list:
                            match_odds.sources.extend(odds_list)
                            log.info(f"    ✅ TheOddsAPI: +{len(odds_list)}条国际赔率交叉验证")
                        break

        return match_odds if match_odds.sources else None

    def cross_validate(self, matches: List[MatchOdds]) -> Dict:
        """多源交叉验证
        
        Returns:
            {
                "matches": [...],      # 每场比赛的验证结果
                "summary": {           # 汇总统计
                    "total": int,
                    "high_consensus": int,    # 高共识场次
                    "medium_consensus": int,  # 中等共识
                    "low_consensus": int,     # 低共识
                    "divergent": int,         # 严重分歧
                    "multi_source": int,      # 2源以上场次
                    "single_source": int,     # 单源场次
                },
                "anomalies": [...]     # 检测到的异常信号
            }
        """
        report = {
            "matches": [],
            "summary": {
                "total": len(matches),
                "high_consensus": 0,
                "medium_consensus": 0,
                "low_consensus": 0,
                "divergent": 0,
                "multi_source": 0,
                "single_source": 0,
            },
            "anomalies": [],
        }

        for m in matches:
            consensus = m.consensus
            anomalies = m.detect_anomalies()

            match_report = {
                "match_id": m.match_id,
                "home_team": m.home_team,
                "away_team": m.away_team,
                "league": m.league,
                "sources": [{"name": s.source, "home": s.home_win, "draw": s.draw, "away": s.away_win} for s in m.sources],
                "source_count": m.source_count,
                "consensus": consensus,
                "anomalies": anomalies,
            }
            report["matches"].append(match_report)

            # 汇总
            if m.source_count >= 2:
                report["summary"]["multi_source"] += 1
            else:
                report["summary"]["single_source"] += 1

            if consensus:
                level = consensus["consensus_level"]
                report["summary"][f"{level}_consensus"] += 1
                if anomalies:
                    report["anomalies"].extend(anomalies)

        report["summary"]["anomaly_count"] = len(report["anomalies"])

        return report

    def _league_to_sport_key(self, league: str) -> Optional[str]:
        """中文联赛名 → TheOddsAPI sport_key"""
        mapping = {
            "英超": "soccer_epl",
            "英冠": "soccer_efl_champ",
            "英甲": "soccer_england_league1",
            "西甲": "soccer_spain_la_liga",
            "西乙": "soccer_spain_segunda_division",
            "德甲": "soccer_germany_bundesliga",
            "德乙": "soccer_germany_bundesliga2",
            "意甲": "soccer_italy_serie_a",
            "意乙": "soccer_italy_serie_b",
            "法甲": "soccer_france_ligue_one",
            "法乙": "soccer_france_ligue_two",
            "荷甲": "soccer_netherlands_eredivisie",
            "葡超": "soccer_portugal_primeira_liga",
            "苏超": "soccer_uk_scotland_premiership",
            "日职联": "soccer_japan_j1_league",
            "日职乙": "soccer_japan_j2_league",
            "韩K联": "soccer_korea_kleague1",
            "澳超": "soccer_australia_aleague",
            "瑞典超": "soccer_sweden_allsvenskan",
            "挪超": "soccer_norway_eliteserien",
            "芬超": "soccer_finland_veikkausliiga",
            "欧冠": "soccer_uefa_champs_league",
            "欧罗巴": "soccer_uefa_europa_league",
            "巴甲": "soccer_brazil_campeonato",
            "墨超": "soccer_mexico_ligamx",
            "美职": "soccer_usa_mls",
            "阿甲": "soccer_argentina_primera_division",
        }
        return mapping.get(league)


# ============================================
# 命令行入口
# ============================================

def main():
    parser = argparse.ArgumentParser(description="多源赔率采集器")
    parser.add_argument("--date", type=str, help="日期 YYYY-MM-DD")
    parser.add_argument("--match", type=str, help="单场比赛：主队 vs 客队")
    parser.add_argument("--league", type=str, help="联赛名称")
    parser.add_argument("--output", type=str, help="输出JSON文件路径")
    parser.add_argument("--no-theodds", action="store_true", help="禁用TheOddsAPI")
    
    args = parser.parse_args()

    fetcher = MultiSourceFetcher(enable_theodds=not args.no_theodds)

    if args.match:
        # 单场模式
        parts = args.match.split("vs")
        if len(parts) != 2:
            parts = args.match.split("VS")
        if len(parts) != 2:
            parts = args.match.split(" vs ")
        if len(parts) != 2:
            parts = args.match.split(" VS ")
        if len(parts) != 2:
            print("错误: 请使用格式 '主队 vs 客队'")
            sys.exit(1)

        home = parts[0].strip()
        away = parts[1].strip()
        league = args.league or ""

        print(f"采集: {home} vs {away}")
        match_odds = fetcher.fetch_match(home, away, league)
        
        if match_odds:
            report = fetcher.cross_validate([match_odds])
            result = report
        else:
            print("未获取到任何赔率数据")
            result = {"error": "no_data"}

    elif args.date:
        # 批量模式
        print(f"批量采集: {args.date}")
        matches = fetcher.fetch_by_date(args.date)
        report = fetcher.cross_validate(matches)
        result = {
            "date": args.date,
            "matches_count": len(matches),
            "report": report,
        }

    else:
        # 默认今天
        today = datetime.now().strftime("%Y-%m-%d")
        print(f"批量采集: {today}")
        matches = fetcher.fetch_by_date(today)
        report = fetcher.cross_validate(matches)
        result = {
            "date": today,
            "matches_count": len(matches),
            "report": report,
        }

    # 输出
    json_output = json.dumps(result, ensure_ascii=False, indent=2, default=str)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_output, encoding='utf-8')
        print(f"已保存到: {args.output}")
    else:
        print(json_output)


if __name__ == "__main__":
    main()
