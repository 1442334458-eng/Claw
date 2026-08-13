#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  多源赔率采集器 v1.0
  Multi-Source Odds Collector
============================================

三路赔率采集 + WebSearch兜底：
  路1: 竞彩官方 (jc-mcp → sporttery.cn) → 中国竞彩SPF/让球/比分
  路2: 500.com WebFetch → 百家欧指(澳彩+盈禾+立博+威廉等49家)
  路3: TheOddsAPI → Bet365/Pinnacle/Betfair 国际赔率
  兜底: WebSearch → 赔率关键词搜索引擎降级

输出统一格式 MultiSourceOddsReport，供 cross_validate.py 消费。

设计原则：
  - 三级降级链: API → WebFetch → WebSearch → 缓存
  - 每条赔率标注 source_type (official/api/web/fallback)
  - 时效标记 freshness: realtime / <1h / <6h / <24h / stale
  - 可用率: jc-mcp ✅ / 500.com ✅ / TheOddsAPI ✅

依赖: main.py 的 OddsData, MatchData, CONFIG

作者：CodeBuddy Code (管道 v2.1 升级)
日期：2026-08-10
版本：v1.0
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

# 添加父目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

log = logging.getLogger(__name__)


# ============================================
# 数据模型
# ============================================

class SourceType(Enum):
    OFFICIAL = "official"      # 竞彩官方 (sporttery.cn)
    API = "api"                # TheOddsAPI 等付费API
    WEB = "web"                # WebFetch (500.com等)
    FALLBACK = "fallback"      # WebSearch 降级
    CACHED = "cached"          # 本地缓存

class Freshness(Enum):
    REALTIME = "realtime"      # <5min
    HOUR_1 = "<1h"            # <1小时
    HOUR_6 = "<6h"            # <6小时
    HOUR_24 = "<24h"          # <24小时
    STALE = "stale"           # >24小时


@dataclass
class BookmakerOdds:
    """单家博彩公司赔率"""
    name: str                           # 博彩公司名称 (e.g. "竞彩", "Bet365", "澳彩")
    source_type: SourceType = SourceType.WEB
    freshness: Freshness = Freshness.HOUR_6
    collected_at: str = ""              # ISO 8601 采集时间
    home_win: float = 0.0               # 主胜赔率 (decimal)
    draw: float = 0.0                   # 平局赔率
    away_win: float = 0.0               # 客胜赔率
    asian_opening: float = 0.0          # 亚盘初盘
    asian_current: float = 0.0          # 亚盘即时盘
    asian_opening_water_home: float = 0.0  # 初盘主队水位
    asian_opening_water_away: float = 0.0  # 初盘客队水位
    asian_current_water_home: float = 0.0  # 即时主队水位
    asian_current_water_away: float = 0.0  # 即时客队水位
    over_line: float = 0.0              # 大小球盘口
    over_odds: float = 0.0              # 大球赔率
    under_odds: float = 0.0             # 小球赔率
    commission_rate: float = 0.0        # 抽水率 (隐含)
    raw_data: Dict = field(default_factory=dict)  # 原始数据


@dataclass
class MultiSourceOddsReport:
    """多源赔率汇总报告"""
    match_id: str = ""
    home_team: str = ""
    away_team: str = ""
    league: str = ""
    kickoff_time: str = ""
    generated_at: str = ""

    # 各博彩公司赔率
    bookmakers: List[BookmakerOdds] = field(default_factory=list)

    # 汇总统计
    home_win_range: Tuple[float, float] = (0, 0)   # (min, max)
    draw_range: Tuple[float, float] = (0, 0)
    away_win_range: Tuple[float, float] = (0, 0)
    source_count: int = 0
    source_types_used: List[str] = field(default_factory=list)

    # 元数据
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ============================================
# 采集器: 路1 — 竞彩官方 (jc-mcp)
# ============================================

class JcMcpCollector:
    """
    竞彩官方赔率采集器
    通过 jc-mcp MCP 服务器获取 sporttery.cn 官方赔率

    数据特点:
      - 返奖率 ~71%
      - 中国竞彩市场基准
      - 数据最权威、最及时
    """

    def __init__(self):
        self.available = self._check_availability()

    def _check_availability(self) -> bool:
        """检查 jc-mcp 是否可用"""
        # jc-mcp 通过 MCP 协议调用，需要 CodeBuddy 环境
        # 在纯Python脚本中通过环境变量判断
        return os.environ.get('JC_MCP_ENABLED', '1') == '1'

    def fetch_odds(self, match_id: str = "",
                   home_team: str = "", away_team: str = "",
                   date_str: str = "") -> Optional[BookmakerOdds]:
        """
        从 jc-mcp 获取单场比赛赔率

        Args:
            match_id: 竞彩比赛编号 (e.g. "1001")
            home_team: 主队名称
            away_team: 客队名称
            date_str: 日期 (YYYY-MM-DD)

        Returns:
            BookmakerOdds 或 None
        """
        if not self.available:
            return None

        # jc-mcp 通过 MCP 协议提供赔率
        # 此方法生成调用清单，外部调度器(CodeBuddy)执行实际调用
        bm = BookmakerOdds(
            name="竞彩官方",
            source_type=SourceType.OFFICIAL,
            freshness=Freshness.REALTIME,
            collected_at=datetime.now().isoformat()
        )

        # 调用标记: 由外部MCP调度器填充实际数据
        bm.raw_data = {
            "_collector": "jc_mcp",
            "_method": "get_jc_odds_simple",
            "_params": {
                "match_id": match_id,
                "date": date_str or datetime.now().strftime('%Y-%m-%d')
            },
            "_status": "pending_external_fill"
        }

        log.info(f"  🎫 竞彩官方: 标记 {home_team} vs {away_team} (待MCP填充)")
        return bm


# ============================================
# 采集器: 路2 — 500.com 百家欧指
# ============================================

class WubaicomCollector:
    """
    500.com 百家欧指采集器
    通过 WebFetch 获取 49家博彩公司的欧赔/亚盘/大小球

    数据特点:
      - 49家博彩公司赔率对比
      - 含 澳彩(Macau Slot) 亚盘基准水位
      - 含 盈禾(Wewbet) 亚洲庄家赔率
      - 含 立博(Ladbrokes)/威廉希尔(William Hill) 欧洲庄家
      - 初盘+即时盘对比
      - 百家平均+离散值
    """

    # 500.com 赔率分析的 URL 模式
    URL_PATTERN = "https://odds.500.com/fenxi/ouzhi-{match_hash}.shtml"

    def __init__(self):
        self.available = True  # WebFetch 始终可用

    def generate_fetch_task(self, match_hash: str,
                            home_team: str, away_team: str) -> Dict:
        """
        生成500.com WebFetch任务

        由于500.com使用数字hash而非队名作为URL参数，
        实际调用需要通过WebSearch先查到正确的hash，
        然后再用WebFetch获取赔率数据。

        此方法返回WebFetch的任务描述，供外部调度器执行。
        """
        return {
            "_collector": "500com",
            "_method": "WebFetch",
            "_url": f"https://odds.500.com/fenxi/ouzhi-{match_hash}.shtml" if match_hash else None,
            "_search_url_pattern": f"https://odds.500.com/fenxi/ouzhi-{{hash}}.shtml",
            "_teams": f"{home_team} vs {away_team}",
            "_target_bookmakers": [
                "竞彩官方",       # 官方参考
                "澳门彩票",       # 澳彩 (ID:1 亚盘基准)
                "盈禾/Wewbet",    # 亚洲庄家 (ID:47)
                "立博/Ladbrokes", # 欧洲传统 (ID:4)
                "威廉希尔/William Hill", # 英国主流 (ID:9)
                "Bet365",        # 国际主流 (ID:8)
                "平博/Pinnacle",  # 锋线庄家
                "百家欧指",       # 49家平均
            ],
            "_data_fields": [
                "初盘_主胜", "初盘_平局", "初盘_客胜",
                "即时_主胜", "即时_平局", "即时_客胜",
                "亚盘初盘", "亚盘即时盘", "亚盘水位变化",
                "大小球盘口", "大小球赔率",
                "离散值", "凯利指数"
            ],
            "_status": "pending_webfetch"
        }

    def parse_odds_from_html(self, html_content: str) -> List[BookmakerOdds]:
        """
        从500.com HTML解析赔率数据

        500.com 赔率页面结构:
          <table id="oddsTable">
            <tr data-bid="1">  ← 澳彩
            <tr data-bid="8">  ← Bet365
            <tr data-bid="9">  ← William Hill
            ...
        """
        results = []
        # HTML解析在实际调用时由外部完成
        # 此处保留接口供集成使用
        return results


# ============================================
# 采集器: 路3 — TheOddsAPI
# ============================================

class TheOddsCollector:
    """
    TheOddsAPI 国际赔率采集器
    已有集成 (main.py OddsAPIClient)，此处做封装适配

    数据特点:
      - 50+ 博彩公司
      - Pinnacle 锋线赔率 (最sharp)
      - Bet365 国际主流
      - 实时更新
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get('ODDS_API_KEY', '')
        self.available = bool(self.api_key)

    def wrap_odds_to_bookmaker(self, api_response: Dict,
                               bm_name: str = "Bet365") -> Optional[BookmakerOdds]:
        """
        将 TheOddsAPI 返回的赔率转换为统一 BookmakerOdds 格式
        """
        if not api_response:
            return None

        bm = BookmakerOdds(
            name=bm_name,
            source_type=SourceType.API,
            freshness=Freshness.REALTIME,
            collected_at=datetime.now().isoformat()
        )

        # 从API响应中提取数据 (兼容OddsAPIClient的解析逻辑)
        for item in (api_response if isinstance(api_response, list) else [api_response]):
            for bkm in item.get('bookmakers', []):
                if bkm.get('title', '') != bm_name:
                    continue

                for market in bkm.get('markets', []):
                    mk = market.get('key', '')
                    outcomes = market.get('outcomes', [])

                    if mk == 'h2h':
                        # 解析 1X2
                        o_dict = {o['name']: o['price'] for o in outcomes}
                        bm.home_win = o_dict.get('Home', o_dict.get(list(o_dict.keys())[0], 0))
                        bm.draw = o_dict.get('Draw', 0)
                        away_key = [k for k in o_dict if k not in ('Home', 'Draw')]
                        bm.away_win = o_dict.get(away_key[0], 0) if away_key else 0

                    elif mk == 'spreads':
                        for o in outcomes:
                            if o['name'] == 'Home':
                                bm.asian_current = o.get('point', 0)
                                bm.asian_current_water_home = o.get('price', 0)
                            elif o['name'] == 'Away':
                                bm.asian_current_water_away = o.get('price', 0)

                    elif mk == 'totals':
                        for o in outcomes:
                            if o['name'] == 'Over':
                                bm.over_line = o.get('point', 2.5)
                                bm.over_odds = o.get('price', 0)
                            elif o['name'] == 'Under':
                                bm.under_odds = o.get('price', 0)

                bm.raw_data = bkm
                return bm

        return None


# ============================================
# 兜底模块: WebSearch 降级
# ============================================

class WebSearchFallback:
    """
    WebSearch 赔率数据降级模块
    当所有API/WebFetch不可用时，通过搜索引擎获取赔率

    搜索策略:
      关键词: "{home} vs {away} 赔率 竞彩 今日"
      → 从搜索结果文本中提取赔率数字
    """

    SEARCH_TEMPLATES = [
        "{home} vs {away} 赔率 竞彩 {date}",
        "{home} {away} betting odds analysis",
        "{home} vs {away} 百家欧赔 即时赔率",
    ]

    def __init__(self):
        self.available = True

    def generate_search_task(self, home_team: str, away_team: str,
                             date_str: str = "") -> Dict:
        """生成WebSearch降级任务"""
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        queries = []
        for tmpl in self.SEARCH_TEMPLATES:
            q = tmpl.format(home=home_team, away=away_team, date=date_str)
            queries.append(q)

        return {
            "_collector": "websearch_fallback",
            "_method": "WebSearch",
            "_queries": queries,
            "_parse_instructions": "从搜索结果提取赔率: 主胜/平局/客胜 (decimal格式)",
            "_status": "pending_search"
        }


# ============================================
# 主采集器: 三路并行 + 降级链
# ============================================

class MultiSourceOddsEngine:
    """
    多源赔率采集引擎

    三级降级链:
      Level 1: API 直接调用 (jc-mcp + TheOddsAPI)
      Level 2: WebFetch 网页采集 (500.com)
      Level 3: WebSearch 搜索引擎降级
      Level 4: 本地缓存快照 (cache/{date}_snapshot.json)

    使用流程:
      1. engine = MultiSourceOddsEngine()
      2. report = engine.collect("1001", "天狼星", "布鲁马波", "瑞典超")
      3. 外部调度器根据 report 中的 _pending_tasks 执行采集
      4. engine.fill_report(report, collected_data)
      5. 输出最终 MultiSourceOddsReport
    """

    def __init__(self, cache_dir: Path = None):
        self.jc_collector = JcMcpCollector()
        self.wubaicom = WubaicomCollector()
        self.theodds = TheOddsCollector()
        self.fallback = WebSearchFallback()

        self.cache_dir = cache_dir or Path(__file__).parent / "cache"
        self.cache_dir.mkdir(exist_ok=True)

    def collect(self, match_id: str, home_team: str, away_team: str,
                league: str = "", date_str: str = "",
                kickoff_time: str = "") -> MultiSourceOddsReport:
        """
        主采集入口：生成采集任务清单

        外部调度器(CodeBuddy)读取 _pending_tasks 后执行采集，
        再调用 fill_report() 填入实际数据。

        Returns:
            MultiSourceOddsReport (含 _pending_tasks 标记)
        """
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')

        report = MultiSourceOddsReport(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league=league,
            kickoff_time=kickoff_time or date_str,
            generated_at=datetime.now().isoformat()
        )

        # 尝试从缓存加载
        cached = self._load_cache(match_id, date_str)
        if cached:
            report.bookmakers.extend(cached)
            report.source_count += len(cached)
            report.source_types_used.append("cached")
            log.info(f"  📦 缓存命中: {match_id} ({len(cached)}条赔率)")

        # === Level 1: API 采集 ===
        # 竞彩官方 (jc-mcp)
        jc_bm = self.jc_collector.fetch_odds(match_id, home_team, away_team, date_str)
        if jc_bm:
            report.bookmakers.append(jc_bm)
            report.source_count += 1
            report.source_types_used.append("official")

        # TheOddsAPI
        if self.theodds.available:
            # 标记 Pinnacle (高价值锋线赔率)
            pin_bm = BookmakerOdds(
                name="Pinnacle",
                source_type=SourceType.API,
                freshness=Freshness.REALTIME,
                collected_at=datetime.now().isoformat(),
                raw_data={"_collector": "theoddsapi", "_status": "pending_api"}
            )
            # 标记 Bet365
            b365_bm = BookmakerOdds(
                name="Bet365",
                source_type=SourceType.API,
                freshness=Freshness.REALTIME,
                collected_at=datetime.now().isoformat(),
                raw_data={"_collector": "theoddsapi", "_status": "pending_api"}
            )
            report.bookmakers.extend([pin_bm, b365_bm])
            report.source_count += 2
            report.source_types_used.append("api")

        # === Level 2: WebFetch 采集 ===
        # 500.com 百家欧指 (澳彩+盈禾+立博+威廉)
        # 使用待填充标记，由外部WebFetch调度器填充
        for bm_name in ["澳彩", "盈禾", "立博", "威廉希尔"]:
            bm = BookmakerOdds(
                name=bm_name,
                source_type=SourceType.WEB,
                freshness=Freshness.HOUR_6,
                collected_at=datetime.now().isoformat(),
                raw_data={
                    "_collector": "500com",
                    "_method": "WebFetch",
                    "_status": "pending_webfetch"
                }
            )
            report.bookmakers.append(bm)
        report.source_count += 4
        report.source_types_used.append("web")

        # === Level 3: WebSearch 兜底 ===
        # 所有API+WebFetch都失败时启用
        fallback_task = self.fallback.generate_search_task(home_team, away_team, date_str)
        report.raw_data = {"fallback_task": fallback_task}

        # 计算赔率范围
        self._compute_ranges(report)

        # 保存到缓存
        self._save_cache(report)

        log.info(f"  ✅ 多源采集: {match_id} ({home_team} vs {away_team}) → "
                 f"{report.source_count}个数据源 [{', '.join(report.source_types_used)}]")

        return report

    def fill_report(self, report: MultiSourceOddsReport,
                    collected_data: Dict[str, Dict]) -> MultiSourceOddsReport:
        """
        外部调度器调用：将实际采集到的数据填入report

        Args:
            report: collect() 返回的报告 (含 fill_me 标记)
            collected_data: {
                "竞彩官方": {"home_win": 1.19, "draw": 5.80, "away_win": 8.55},
                "澳彩": {...},
                ...
            }

        Returns:
            填充后的完整报告
        """
        for bm in report.bookmakers:
            if bm.name in collected_data:
                data = collected_data[bm.name]
                bm.home_win = data.get('home_win', bm.home_win)
                bm.draw = data.get('draw', bm.draw)
                bm.away_win = data.get('away_win', bm.away_win)
                bm.asian_current = data.get('asian_current', bm.asian_current)
                bm.asian_opening = data.get('asian_opening', bm.asian_opening)
                bm.raw_data['_status'] = 'filled'

        # 重新计算范围
        self._compute_ranges(report)

        # 更新缓存
        self._save_cache(report)

        return report

    def get_consensus_score(self, report: MultiSourceOddsReport) -> Dict:
        """
        快速共识度评估 (简化版，完整版见 cross_validate.py)

        Returns:
            {
                "consensus_level": "high" | "medium" | "low" | "divergent",
                "cv_coefficient": float,
                "outlier_count": int,
                "recommendation": str
            }
        """
        filled_bms = [bm for bm in report.bookmakers
                      if bm.home_win > 0 and bm.draw > 0 and bm.away_win > 0]

        if len(filled_bms) < 3:
            return {
                "consensus_level": "low",
                "cv_coefficient": 99.0,
                "outlier_count": 0,
                "recommendation": "数据源不足(<3家)，无法评估共识度"
            }

        # 计算主胜赔率的变异系数 (CV)
        home_odds = [bm.home_win for bm in filled_bms]
        mean_h = sum(home_odds) / len(home_odds)
        if mean_h > 0:
            variance = sum((x - mean_h) ** 2 for x in home_odds) / len(home_odds)
            std_dev = variance ** 0.5
            cv = std_dev / mean_h
        else:
            cv = 0

        # 判定共识等级
        if cv < 0.03:
            level = "high"
        elif cv < 0.08:
            level = "medium"
        elif cv < 0.15:
            level = "low"
        else:
            level = "divergent"

        # 2σ 异常检测
        outliers = []
        for bm in filled_bms:
            z = abs(bm.home_win - mean_h) / std_dev if std_dev > 0 else 0
            if z > 2.0:
                outliers.append(bm.name)

        return {
            "consensus_level": level,
            "cv_coefficient": round(cv, 4),
            "outlier_count": len(outliers),
            "outlier_bookmakers": outliers,
            "recommendation": self._get_consensus_advice(level, outliers)
        }

    def _get_consensus_advice(self, level: str, outliers: List[str]) -> str:
        if level == "divergent":
            return "⚠️ 赔率严重分歧！建议等临场赔率稳定后再分析"
        elif level == "low":
            return "⚠️ 赔率分歧较大，星级降1档 + 建议双选"
        elif outliers:
            return f"⚠️ 检测到异常庄家: {', '.join(outliers)}，忽略其数据"
        elif level == "high":
            return "✅ 赔率高度共识，可信度加持"
        else:
            return "➡️ 赔率分歧正常范围"

    def _compute_ranges(self, report: MultiSourceOddsReport):
        """计算赔率范围统计"""
        filled = [bm for bm in report.bookmakers
                  if bm.home_win > 0]
        if filled:
            home_vals = [bm.home_win for bm in filled]
            draw_vals = [bm.draw for bm in filled]
            away_vals = [bm.away_win for bm in filled]
            report.home_win_range = (min(home_vals), max(home_vals))
            report.draw_range = (min(draw_vals), max(draw_vals))
            report.away_win_range = (min(away_vals), max(away_vals))

    def _cache_path(self, match_id: str, date_str: str) -> Path:
        return self.cache_dir / f"odds_{date_str}_{match_id}.json"

    def _load_cache(self, match_id: str, date_str: str) -> List[BookmakerOdds]:
        path = self._cache_path(match_id, date_str)
        if not path.exists():
            return []

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检查缓存时效 (1小时内有效)
            cached_at = data.get('generated_at', '')
            if cached_at:
                dt = datetime.fromisoformat(cached_at)
                age = (datetime.now() - dt).total_seconds()
                if age > 3600:  # >1小时，过期
                    log.info(f"  ⏰ 缓存过期 ({age/60:.0f}min): {match_id}")
                    return []

            bms = []
            for bm_data in data.get('bookmakers', []):
                bm = BookmakerOdds(
                    name=bm_data['name'],
                    source_type=SourceType.CACHED,
                    freshness=Freshness.HOUR_6,
                    home_win=bm_data.get('home_win', 0),
                    draw=bm_data.get('draw', 0),
                    away_win=bm_data.get('away_win', 0),
                    asian_opening=bm_data.get('asian_opening', 0),
                    asian_current=bm_data.get('asian_current', 0),
                )
                bms.append(bm)

            return bms
        except Exception:
            return []

    def _save_cache(self, report: MultiSourceOddsReport):
        """保存赔率快照到本地缓存"""
        filled_bms = [bm for bm in report.bookmakers
                       if bm.home_win > 0]
        if not filled_bms:
            return

        date_str = report.kickoff_time[:10] if report.kickoff_time else datetime.now().strftime('%Y-%m-%d')
        path = self._cache_path(report.match_id, date_str)

        cache_data = {
            "match_id": report.match_id,
            "home_team": report.home_team,
            "away_team": report.away_team,
            "generated_at": report.generated_at,
            "bookmakers": [
                {
                    "name": bm.name,
                    "source_type": bm.source_type.value,
                    "home_win": bm.home_win,
                    "draw": bm.draw,
                    "away_win": bm.away_win,
                    "asian_opening": bm.asian_opening,
                    "asian_current": bm.asian_current,
                    "asian_opening_water_home": bm.asian_opening_water_home,
                    "asian_current_water_home": bm.asian_current_water_home,
                }
                for bm in filled_bms
            ]
        }

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)


# ============================================
# 便捷函数
# ============================================

def quick_collect(match_id: str, home: str, away: str,
                  league: str = "", date: str = "") -> Dict:
    """快速采集单场比赛多源赔率 (返回JSON)"""
    engine = MultiSourceOddsEngine()
    report = engine.collect(match_id, home, away, league, date)
    consensus = engine.get_consensus_score(report)

    return {
        "match": f"{home} vs {away}",
        "match_id": match_id,
        "sources": report.source_count,
        "source_types": report.source_types_used,
        "consensus": consensus,
        "bookmakers": [
            {
                "name": bm.name,
                "spf": [bm.home_win, bm.draw, bm.away_win],
                "asian": bm.asian_current,
                "source": bm.source_type.value,
                "status": bm.raw_data.get('_status', 'unknown')
            }
            for bm in report.bookmakers
        ],
        "home_win_range": list(report.home_win_range),
        "draw_range": list(report.draw_range),
        "away_win_range": list(report.away_win_range),
    }


# ============================================
# 自测
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print("=" * 60)
    print("  多源赔率采集器 v1.0 - 自测")
    print("=" * 60)

    engine = MultiSourceOddsEngine()

    # 测试用例 (天狼星 vs 布鲁马波 — 2026-08-10 22:00瑞超)
    test_matches = [
        ("1001", "天狼星", "布洛马波卡纳", "瑞典超", "2026-08-10"),
        ("1002", "韦斯特罗斯", "尤尔加登", "瑞典超", "2026-08-10"),
        ("1003", "圣克拉拉", "葡萄牙国民", "葡超", "2026-08-10"),
    ]

    for mid, home, away, league, dt in test_matches:
        print(f"\n{'─' * 40}")
        report = engine.collect(mid, home, away, league, dt)
        consensus = engine.get_consensus_score(report)
        print(f"  📊 {home} vs {away}")
        print(f"     数据源: {report.source_count} ({', '.join(report.source_types_used)})")
        print(f"     共识度: {consensus['consensus_level']} (CV={consensus['cv_coefficient']})")
        print(f"     建议: {consensus['recommendation']}")

    print(f"\n{'=' * 60}")
    print(f"  ✅ 自测完成")
    print(f"  注意: 赔率数据需要外部MCP/WebFetch调度器填充")
    print(f"{'=' * 60}")
