#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  足球数据聚合器 v2.0 (双引擎混合架构)
  Football Data Aggregator v2.0 (Hybrid Dual-Engine)
============================================

架构升级说明 (v1 → v2):
  v1 问题：核心逻辑绑死 API-Football (RapidAPI)，用户注册受阻(reCAPTCHA)
  v2 方案：双引擎混合模式

  ┌─────────────────────────────────────────────────────┐
  │                  引擎 A: API 直接调用                │
  │  ├─ The Odds API        → 赔率/亚盘变动 ✅ 已有Key   │
  │  ├─ football-data.org   → 积分/赛程(大联赛) 🔄 等Key  │
  │  └─ Open-Meteo          → 天气 ✅ 无需Key            │
  ├─────────────────────────────────────────────────────┤
  │              引擎 B: WebSearch 结构化降级            │
  │  └─ 14词情报模板(YAML配置) → 伤停/H2H/首发/PFI/新闻  │
  │     基于 维京2-1 / 博德1-2 100%命中验证的方法论       │
  └─────────────────────────────────────────────────────┘

数据源优先级：
  Layer 1 (伤停/阵容): WebSearch > API-Football(RapidAPI) > football-data
  Layer 2 (H2H):      WebSearch > API-Football
  Layer 3 (赔率):     The Odds API > WebSearch
  Layer 4 (PFI):     WebSearch > API-Football fixtures
  Layer 5 (天气):    Open-Meteo > WebSearch
  Layer 6 (新闻):    WebSearch only

使用方法：
  python main.py --matches "Viking vs Sarpsborg,Bodoe Glimt vs Valerenga"
  python main.py --league ELITESERIEN --days 3
  python main.py --file matches.txt
  python main.py --websearch-only  (强制使用WebSearch降级模式)

作者：CodeBuddy Code (铁律系统 v7.5.2.7)
日期：2026-08-09
版本：v2.0 (Hybrid Architecture)
"""

import os
import sys
import json
import time
import logging
import unicodedata
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field

# ============================================
# 配置区
# ============================================

BASE_DIR = Path(__file__).parent
CACHE_DIR = BASE_DIR / "cache"
LOG_DIR = BASE_DIR / "logs"
ENV_FILE = BASE_DIR / ".env"
TEMPLATE_FILE = BASE_DIR / "websearch_templates.yaml"

# 确保目录存在
CACHE_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"pipeline_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)


# ============================================
# 加载API Keys
# ============================================

def load_env():
    """从.env文件加载API Key"""
    if not ENV_FILE.exists():
        log.warning(f"⚠️  .env文件不存在: {ENV_FILE}")
        log.warning("请复制 .env.example 为 .env 并填入你的API Key")
        return {}

    keys = {}
    with open(ENV_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                keys[key.strip()] = value.strip()

    log.info(f"✅ 已加载 {len(keys)} 个配置项")
    return keys


CONFIG = load_env()

ODDS_API_KEY = CONFIG.get('ODDS_API_KEY', '')
FOOTBALL_DATA_TOKEN = CONFIG.get('FOOTBALL_DATA_TOKEN', '')  # football-data.org token


# ============================================
# 数据模型 (保持v1不变)
# ============================================

@dataclass
class OddsData:
    """赔率数据"""
    home_win: float = 0.0
    draw: float = 0.0
    away_win: float = 0.0
    asian_opening: float = 0.0
    asian_current: float = 0.0
    asian_change: float = 0.0
    asian_change_detected: bool = False
    total_over: float = 0.0
    total_under: float = 0.0
    sources: List[str] = field(default_factory=list)


@dataclass
class InjuryRecord:
    """伤停记录"""
    name: str = ""
    position: str = ""
    reason: str = ""
    days_out: int = 0
    expected_return: str = ""


@dataclass
class TeamData:
    """球队数据"""
    name: str = ""
    id: int = 0
    ranking: int = 0
    points: int = 0
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_diff: int = 0
    form_last5: str = ""
    missing_players: List[InjuryRecord] = field(default_factory=list)


@dataclass
class H2HRecord:
    """交锋记录"""
    date: str = ""
    home_team: str = ""
    away_team: str = ""
    home_score: int = 0
    away_score: int = 0
    winner: str = ""


@dataclass
class PFIData:
    """疲劳度检测数据"""
    level: str = "none"
    last_match_date: str = ""
    last_competition: str = ""
    rest_days: int = 99
    last_match_venue: str = ""
    travel_distance_km: float = 0.0
    extra_match_in_7d: bool = False
    core_player_minutes: int = 0


@dataclass
class MatchData:
    """单场比赛完整数据"""
    match_id: str = ""
    league: str = ""
    season: str = "2026"
    home_team: TeamData = field(default_factory=TeamData)
    away_team: TeamData = field(default_factory=TeamData)
    kickoff_time: str = ""
    venue: str = ""
    city: str = ""
    country: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    odds: OddsData = field(default_factory=OddsData)
    h2h_last10: List[H2HRecord] = field(default_factory=list)
    pfi_home: PFIData = field(default_factory=PFIData)
    pfi_away: PFIData = field(default_factory=PFIData)
    weather: Dict[str, Any] = field(default_factory=dict)
    lineup_home: List[str] = field(default_factory=list)
    lineup_away: List[str] = field(default_factory=list)
    data_sources: List[str] = field(default_factory=list)
    collected_at: str = ""
    confidence: str = ""
    data_quality_tier: str = ""  # 新增：数据质量分级 (🟢AAA/🟢AA/🟡A/🟠B/⚪C)
    _quality_meta: Dict[str, Any] = field(default_factory=dict, repr=False)  # 内部质量元数据
    websearch_results: Dict[str, Any] = field(default_factory=dict)  # 新增：WebSearch原始结果


# ============================================
# API 客户端
# ============================================

import urllib.request
import urllib.error
import urllib.parse
import ssl

ssl_ctx = ssl.create_default_context()


def api_get(url: str, headers: Dict[str, str] = {}, timeout: int = 30) -> Optional[Dict]:
    """通用GET请求封装"""
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data
    except urllib.error.HTTPError as e:
        log.error(f"  ❌ HTTP {e.code}: {url[:60]}")
        return None
    except urllib.error.URLError as e:
        log.warning(f"  ⚠️ 网络错误: {e.reason} ({url[:50]}...)")
        return None
    except Exception as e:
        log.error(f"  ❌ 未知错误: {type(e).__name__}: {e}")
        return None


def rate_limit(min_interval: float = 1.5):
    """请求间隔控制"""
    time.sleep(min_interval)


# ------------------------------------------
# The Odds API 客户端 (保持不变)
# ------------------------------------------

class OddsAPIClient:
    """The Odds API - 赔率数据"""

    BASE_URL = "https://api.the-odds-api.com/v4"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.enabled = bool(api_key)

    def search_matches(self, sport_key: str, days_from_now: int = 3) -> List[Dict]:
        if not self.enabled:
            return []

        url = (
            f"{self.BASE_URL}/sports/{sport_key}/odds/"
            f"?apiKey={self.api_key}"
            f"&regions=eu&markets=h2h,spreads,totals"
            f"&oddsFormat=decimal&dateFormat=iso"
        )

        data = api_get(url)
        if not data:
            return []

        # API v4 可能返回 list 或 {"data": [...]}
        match_list = data if isinstance(data, list) else data.get('data', [])
        if match_list:
            log.info(f"  📊 The Odds API: 找到 {len(match_list)} 场比赛")
        return match_list

    def get_odds_for_match(self, sport_key: str, match_id: str) -> Optional[OddsData]:
        if not self.enabled:
            return None

        url = (
            f"{self.BASE_URL}/sports/{sport_key}/events/{match_id}/odds"
            f"?apiKey={self.api_key}"
            f"&regions=eu&markets=h2h,spreads,totals"
            f"&oddsFormat=decimal"
        )

        data = api_get(url)
        if not data:
            return None

        # API v4 可能返回 list 或 {"data": [...]}
        items = data if isinstance(data, list) else data.get('data', [data])

        odds_data = OddsData()
        bookmakers_seen = []

        for item in items:
            for bm in item.get('bookmakers', []):
                bm_name = bm.get('title', 'unknown')
                bookmakers_seen.append(bm_name)

                for market in bm.get('markets', []):
                    market_key = market.get('key')

                    if market_key == 'h2h':
                        outcomes_list = market.get('outcomes', [])
                        # V4 API: outcome name 是实际队名 (如 "1. FC Nürnberg")，不是 "Home"/"Away"
                        # 第一个 outcome 是主队，第二个是客队，第三个是 Draw
                        if len(outcomes_list) >= 3:
                            # 区分方式：第三个 outcome 的 name 是 "Draw"
                            if outcomes_list[2].get('name', '').lower() == 'draw':
                                odds_data.home_win = outcomes_list[0].get('price', 0)
                                odds_data.away_win = outcomes_list[1].get('price', 0)
                                odds_data.draw = outcomes_list[2].get('price', 0)
                            elif outcomes_list[1].get('name', '').lower() == 'draw':
                                odds_data.home_win = outcomes_list[0].get('price', 0)
                                odds_data.draw = outcomes_list[1].get('price', 0)
                                odds_data.away_win = outcomes_list[2].get('price', 0)
                            else:
                                # 兼容旧格式 (Home/Away/Draw)
                                outcomes = {o['name']: o['price'] for o in outcomes_list}
                                odds_data.home_win = outcomes.get('Home', 0)
                                odds_data.draw = outcomes.get('Draw', 0)
                                odds_data.away_win = outcomes.get('Away', 0)

                    elif market_key == 'spreads':
                        outcomes = market.get('outcomes', [])
                        for o in outcomes:
                            if o['name'] == 'Home':
                                point = o.get('point', 0)
                                if odds_data.asian_opening == 0:
                                    odds_data.asian_opening = point
                                odds_data.asian_current = point
                                odds_data.asian_change = abs(odds_data.asian_current - odds_data.asian_opening)
                                if odds_data.asian_change >= 0.25:
                                    odds_data.asian_change_detected = True

                    elif market_key == 'totals':
                        outcomes = market.get('outcomes', [])
                        for o in outcomes:
                            if o['name'] == 'Over':
                                odds_data.total_over = o['price']
                            elif o['name'] == 'Under':
                                odds_data.total_under = o['price']

        odds_data.sources = list(set(bookmakers_seen))
        return odds_data


# ------------------------------------------
# Football-data.org 客户端 (新增激活)
# ------------------------------------------

class FootballDataClient:
    """
    Football-data.org - 大联赛积分/赛程/历史数据
    免费版限制：10次/分钟
    覆盖联赛：PL/BL1/SA/PD/FL1/PCL 等（见 https://www.football-data.org/documentation/quickstart）
    """

    BASE_URL = "https://api.football-data.org/v4"

    def __init__(self, token: str):
        self.token = token
        self.headers = {"X-Auth-Token": token}
        self.enabled = bool(token)

    def get_standings(self, competition_code: str, season: str = "2026") -> Optional[Dict]:
        """获取积分榜"""
        if not self.enabled:
            return None

        url = f"{self.BASE_URL}/competitions/{competition_code}/standings?season={season}"
        data = api_get(url, headers=self.headers)
        rate_limit(6.0)  # 免费版10次/分钟，保守点用6秒间隔
        if data:
            table = data.get('standings', [{}])[0].get('table', [])
            log.info(f"  📊 Football-data积分榜: {competition_code} → {len(table)}队")
        return data

    def get_matches(self, competition_code: str, days_from_now: int = 7) -> List[Dict]:
        """获取未来N天的比赛"""
        if not self.enabled:
            return []

        start = datetime.now().strftime('%Y-%m-%d')
        end = (datetime.now() + timedelta(days=days_from_now)).strftime('%Y-%m-%d')

        url = f"{self.BASE_URL}/competitions/{competition_code}/matches?status=SCHEDULED&from={start}&to={end}"
        data = api_get(url, headers=self.headers)
        rate_limit(6.0)

        if data and 'matches' in data:
            log.info(f"  📅 Football-data赛程: {competition_code} 未来{days_from_now}天 → {len(data['matches'])}场")
            return data['matches']
        return []

    def get_team_matches(self, team_id: int, days: int = 30) -> List[Dict]:
        """获取球队近期比赛（用于PFI计算）"""
        if not self.enabled:
            return []

        start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        end = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        url = f"{self.BASE_URL}/teams/{team_id}/matches?from={start}&to={end}"
        data = api_get(url, headers=self.headers)
        rate_limit(6.0)

        if data and 'matches' in data:
            return data['matches']
        return []


# ------------------------------------------
# Open-Meteo 天气客户端 (保持不变)
# ------------------------------------------


def normalize_name(name: str) -> str:
    """
    规整球队/城市名称（处理 umlaut、变音符、FC/1. 前缀等）
    "Greuther Fürth" → "greuther furth"
    "FC St. Pauli" → "st pauli"
    "1. FC Nürnberg" → "nurnberg"
    """
    # 1. Unicode 规整：ü→u, ö→o, ä→a, é→e, í→i, ó→o, ú→u, ñ→n
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    # 2. 全小写
    name = name.lower()
    # 3. 去掉常见前缀: "fc ", "1. fc ", "vfl ", "sv ", etc.
    prefixes = ['1. fc ', 'fc ', 'vfl ', 'sv ', 'tsv ', 'sc ', 'rb ', 'ac ', 'acf ', 'as ', 'cd ', 'cf ', 'cs ', 'rc ', 'ud ', 'pfc ', 'fc ']
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    # 4. 去掉冗余空格和标点
    name = name.replace('.', '').replace(',', '').strip()
    return name


class WeatherClient:
    """Open-Meteo 免费天气API"""

    BASE_URL = "https://api.open-meteo.com/v1/forecast"

    CITY_COORDS = {
        "stavanger": (58.97, 5.73),
        "bergen": (60.39, 5.32),
        "oslo": (59.91, 10.75),
        "trondheim": (63.43, 10.40),
        "bodo": (67.28, 14.38),
        "stockholm": (59.33, 18.06),
        "gothenburg": (57.71, 11.97),
        "malmo": (55.60, 13.00),
        "uppsala": (59.86, 17.64),
        "lisbon": (38.72, -9.13),
        "porto": (41.15, -8.63),
        "tokyo": (35.68, 139.69),
        "kashima": (35.97, 140.62),
        "yokohama": (35.44, 139.64),
        "kawasaki": (35.53, 139.70),
        "seoul": (37.57, 126.98),
        "suwon": (37.29, 126.98),
        "jeonju": (35.82, 127.15),
        "daegu": (35.87, 128.60),
        "amsterdam": (52.37, 4.89),
        "rotterdam": (51.92, 4.48),
        "eindhoven": (51.44, 5.47),
        "breda": (51.59, 4.78),
        "bochum": (51.48, 7.22),
        "hamburg": (53.55, 9.99),
        "paris": (48.85, 2.35),
        "lyon": (45.76, 4.84),
        "marseille": (43.30, 5.37),
        # 西班牙（新增）
        "vitoria-gasteiz": (42.85, -2.67),  # 阿拉维斯主场
        "alaves": (42.85, -2.67),
        "getafe": (40.36, -3.73),
        "madrid": (40.42, -3.70),
        "barcelona": (41.39, 2.17),
        "seville": (37.39, -5.98),
        "valencia": (39.47, -0.38),
        "bilbao": (43.26, -2.93),
        "san sebastian": (43.31, -1.99),
    }

    def get_weather(self, city: str, date_str: str = "") -> Dict:
        coords = self.CITY_COORDS.get(city.lower())
        if not coords:
            for c_name, c_coords in self.CITY_COORDS.items():
                if city.lower() in c_name or c_name in city.lower():
                    coords = c_coords
                    break

        if not coords:
            log.warning(f"  🌤️ 未知城市坐标: {city}，跳过天气查询")
            return {}

        lat, lon = coords
        url = (
            f"{self.BASE_URL}"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,precipitation_probability,windspeed_10m,relativehumidity_2m"
            f"&timezone=auto&forecast_days=3"
        )

        data = api_get(url)
        if data and 'hourly' in data:
            weather = {
                "city": city,
                "latitude": lat,
                "longitude": lon,
                "current_temp_c": data['hourly'].get('temperature_2m', [None])[0],
                "precipitation_prob": data['hourly'].get('precipitation_probability', [None])[0],
                "wind_speed_kmh": data['hourly'].get('windspeed_10m', [None])[0],
                "humidity_pct": data['hourly'].get('relativehumidity_2m', [None])[0],
                "source": "Open-Meteo"
            }
            log.info(f"  🌤️ {city}: {weather['current_temp_c']}°C, 风{weather['wind_speed_kmh']}km/h, 湿度{weather['humidity_pct']}%")
            return weather
        return {}


# ============================================
# 🔥🔥🔥 新增：WebSearch 结构化情报收集引擎 🔥🔥🔥
# ============================================

class WebSearchIntelligence:
    """
    WebSearch 结构化情报收集引擎

    核心功能：
    1. 读取 websearch_templates.yaml 中的14个搜索词模板
    2. 按轮次（T-12h/T-6h/T-3h）逐步执行
    3. 调用系统命令触发 WebSearch（通过 CodeBuddy 的 WebSearch 工具）
    4. 将非结构化搜索结果解析为标准化 JSON

    注意：此类不直接执行网络搜索，而是生成「搜索任务清单」，
         由外部调度器（或人工）执行后回填结果。
         在自动化场景下，可通过 subprocess 调用搜索引擎CLI。
    """

    def __init__(self, template_file: Path = TEMPLATE_FILE):
        self.template_file = template_file
        self.templates = []
        self._last_search_time = 0.0
        self._min_delay = 0.5  # 两次搜索之间至少间隔0.5秒，防止Bing限流
        self._max_retries = 2  # 单个搜索词最多重试2次
        self._load_templates()

    def _load_templates(self):
        """加载 YAML 模板文件"""
        try:
            import yaml
            with open(self.template_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            self.templates = config.get('search_templates', [])
            self.execution_strategy = config.get('execution_strategy', {})
            log.info(f"  🔍 WebSearch模板: 已加载 {len(self.templates)} 个搜索词")
        except ImportError:
            log.warning("  ⚠️ PyYAML 未安装，使用内置简化模板")
            self._load_builtin_templates()
        except FileNotFoundError:
            log.warning(f"  ⚠️ 模板文件不存在: {self.template_file}")
            self._load_builtin_templates()

    def _load_builtin_templates(self):
        """内置简化模板（当YAML文件不可用时）"""
        self.templates = [
            {"id": 1, "category": "injuries_home", "template": "{home} injuries {date}", "layer": 1},
            {"id": 2, "category": "injuries_away", "template": "{away} injuries {date}", "layer": 1},
            {"id": 3, "category": "lineup_home", "template": "{home} predicted lineup {date}", "layer": 1},
            {"id": 4, "category": "lineup_away", "template": "{away} predicted lineup {date}", "layer": 1},
            {"id": 5, "category": "h2h", "template": "{home} vs {away} head to head", "layer": 2},
            {"id": 6, "category": "odds", "template": "{home} vs {away} odds today", "layer": 3},
            {"id": 7, "category": "asian", "template": "{home} vs {away} asian handicap", "layer": 3},
            {"id": 8, "category": "pfi_home", "template": "{home} fixture congestion fatigue", "layer": 4},
            {"id": 9, "category": "pfi_away", "template": "{away} fixture congestion fatigue", "layer": 4},
            {"id": 10, "category": "weather", "template": "{city} weather forecast", "layer": 5},
            {"id": 11, "category": "news", "template": "{home} vs {away} team news", "layer": 6},
            {"id": 12, "category": "lineup_leak_home", "template": "{home} lineup leak confirmed", "layer": 6},
            {"id": 13, "category": "lineup_leak_away", "template": "{away} lineup leak confirmed", "layer": 6},
            {"id": 14, "category": "motivation", "template": "{home} vs {away} motivation stakes", "layer": 6},
        ]
        self.execution_strategy = {"mode": "progressive"}

    def generate_search_tasks(self, home_team: str, away_team: str,
                              league: str, kickoff: str, city: str) -> List[Dict]:
        """
        为指定比赛生成完整的搜索任务清单

        返回：
          [
            {
              "task_id": "01_injuries_home",
              "search_term": "Viking injuries news today 2026-08-09",
              "fallback_term": "Viking 伤停名单 2026年8月9日",
              "layer": 1,
              "category": "injuries",
              "priority": "critical",
              "iron_rules": ["#5", "#19"],
              "target_fields": ["missing_player_name", "position", "reason"]
            },
            ...
          ]
        """
        match_date = kickoff[:10] if kickoff else datetime.now().strftime('%Y-%m-%d')
        match_date_cn = kickoff[:10].replace('-', '年')[2:].replace('-', '月') + '日' if kickoff else ""

        tasks = []
        for t in self.templates:
            template = t.get('search_term_template', t.get('template', ''))
            fallback = t.get('fallback_term_template', '')

            # 替换模板变量
            search_term = template.format(
                home=home_team, away=away_team,
                date=match_date, date_cn=match_date_cn,
                city=city, league=league,
                match_month=datetime.now().strftime('%B'),
                match_year=datetime.now().strftime('%Y')
            )
            fallback_term = fallback.format(
                home=home_team, away=away_team,
                date=match_date, date_cn=match_date_cn,
                city=city, league=league
            ) if fallback else ""

            task = {
                "task_id": f"{t.get('id', len(tasks)+1):02d}_{t.get('category', 'unknown')}",
                "search_term": search_term,
                "fallback_term": fallback_term,
                "layer": t.get('layer', 0),
                "category": t.get('category', ''),
                "priority": t.get('priority', 'medium'),
                "iron_rules": t.get('iron_rules', []),
                "target_fields": t.get('target_data', []) if isinstance(t.get('target_data'), list) else [],
                "notes": t.get('notes', '')
            }
            tasks.append(task)

        log.info(f"  📋 为 [{home_team} vs {away_team}] 生成 {len(tasks)} 个搜索任务")
        return tasks

    def execute_search_task(self, task: Dict) -> Dict:
        """
        执行单个搜索任务（带反限流延迟）

        策略：
        1. 调用前确保距上次调用 >= 0.5s（防Bing限流）
        2. 优先 cn_bing（复用了 _search_bing_cn 的重试机制）
        3. 如果失败，尝试 DuckDuckGo + HTML fallback
        4. 主搜索词失败 → 自动尝试中文fallback搜索词
        """
        search_term = task['search_term']
        fallback_term = task.get('fallback_term', '')

        # 反限流：确保两次调用间隔 >= 最小延迟
        now = time.time()
        elapsed = now - self._last_search_time
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)

        log.info(f"  🔍 搜索 [{task['task_id']}]: {search_term[:60]}...")

        result = {
            "task_id": task['task_id'],
            "search_term": search_term,
            "executed_at": datetime.now().isoformat(),
            "status": "pending",
            "raw_snippets": [],
            "structured_data": {},
            "source_count": 0,
            "confidence": "low",
            "search_engine_used": ""
        }

        # 尝试多个搜索引擎（Bing中国优先，DuckDuckGo/Google被墙）
        search_engines = [
            ("cn_bing", self._search_bing_cn),
            ("duckduckgo", self._search_duckduckgo),
            ("html_duckduckgo", self._search_html_fallback),
        ]

        for engine_name, engine_func in search_engines:
            try:
                log.info(f"    → 尝试 {engine_name}...")
                snippets = engine_func(search_term)

                if snippets and len(snippets) > 0:
                    result['raw_snippets'] = snippets
                    result['source_count'] = len(snippets)
                    result['status'] = 'success'
                    result['search_engine_used'] = engine_name

                    if len(snippets) >= 3:
                        result['confidence'] = 'high'
                    elif len(snippets) >= 1:
                        result['confidence'] = 'medium'

                    log.info(f"    ✅ {engine_name}: 找到 {len(snippets)} 条结果")
                    self._last_search_time = time.time()
                    return result  # 提前返回，跳过后续引擎

                else:
                    log.info(f"    ⚠️ {engine_name}: 无结果，尝试下一个...")

            except Exception as e:
                log.warning(f"    ❌ {engine_name} 异常: {type(e).__name__}: {str(e)[:50]}")
                continue

        # 如果主搜索词失败，尝试 fallback 搜索词
        if result['status'] == 'pending' and fallback_term:
            log.info(f"  🔍 Fallback搜索: {fallback_term[:40]}...")
            for engine_name, engine_func in search_engines:
                try:
                    snippets = engine_func(fallback_term)
                    if snippets and len(snippets) > 0:
                        result['raw_snippets'] = snippets
                        result['source_count'] = len(snippets)
                        result['status'] = 'success (fallback)'
                        result['search_engine_used'] = f"{engine_name}-fallback"
                        result['confidence'] = 'medium' if len(snippets) >= 2 else 'low'
                        log.info(f"    ✅ Fallback ({engine_name}): 找到 {len(snippets)} 条结果")
                        self._last_search_time = time.time()
                        return result
                except:
                    continue

        # 最终状态检查
        if result['status'] == 'pending':
            result['status'] = 'failed'
            result['error'] = '所有搜索引擎均无结果'

        self._last_search_time = time.time()
        return result

    def _search_duckduckgo(self, query: str, max_results: int = 5) -> List[str]:
        """
        使用 DuckDuckGo 即时答案API进行搜索
        无需 API Key，免费使用
        """
        import urllib.parse

        encoded_query = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded_query}&format=json&no_html=1"

        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (FootballDataPipeline/2.0)'
            })
            with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as response:
                data = json.loads(response.read().decode('utf-8'))

                snippets = []

                # 提取 Abstract（主要摘要）
                abstract = data.get('Abstract', '')
                if abstract and len(abstract) > 20:
                    snippets.append(f"[摘要] {abstract}")

                # 提取 RelatedTopics（相关主题）
                for topic in data.get('RelatedTopics', [])[:max_results-1]:
                    text = topic.get('Text', '')
                    if text and len(text) > 15:
                        # 清理 HTML 标签
                        import re
                        clean_text = re.sub(r'<[^>]+>', '', text)
                        snippets.append(clean_text)

                return snippets[:max_results]

        except Exception as e:
            log.debug(f"DuckDuckGo 搜索失败: {e}")
            return []

    def _search_bing_cn(self, query: str, max_results: int = 5) -> List[str]:
        """
        使用 cn.bing.com 在中国大陆进行搜索（带重试和反限流）
        相比 DuckDuckGo/Google，Bing中国版在国内稳定性最好
        """
        import urllib.parse
        import re

        encoded_query = urllib.parse.quote(query)
        url = f"https://cn.bing.com/search?q={encoded_query}"

        for attempt in range(self._max_retries + 1):
            try:
                if attempt > 0:
                    backoff = 1.5 * (2 ** (attempt - 1))  # 1.5s, 3s
                    time.sleep(backoff)
                    log.info(f"    🔄 Bing重试 {attempt}/{self._max_retries}: {query[:40]}...")

                req = urllib.request.Request(url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                })
                with urllib.request.urlopen(req, timeout=15) as response:
                    html = response.read().decode('utf-8', errors='ignore')

                    snippets = []

                    # Bing 结果片段常见模式
                    # Pattern 1: <p class="b_lineclamp\d*">文本</p>
                    snippet_pattern = r'<p\s+class="b_lineclamp\d*"[^>]*>(.*?)</p>'
                    matches = re.findall(snippet_pattern, html, re.DOTALL)

                    for match in matches:
                        # 清理 HTML 实体和标签
                        clean = re.sub(r'<[^>]+>', '', match)  # 去除标签
                        clean = clean.replace('&ensp;', ' ').replace('&nbsp;', ' ')
                        clean = clean.replace('&#0183;', '-').replace('&amp;', '&')
                        clean = re.sub(r'\s+', ' ', clean).strip()
                        if len(clean) > 20:  # 过滤太短的片段
                            snippets.append(clean)

                    # Pattern 2: 如果没找到 b_lineclamp，尝试 b_caption 内的 <p>
                    if not snippets:
                        alt_pattern = r'class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>'
                        alt_matches = re.findall(alt_pattern, html, re.DOTALL)
                        for match in alt_matches:
                            clean = re.sub(r'<[^>]+>', '', match)
                            clean = clean.replace('&ensp;', ' ').replace('&nbsp;', ' ')
                            clean = clean.replace('&#0183;', '-')
                            clean = re.sub(r'\s+', ' ', clean).strip()
                            if len(clean) > 20:
                                snippets.append(clean)

                    # Pattern 3: 通用 li 结果条目
                    if not snippets:
                        li_pattern = r'<li\s+class="b_algo"[^>]*>.*?<a[^>]*>(.*?)</a>.*?<p[^>]*>(.*?)</p>'
                        li_matches = re.findall(li_pattern, html, re.DOTALL | re.IGNORECASE)
                        for title, desc in li_matches:
                            clean = re.sub(r'<[^>]+>', '', desc)
                            clean = clean.replace('&ensp;', ' ').replace('&nbsp;', ' ')
                            clean = re.sub(r'\s+', ' ', clean).strip()
                            if len(clean) > 20:
                                snippets.append(clean)

                    if snippets:
                        return snippets[:max_results]

                    # 有HTML但没有提取到片段 → 可能是验证页面或空结果
                    if len(html) < 500:
                        log.warning(f"    ⚠️ Bing返回内容过短({len(html)}字节)，可能被限流或验证")
                        # 被限流时等待更久再重试
                        if attempt < self._max_retries:
                            time.sleep(3)
                            continue
                    elif '验证' in html or 'captcha' in html.lower():
                        log.warning(f"    ⚠️ Bing触发验证页面，等待重试")
                        if attempt < self._max_retries:
                            time.sleep(5)
                            continue

                    return []

            except urllib.error.HTTPError as e:
                log.warning(f"    ❌ Bing HTTP {e.code}: {query[:40]}...")
                if e.code in (429, 503):  # Rate limit / Service unavailable
                    if attempt < self._max_retries:
                        time.sleep(3)
                        continue
                return []
            except urllib.error.URLError as e:
                log.warning(f"    ❌ Bing连接失败: {str(e)[:60]}")
                if attempt < self._max_retries:
                    continue
                return []
            except Exception as e:
                log.warning(f"    ❌ Bing搜索异常: {type(e).__name__}: {str(e)[:60]}")
                if attempt < self._max_retries:
                    continue
                return []

        return []

    def _search_html_fallback(self, query: str, max_results: int = 5) -> List[str]:
        """
        降级方案：使用 HTML 解析方式获取搜索结果
        当 API 方式失败时启用
        """
        import urllib.parse

        encoded_query = urllib.parse.quote(query)

        # 使用 DuckDuckGo HTML 版本（比 Google 更容易解析）
        url = f"https://html.duckduckgo.com/html/?q={encoded_query}"

        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as response:
                html = response.read().decode('utf-8', errors='ignore')

                import re
                snippets = []

                # 提取结果片段（DuckDuckGo HTML 格式）
                # 匹配 <a class="result__snippet">...</a> 标签
                snippet_pattern = r'class="result__snippet"[^>]*>([^<]+)</a>'
                matches = re.findall(snippet_pattern, html, re.IGNORECASE)

                for match in matches[:max_results]:
                    clean = match.strip()
                    if len(clean) > 20:  # 过滤太短的结果
                        snippets.append(clean)

                # 如果没找到 snippet，尝试提取标题
                if not snippets:
                    title_pattern = r'class="result__title"[^>]*><a[^>]*class="result__a"[^>]*>([^<]+)<'
                    title_matches = re.findall(title_pattern, html, re.IGNORECASE)
                    for match in title_matches[:max_results]:
                        clean = match.strip()
                        if clean:
                            snippets.append(f"[标题] {clean}")

                return snippets

        except Exception as e:
            log.debug(f"HTML 降级搜索失败: {e}")
            return []

    def execute_round(self, round_id: int, all_tasks: List[Dict]) -> Dict[int, Dict]:
        """
        执行某一轮次的所有搜索任务

        round_id: 1 (T-12h), 2 (T-6h), 3 (T-3h)
        """
        strategy = self.execution_strategy
        rounds_config = strategy.get('rounds', [])

        # 找到当前轮次应该执行的模板ID列表
        target_template_ids = []
        for rc in rounds_config:
            if rc.get('round_id') == round_id:
                target_template_ids = rc.get('templates', [])
                break

        if not target_template_ids:
            # 如果没有配置轮次，默认全部执行
            target_template_ids = [t.get('id', i+1) for i, t in enumerate(self.templates)]

        # 过滤出当前轮次的任务
        round_tasks = [t for t in all_tasks if any(
            str(t['task_id'].split('_')[0]) == str(tid) for tid in target_template_ids
        )]

        log.info(f"\n{'='*50}")
        log.info(f"🔍 Round {round_id}: 执行 {len(round_tasks)} 个搜索任务")
        log.info(f"{'='*50}")

        results = {}
        for task in round_tasks:
            task_num = int(task['task_id'].split('_')[0])
            result = self.execute_search_task(task)
            results[task_num] = result
            rate_limit(2.0)  # 搜索间隔2秒，避免被限流

        success_count = sum(1 for r in results.values() if r['status'] == 'success')
        log.info(f"  ✅ Round {round_id} 完成: {success_count}/{len(round_tasks)} 成功")

        return results


# ============================================
# PFI 疲劳度检测引擎 (保持不变)
# ============================================

class PFIEngine:
    """PFI (Physical Fatigue Index) 疲劳度检测引擎"""

    @staticmethod
    def analyze(fixtures_history: List[Dict], target_date: str) -> PFIData:
        pfi = PFIData()
        pfi.last_match_date = ""

        if not fixtures_history:
            pfi.level = "none"
            pfi.rest_days = 99
            return pfi

        target_dt = datetime.fromisoformat(target_date.replace('Z', '+00:00'))
        last_match = None

        for fixture in fixtures_history:
            match_date = fixture.get('date', '')[:10] or fixture.get('utcDate', '')[:10]
            try:
                match_dt = datetime.fromisoformat(match_date)
                if match_dt < target_dt:
                    if last_match is None or match_dt > datetime.fromisoformat(last_match.get('date', '')[:10] or last_match.get('utcDate', '')[:10]):
                        last_match = fixture
            except:
                pass

        if not last_match:
            pfi.level = "none"
            pfi.rest_days = 99
            return pfi

        last_date = last_match.get('date', '')[:10] or last_match.get('utcDate', '')[:10]
        pfi.last_match_date = last_date
        try:
            last_dt = datetime.fromisoformat(last_date)
            delta = target_dt - last_dt
            pfi.rest_days = max(0, delta.days)
        except:
            pfi.rest_days = 99

        comp_name = (last_match.get('competition', {}) or {}).get('name', '') or ''
        if any(kw in comp_name.lower() for kw in ['champions', 'ucl']):
            pfi.last_competition = "UCL"
        elif any(kw in comp_name.lower() for kw in ['europa', 'uel', 'conference']):
            pfi.last_competition = "UEL"
        elif any(kw in comp_name.lower() for kw in ['cup', 'pokal', 'copa']):
            pfi.last_competition = "CUP"
        else:
            pfi.last_competition = "League"

        home_team_id = (last_match.get('homeTeam', {}) or {}).get('id', 0)
        away_team_id = (last_match.get('awayTeam', {}) or {}).get('id', 0)
        # 简化判断（实际需要更复杂的逻辑）
        pfi.last_match_venue = "home"  # 默认

        for fixture in fixtures_history:
            match_date = fixture.get('date', '')[:10] or fixture.get('utcDate', '')[:10]
            try:
                match_dt = datetime.fromisoformat(match_date)
                days_diff = (target_dt - match_dt).days
                if 0 < days_diff <= 7:
                    comp = (fixture.get('competition', {}) or {}).get('name', '') or ''
                    if any(kw in comp.lower() for kw in ['champions', 'europa', 'cup']):
                        pfi.extra_match_in_7d = True
                        break
            except:
                pass

        triggers = 0
        if pfi.extra_match_in_7d:
            triggers += 1
        if pfi.rest_days <= 4:
            triggers += 1
        if pfi.last_competition in ["UCL", "UEL"]:
            triggers += 1
        if pfi.last_match_venue == "away":
            triggers += 1

        if triggers >= 4:
            pfi.level = "critical"
        elif triggers >= 3:
            pfi.level = "high"
        elif triggers >= 2:
            pfi.level = "medium"
        elif triggers >= 1:
            pfi.level = "low"
        else:
            pfi.level = "none"

        log.info(f"  🔋 PFI [{pfi.level.upper()}]: 休息{pfi.rest_days}天, 上场{pfi.last_competition}, 触发项{triggers}/4")

        return pfi


# ============================================
# 主聚合逻辑 (v2 重构：双引擎模式)
# ============================================

class DataAggregator:
    """
    数据聚合器 v2 - 双引擎混合架构

    数据采集策略：
    ┌────────────────┐     ┌─────────────────┐
    │  引擎A: API     │     │  引擎B: WebSearch│
    │  -The Odds API  │     │  -14词模板       │
    │  -football-data │     │  -结构化降级     │
    │  -Open-Meteo    │     │                 │
    └───────┬────────┘     └────────┬────────┘
            │                       │
            ▼                       ▼
    ┌──────────────────────────────────────┐
    │         MatchData (标准化JSON)        │
    │  6层SOP → 质量评估 → cache/ 输出      │
    └──────────────────────────────────────┘
    """

    def __init__(self, force_websearch: bool = False):
        self.odds_client = OddsAPIClient(ODDS_API_KEY)
        self.fd_client = FootballDataClient(FOOTBALL_DATA_TOKEN)
        self.weather_client = WeatherClient()
        self.pfi_engine = PFIEngine()
        self.websearch_engine = WebSearchIntelligence()
        self.force_websearch = force_websearch

        # 联赛映射 (key统一为小写，支持多种别称)
        self.league_map = {
            # 德乙 (2. Bundesliga)
            "2. bundesliga": {"sport_key": "soccer_germany_bundesliga2", "fd_code": "BL2"},
            "bundesliga 2": {"sport_key": "soccer_germany_bundesliga2", "fd_code": "BL2"},
            "德乙": {"sport_key": "soccer_germany_bundesliga2", "fd_code": "BL2"},
            "德国乙级联赛": {"sport_key": "soccer_germany_bundesliga2", "fd_code": "BL2"},
            # 德甲 (Bundesliga)
            "bundesliga": {"sport_key": "soccer_germany_bundesliga", "fd_code": "BL1"},
            "德甲": {"sport_key": "soccer_germany_bundesliga", "fd_code": "BL1"},
            # 日职联 (⚠️ Odds API key: soccer_japan_j_league, 不是 j1_league)
            "j1 league": {"sport_key": "soccer_japan_j_league", "fd_code": None},
            "j1": {"sport_key": "soccer_japan_j_league", "fd_code": None},
            "日职联": {"sport_key": "soccer_japan_j_league", "fd_code": None},
            "日职": {"sport_key": "soccer_japan_j_league", "fd_code": None},
            "j league": {"sport_key": "soccer_japan_j_league", "fd_code": None},
            # 日职乙 (Odds API 可能不支持，保留原 key)
            "j2 league": {"sport_key": "soccer_japan_j_league", "fd_code": None},  # 降级到J League一起查
            "j2": {"sport_key": "soccer_japan_j_league", "fd_code": None},
            "日职乙": {"sport_key": "soccer_japan_j_league", "fd_code": None},
            # 瑞超
            "allsvenskan": {"sport_key": "soccer_sweden_allsvenskan", "fd_code": None},
            "瑞典超": {"sport_key": "soccer_sweden_allsvenskan", "fd_code": None},
            "瑞超": {"sport_key": "soccer_sweden_allsvenskan", "fd_code": None},
            "swedish allsvenskan": {"sport_key": "soccer_sweden_allsvenskan", "fd_code": None},
            # 挪超
            "eliteserien": {"sport_key": "soccer_norway_eliteserien", "fd_code": None},
            "挪超": {"sport_key": "soccer_norway_eliteserien", "fd_code": None},
            "norwegian eliteserien": {"sport_key": "soccer_norway_eliteserien", "fd_code": None},
            # 葡超 (⚠️ Odds API key: soccer_portugal_primeira_liga)
            "liga portugal": {"sport_key": "soccer_portugal_primeira_liga", "fd_code": "PPL"},
            "primeira liga": {"sport_key": "soccer_portugal_primeira_liga", "fd_code": "PPL"},
            "葡超": {"sport_key": "soccer_portugal_primeira_liga", "fd_code": "PPL"},
            "葡萄牙超级联赛": {"sport_key": "soccer_portugal_primeira_liga", "fd_code": "PPL"},
            # 韩职 (⚠️ Odds API key: soccer_korea_kleague1)
            "k league": {"sport_key": "soccer_korea_kleague1", "fd_code": None},
            "k league 1": {"sport_key": "soccer_korea_kleague1", "fd_code": None},
            "韩职": {"sport_key": "soccer_korea_kleague1", "fd_code": None},
            "k联赛": {"sport_key": "soccer_korea_kleague1", "fd_code": None},
            # 英超
            "premier league": {"sport_key": "soccer_england_premier_league", "fd_code": "PL"},
            "英超": {"sport_key": "soccer_england_premier_league", "fd_code": "PL"},
            # 荷甲
            "eredivisie": {"sport_key": "soccer_netherlands_eredivisie", "fd_code": "ED"},
            "荷甲": {"sport_key": "soccer_netherlands_eredivisie", "fd_code": "ED"},
            "荷兰甲级联赛": {"sport_key": "soccer_netherlands_eredivisie", "fd_code": "ED"},
            # 法甲
            "ligue 1": {"sport_key": "soccer_france_ligue_1", "fd_code": "FL1"},
            "法甲": {"sport_key": "soccer_france_ligue_1", "fd_code": "FL1"},
            # 意甲
            "serie a": {"sport_key": "soccer_italy_serie_a", "fd_code": "SA"},
            "意甲": {"sport_key": "soccer_italy_serie_a", "fd_code": "SA"},
            # 西甲
            "la liga": {"sport_key": "soccer_spain_la_liga", "fd_code": "PD"},
            "西甲": {"sport_key": "soccer_spain_la_liga", "fd_code": "PD"},
            # 芬超
            "veikkausliiga": {"sport_key": "soccer_finland_veikkausliiga", "fd_code": None},
            "芬超": {"sport_key": "soccer_finland_veikkausliiga", "fd_code": None},
            "芬兰超级联赛": {"sport_key": "soccer_finland_veikkausliiga", "fd_code": None},
            # 巴甲
            "serie a brasileiro": {"sport_key": "soccer_brazil_serie_a", "fd_code": None},
            "brasileiro": {"sport_key": "soccer_brazil_serie_a", "fd_code": None},
            "巴甲": {"sport_key": "soccer_brazil_serie_a", "fd_code": None},
            "巴西甲级联赛": {"sport_key": "soccer_brazil_serie_a", "fd_code": None},
            # 日职联补充
            "japan j1": {"sport_key": "soccer_japan_j_league", "fd_code": None},
            # 英冠 (⚠️ Odds API key: soccer_efl_champ)
            "championship": {"sport_key": "soccer_efl_champ", "fd_code": "ELC"},
            "英冠": {"sport_key": "soccer_efl_champ", "fd_code": "ELC"},
            # 澳超 (⚠️ Odds API 不支持澳超，无法获取赔率)
            "a-league": {"sport_key": "", "fd_code": None},  # API不可用
            "a league": {"sport_key": "", "fd_code": None},
            "澳超": {"sport_key": "", "fd_code": None},
        }

        # 中文队名 → 英文标准名映射（用于 The Odds API 赔率匹配）
        self.team_name_map = {
            # 日职联
            "东京绿茵": "Tokyo Verdy", "川崎前锋": "Kawasaki Frontale",
            "长崎航海": "Nagasaki", "京都不死鸟": "Kyoto",
            # 日职乙
            "山形山神": "Montedio Yamagata", "枥木城": "Tochigi",
            # 荷甲
            "鹿特丹斯巴达": "Sparta", "费耶诺德": "Feyenoord",
            "兹沃勒": "Zwolle", "阿贾克斯": "Ajax",
            "格罗宁根": "Groningen", "乌德勒支": "Utrecht",
            "海伦芬": "Heerenveen", "特温特": "Twente",
            # 德乙
            "圣保利": "St Pauli", "菲尔特": "Furth",
            "纽伦堡": "Nurnberg", "德累斯顿": "Dresden",
            # 瑞典超
            "哈马比": "Hammarby", "赫根": "Hacken",
            "哈尔姆斯塔德": "Halmstad", "哥德堡盖斯": "GAIS",
            "IFK哥德堡": "IFK Goteborg", "卡尔马": "Kalmar",
            "马尔默": "Malmo", "代格福什": "Degerfors",
            "天狼星": "Sirius", "布洛马波卡纳": "Brommapojkarna",
            "米亚尔比": "Mjallby", "埃尔夫斯堡": "Elfsborg",
            "奥尔格里特": "Orgryte", "索尔纳": "AIK",
            "瓦斯特拉斯": "Vasteras", "尤尔加登": "Djurgarden",
            # 芬超
            "库奥皮奥": "KuPS", "TPS图尔": "TPS",
            "AC奥卢": "AC Oulu", "赫尔辛基": "HJK",
            # 挪超
            "汉坎": "HamKam", "奥勒松": "Aalesund",
            "克里斯蒂安松": "Kristiansund", "莫尔德": "Molde",
            # 葡超
            "波尔图": "Porto", "阿尔维卡": "Alverca",
            "本菲卡": "Benfica", "维塞乌": "Viseu",
            "吉维森特": "Gil Vicente", "里奥阿维": "Rio Ave",
            "摩雷伦斯": "Moreirense", "布拉加": "Braga",
            # 英冠/友谊赛
            "诺丁汉森林": "Nottingham Forest", "富勒姆": "Fulham",
            # 澳超
            "墨尔本胜利": "Melbourne Victory", "麦克阿瑟FC": "Macarthur",
        }

    def aggregate_match(self, home_name: str, away_name: str, league: str = "",
                        kickoff: str = "", city: str = "") -> MatchData:
        """
        聚集单场比赛的全部数据 (v2 双引擎模式)
        """
        log.info(f"\n{'='*60}")
        log.info(f"⚽ 开始聚集: {home_name} vs {away_name}")
        log.info(f"   模式: {'强制WebSearch' if self.force_websearch else '双引擎自动'}")
        log.info(f"{'='*60}")

        match = MatchData(
            match_id=f"{home_name}_{away_name}_{datetime.now().strftime('%Y%m%d_%H%M')}".lower().replace(' ', '_'),
            league=league,
            kickoff_time=kickoff or datetime.now().isoformat(),
            city=city,
            collected_at=datetime.now().isoformat(),
            data_sources=[]
        )

        # ================================================================
        # Layer 1: 球队基础数据 + 伤停名单
        #   优先级: WebSearch > API-Football(不可用) > football-data(有限)
        # ================================================================
        log.info("\n📋 Layer 1/6: 球队基础数据 + 伤停名单")

        if self.force_websearch or not self._has_api_football():
            # 使用 WebSearch 收集伤停/阵容信息
            log.info("  → 使用 WebSearch 引擎收集伤停/阵容数据")
            tasks = self.websearch_engine.generate_search_tasks(
                home_name, away_name, league, kickoff, city
            )
            # 只执行 Layer 1 相关的搜索任务 (templates 1-4)
            layer1_tasks = [t for t in tasks if t['layer'] == 1]
            layer1_results = {}
            for task in layer1_tasks:
                task_num = int(task['task_id'].split('_')[0])
                result = self.websearch_engine.execute_search_task(task)
                layer1_results[task_num] = result

            # 从搜索结果中提取伤停信息（这里需要后续对接真实WebSearch后的解析逻辑）
            match.websearch_results["layer1"] = layer1_results
            match.data_sources.append("WebSearch:L1-injuries-lineup")

        else:
            log.info("  ⚠️ API-Football 未集成，降级到 WebSearch")
            match.data_sources.append("WebSearch:L1-fallback")

        # ================================================================
        # Layer 2: H2H 历史交锋
        #   优先级: WebSearch > API-Football
        # ================================================================
        log.info("\n⚔️ Layer 2/6: H2H历史交锋")

        if self.force_websearch or not self._has_api_football():
            tasks = self.websearch_engine.generate_search_tasks(home_name, away_name, league, kickoff, city)
            layer2_tasks = [t for t in tasks if t['layer'] == 2]
            layer2_results = {}
            for task in layer2_tasks:
                task_num = int(task['task_id'].split('_')[0])
                result = self.websearch_engine.execute_search_task(task)
                layer2_results[task_num] = result

            match.websearch_results["layer2"] = layer2_results
            match.data_sources.append("WebSearch:L2-H2H")

        # ================================================================
        # Layer 3: 赔率数据 (The Odds API — 这是强项！)
        #   优先级: The Odds API (已有Key) > WebSearch
        # ================================================================
        log.info("\n💰 Layer 3/6: 赔率 + 亚盘变动检测")

        sport_key = self.league_map.get(league.lower(), {}).get('sport_key', '')
        if sport_key and self.odds_client.enabled:
            log.info("  → 使用 The Odds API (已验证可用)")
            matches = self.odds_client.search_matches(sport_key, days_from_now=3)
            for m in matches:
                # API v4: home_team/away_team 可能是 string (如 "1. FC Nürnberg") 或 dict (旧格式)
                home = m.get('home_team', '')
                away = m.get('away_team', '')
                home = home.get('name', home) if isinstance(home, dict) else home
                away = away.get('name', away) if isinstance(away, dict) else away
                # 使用 unicode 规整后的名称进行匹配（解决 umlaut 问题）
                # ⚠️ 先翻译中文队名为英文，否则 non-ASCII 字符会被 normalize_name 吞掉
                translated_home = self.team_name_map.get(home_name, home_name)
                translated_away = self.team_name_map.get(away_name, away_name)
                home_norm = normalize_name(home)
                away_norm = normalize_name(away)
                our_home_norm = normalize_name(translated_home)
                our_away_norm = normalize_name(translated_away)
                # ⚠️ 空字符串匹配任何内容——必须防止 normalize 吞噬中文后误匹配
                if not our_home_norm or not our_away_norm:
                    continue
                # 双向子串匹配：如 "nagasaki" in "varen nagasaki" 和 "kyoto" in "kyoto sanga"
                home_match = our_home_norm in home_norm or home_norm in our_home_norm
                away_match = our_away_norm in away_norm or away_norm in our_away_norm
                if home_match and away_match:
                    log.info(f"    🎯 赔率匹配: {home} vs {away}")
                    match.odds = self.odds_client.get_odds_for_match(sport_key, m.get('id', ''))
                    # 如果 get_odds_for_match 返回空（赛事已结束等），尝试从 m 直接获取
                    if not match.odds.home_win:
                        # 从搜索结果的第一个 bookmaker 获取赔率
                        for bm in m.get('bookmakers', [])[:1]:
                            for mk in bm.get('markets', []):
                                if mk.get('key') == 'h2h':
                                    outcomes = mk.get('outcomes', [])
                                    if len(outcomes) >= 3:
                                        match.odds.home_win = outcomes[0].get('price', 0)
                                        match.odds.away_win = outcomes[1].get('price', 0)
                                        match.odds.draw = outcomes[2].get('price', 0)
                    break

            if match.odds.home_win:
                match.data_sources.append(f"TheOddsAPI:{','.join(match.odds.sources[:3])}")
                if match.odds.asian_change_detected:
                    log.warning(f"  ⚠️ 亚盘异动！变化{match.odds.asian_change}球")
        else:
            # 降级到 WebSearch 收集赔率
            log.info("  → The Odds API 不可用，降级到 WebSearch 收集赔率")
            tasks = self.websearch_engine.generate_search_tasks(home_name, away_name, league, kickoff, city)
            layer3_tasks = [t for t in tasks if t['layer'] == 3]
            layer3_results = {}
            for task in layer3_tasks:
                task_num = int(task['task_id'].split('_')[0])
                result = self.websearch_engine.execute_search_task(task)
                layer3_results[task_num] = result

            match.websearch_results["layer3"] = layer3_results
            match.data_sources.append("WebSearch:L3-odds-fallback")

        # ================================================================
        # Layer 4: PFI 疲劳度检测
        #   优先级: football-data fixtures > WebSearch
        # ================================================================
        log.info("\n🔋 Layer 4/6: PFI疲劳度检测")

        # 尝试使用 football-data.org 获取赛程（如果有token）
        pfi_fixtures_home = []
        pfi_fixtures_away = []

        if self.fd_client.enabled and match.home_team.id:
            pfi_fixtures_home = self.fd_client.get_team_matches(match.home_team.id, days=30)
            match.data_sources.append("Football-data:PFI")

        if self.fd_client.enabled and match.away_team.id:
            pfi_fixtures_away = self.fd_client.get_team_matches(match.away_team.id, days=30)

        # 如果没有 football-data，用 WebSearch 补充
        if not pfi_fixtures_home and not self.force_websearch:
            tasks = self.websearch_engine.generate_search_tasks(home_name, away_name, league, kickoff, city)
            layer4_tasks = [t for t in tasks if t['layer'] == 4]
            layer4_results = {}
            for task in layer4_tasks:
                task_num = int(task['task_id'].split('_')[0])
                result = self.websearch_engine.execute_search_task(task)
                layer4_results[task_num] = result
            match.websearch_results["layer4"] = layer4_results
            match.data_sources.append("WebSearch:L4-PFI")

        # 计算PFI（即使数据为空也运行，得到 baseline）
        match.pfi_home = self.pfi_engine.analyze(pfi_fixtures_home, match.kickoff_time)
        match.pfi_away = self.pfi_engine.analyze(pfi_fixtures_away, match.kickoff_time)

        if match.pfi_home.level != "none" or match.pfi_away.level != "none":
            if "PFI:Engine" not in match.data_sources:
                match.data_sources.append("PFI:Engine")

        # ================================================================
        # Layer 5: 天气条件
        #   优先级: Open-Meteo (免费无限额) > WebSearch
        # ================================================================
        log.info("\n🌤️ Layer 5/6: 天气条件")

        if city:
            match.weather = self.weather_client.get_weather(city, match.kickoff_time[:10] if match.kickoff_time else "")
            if match.weather:
                match.latitude = match.weather.get('latitude', 0)
                match.longitude = match.weather.get('longitude', 0)
                match.data_sources.append("Open-Meteo")
        else:
            # 降级到 WebSearch
            tasks = self.websearch_engine.generate_search_tasks(home_name, away_name, league, kickoff, city)
            layer5_tasks = [t for t in tasks if t['layer'] == 5]
            if layer5_tasks:
                result = self.websearch_engine.execute_search_task(layer5_tasks[0])
                match.websearch_results["layer5"] = {5: result}
                match.data_sources.append("WebSearch:L5-weather")

        # ================================================================
        # Layer 6: 新闻动因 + 首发曝光
        #   仅 WebSearch 可提供
        # ================================================================
        log.info("\n📰 Layer 6/6: 新闻动因 + 首发曝光")

        tasks = self.websearch_engine.generate_search_tasks(home_name, away_name, league, kickoff, city)
        layer6_tasks = [t for t in tasks if t['layer'] == 6]
        layer6_results = {}
        for task in layer6_tasks:
            task_num = int(task['task_id'].split('_')[0])
            result = self.websearch_engine.execute_search_task(task)
            layer6_results[task_num] = result

        match.websearch_results["layer6"] = layer6_results
        if layer6_results:
            match.data_sources.append("WebSearch:L6-news-lineup")

        # ================================================================
        # 最终：数据质量评估 + 分级标签
        # ================================================================
        log.info("\n✅ Layer 6/6: 数据质量评估")

        # 计算各维度数据覆盖
        ws_tasks_total = 0
        ws_tasks_success = 0
        for layer_name, layer_data in match.websearch_results.items():
            if isinstance(layer_data, dict):
                for task_id, task_result in layer_data.items():
                    if isinstance(task_result, dict):
                        ws_tasks_total += 1
                        if task_result.get('status', '') in ('success', 'success (fallback)'):
                            ws_tasks_success += 1

        has_odds = match.odds.home_win > 0
        has_intel = ws_tasks_success >= 4  # 至少4个WebSearch任务成功
        has_full_intel = ws_tasks_success >= 8  # 8+成功=完整情报
        ws_pct = round(ws_tasks_success / ws_tasks_total * 100, 1) if ws_tasks_total > 0 else 0

        source_count = len(match.data_sources)

        # 数据质量分级 (AAA → C)
        if has_full_intel and has_odds:
            match.confidence = "high"
            match.data_quality_tier = "🟢 AAA"
        elif has_intel and has_odds:
            match.confidence = "high"
            match.data_quality_tier = "🟢 AA"
        elif has_intel:
            match.confidence = "medium"
            match.data_quality_tier = "🟡 A"
        elif has_odds:
            match.confidence = "medium"
            match.data_quality_tier = "🟠 B"
        elif source_count >= 3:  # 有批采数据
            match.confidence = "medium"
            match.data_quality_tier = "🟡 A"
        else:
            match.confidence = "low"
            match.data_quality_tier = "⚪ C"

        # 存储质量元数据
        match._quality_meta = {
            "ws_success_rate": ws_pct,
            "ws_success_count": ws_tasks_success,
            "ws_total_count": ws_tasks_total,
            "has_realtime_odds": has_odds,
            "has_full_intel": has_full_intel,
            "max_analysis_depth": "full" if has_full_intel else ("odds_only" if has_odds else "basic"),
        }

        # 输出汇总
        log.info(f"\n📊 聚集完成: {home_name} vs {away_name}")
        log.info(f"   数据质量: {match.data_quality_tier} | WS成功率{ws_pct}%({ws_tasks_success}/{ws_tasks_total}) | 赔率:{'✅' if has_odds else '❌'}")
        log.info(f"   SPF欧赔: 主{match.odds.home_win:.2f} / 平{match.odds.draw:.2f} / 客{match.odds.away_win:.2f}")
        asian_info = f"亚盘: 初盘{match.odds.asian_opening} → 临盘{match.odds.asian_current}"
        if match.odds.asian_change_detected:
            asian_info += f" ⚠️ 变动{match.odds.asian_change}球!"
        log.info(f"   {asian_info}")
        log.info(f"   PFI: 主队[{match.pfi_home.level.upper()}] / 客队[{match.pfi_away.level.upper()}]")
        log.info(f"   伤停: 主{len(match.home_team.missing_players)}人 / 客{len(match.away_team.missing_players)}人")
        log.info(f"   H2H: {len(match.h2h_last10)}场记录")
        log.info(f"   WebSearch任务: {ws_tasks_total}个 ({ws_tasks_success}成功)")

        return match

    def _has_api_football(self) -> bool:
        """检查是否有可用的 API-Football (RapidAPI) Key"""
        # v2 中默认为 False，因为用户注册受阻
        return False

    def save_match(self, match: MatchData):
        """保存比赛数据到本地JSON缓存"""
        filename = f"{match.match_id}.json"
        filepath = CACHE_DIR / filename

        data = asdict(match)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

        log.info(f"💾 已保存: {filepath}")
        return filepath


# ============================================
# CLI 入口 (更新版本号和帮助信息)
# ============================================

def parse_match_input(input_str: str) -> List[tuple]:
    """解析用户输入的比赛列表"""
    matches = []
    separators = [',', ';', '|', '\n']

    parts = [input_str]
    for sep in separators:
        new_parts = []
        for p in parts:
            new_parts.extend(p.split(sep))
        parts = new_parts

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if ' vs ' in part.lower() or ' v ' in part or ' vs. ' in part:
            for sep in [' vs ', ' VS ', ' v ', ' V ', ' vs. ', ' VS. ']:
                if sep in part:
                    teams = part.split(sep, 1)
                    if len(teams) == 2:
                        matches.append((teams[0].strip(), teams[1].strip()))
                        break

    return matches


def main():
    parser = argparse.ArgumentParser(
        description='足球数据聚合器 v2.0 (双引擎混合架构)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
架构说明:
  引擎A (API直接调用):
    The Odds API       → 赔率/亚盘变动 ✅
    football-data.org  → 积分/赛程(大联赛) 🔄 待配置
    Open-Meteo         → 天气 ✅

  引擎B (WebSearch结构化降级):
    14词情报模板 → 伤停/H2H/首发/PFI/新闻
    基于 维京2-1 / 博德1-2 100%命中验证

示例用法:
  python main.py --matches "Viking vs Sarpsborg,Bodoe Glimt vs Valerenga"
  python main.py --matches "本菲卡 vs 维塞乌" --league "Liga Portugal" --city Lisbon
  python main.py --websearch-only --matches "Viking vs Sarpsborg"  (强制WebSearch模式)
  python main.py --file my_matches.txt
        """
    )
    parser.add_argument('--matches', '-m', type=str,
                        help='比赛列表，逗号分隔。格式: "主队 vs 客队, 主队2 vs 客队2"')
    parser.add_argument('--league', '-l', type=str, default='',
                        help='联赛名称（可选，帮助API选择正确的联赛）')
    parser.add_argument('--city', '-c', type=str, default='',
                        help='比赛城市（用于天气查询）')
    parser.add_argument('--file', '-f', type=str,
                        help='从文件读取比赛列表（每行一场）')
    parser.add_argument('--days', '-d', type=int, default=3,
                        help='查询未来N天的比赛（配合--league使用）')
    parser.add_argument('--all', action='store_true',
                        help='自动抓取所有联赛未来48h内的比赛')
    parser.add_argument('--websearch-only', action='store_true',
                        help='强制使用WebSearch降级模式（跳过所有API调用）')
    parser.add_argument('--output', '-o', type=str,
                        help='输出文件路径（默认保存到cache/目录）')

    args = parser.parse_args()

    log.info("=" * 60)
    log.info("🚀 足球数据聚合器 v2.0 启动 (双引擎混合架构)")
    log.info(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info("=" * 60)

    # 检查API Key状态
    log.info("\n📡 API连接状态:")
    log.info(f"   The Odds API:     {'✅ 已配置' if ODDS_API_KEY else '❌ 未配置'}")
    log.info(f"   football-data.org: {'✅ 已配置' if FOOTBALL_DATA_TOKEN else '🔄 未配置 (可选)'}")
    log.info(f"   Open-Meteo:       ✅ 无需配置（免费无限额）")
    log.info(f"   WebSearch引擎:    ✅ 已加载 {len(WebSearchIntelligence().templates)} 个模板")
    log.info(f"   强制WebSearch模式: {'是' if args.websearch_only else '否 (自动选择)'}")

    aggregator = DataAggregator(force_websearch=args.websearch_only)
    results = []

    # 方式1：直接指定比赛
    if args.matches:
        match_list = parse_match_input(args.matches)
        for home, away in match_list:
            match = aggregator.aggregate_match(
                home_name=home,
                away_name=away,
                league=args.league,
                city=args.city
            )
            aggregator.save_match(match)
            results.append(match)

    # 方式2：从文件读取
    elif args.file:
        filepath = Path(args.file)
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            match_list = parse_match_input(content)
            for home, away in match_list:
                match = aggregator.aggregate_match(home, away, args.league, args.city)
                aggregator.save_match(match)
                results.append(match)
        else:
            log.error(f"❌ 文件不存在: {filepath}")

    # 方式3：按联赛批量抓取
    elif args.league:
        log.info(f"\n📅 抓取联赛: {args.league} (未来{args.days}天)")
        log.warning("⚠️ 按联赛批量抓取功能开发中...")

    # 方式4：全部自动
    elif args.all:
        log.info("\n🔄 自动模式: 抓取所有活跃联赛...")
        log.warning("⚠️ 全自动模式开发中...")

    else:
        parser.print_help()
        log.error("\n❌ 请指定至少一种输入方式 (--matches / --file / --league / --all)")
        sys.exit(1)

    # 输出汇总
    log.info("\n" + "=" * 60)
    log.info(f"📊 聚合完成! 共处理 {len(results)} 场比赛")
    log.info("=" * 60)

    if results:
        high_conf = sum(1 for r in results if r.confidence == "high")
        med_conf = sum(1 for r in results if r.confidence == "medium")
        low_conf = sum(1 for r in results if r.confidence == "low")
        log.info(f"   高置信度: {high_conf}场 | 中等: {med_conf}场 | 低: {low_conf}场")

        # 输出索引文件
        index_file = CACHE_DIR / f"index_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        index_data = {
            "generated_at": datetime.now().isoformat(),
            "version": "v2.0-hybrid",
            "engine_mode": "websearch-only" if args.websearch_only else "dual-engine",
            "total_matches": len(results),
            "matches": [
                {
                    "match_id": m.match_id,
                    "home": m.home_team.name,
                    "away": m.away_team.name,
                    "league": m.league,
                    "kickoff": m.kickoff_time,
                    "confidence": m.confidence,
                    "odds_home": m.odds.home_win,
                    "asian_change_detected": m.odds.asian_change_detected,
                    "pfi_home_level": m.pfi_home.level,
                    "pfi_away_level": m.pfi_away.level,
                    "injuries_home": len(m.home_team.missing_players),
                    "injuries_away": len(m.away_team.missing_players),
                    "h2h_records": len(m.h2h_last10),
                    "data_sources": m.data_sources,
                    "websearch_tasks_completed": sum(len(v) for v in m.websearch_results.values()),
                    "cache_file": f"{m.match_id}.json"
                }
                for m in results
            ]
        }
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)
        log.info(f"📑 索引文件: {index_file}")

    log.info("\n✨ 下一步: 铁律分析引擎读取 cache/*.json 文件进行预测")


if __name__ == '__main__':
    main()
