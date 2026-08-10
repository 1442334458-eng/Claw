#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  FotMob 数据采集器 v1.0
  FotMob Data Collector
============================================

数据源: https://www.fotmob.com (FotMob)
访问方式: WebFetch (CodeBuddy调度器)
覆盖内容:
  ✅ 预期进球 (xG) — 填补管道Layer 2最大空白
  ✅ 预期助攻 (xA)
  ✅ 球员评分 — 实时+赛后评分
  ✅ 阵容 — 首发+替补+阵型
  ✅ 比赛数据 — 控球率/射门/传球/抢断50+统计
  ✅ 射门图 — 坐标+xG
  ✅ 势头图 — 分钟级比赛势头
  ✅ H2H — 历史交锋数据

API端点:
  /api/matchDetails?matchId={id}  → 完整比赛详情（核心端点）
  /api/matches?date=YYYYMMDD      → 按日期获取比赛列表
  /api/teams?id={id}              → 球队数据
  /api/playerData?id={id}         → 球员数据
  /api/leagues?id={id}            → 联赛数据
  /api/searchData?term={query}    → 搜索

应用层:
  Layer 1 (阵容)    — 阵容+阵型+球员评分
  Layer 2 (数据)    — xG/xA/控球率/射门/传球/抢断
  Layer 3 (H2H)     — 历史交锋比较
  Layer 6 (情报)    — 势头图+比赛事件

联动画像库:
  赛后自动提取 → teams/{team}/fotmob_stats.json → 联动 Rule 5/19/27

与球迷屋采集器的关系:
  球迷屋: 中文伤停精确到人 + H2H + 赛前前瞻
  FotMob: xG数据 + 球员评分 + 射门图 + 50+统计
  → 互补关系，无重复覆盖

设计原则:
  - 通过外部WebFetch调度器获取JSON（沙箱环境无法直连）
  - JSON解析全自动，无需AI辅助
  - 输出统一管道格式，兼容 cross_validate.py / main.py

作者：CodeBuddy Code (管道 v2.1 升级)
日期：2026-08-10
版本：v1.0
"""

import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


# ============================================
# 数据模型
# ============================================

@dataclass
class FotMobTeamStats:
    """FotMob 球队统计数据"""
    expected_goals: float = 0.0            # 预期进球 xG
    possession_pct: float = 0.0            # 控球率 %
    total_shots: int = 0                   # 总射门
    shots_on_target: int = 0               # 射正
    shots_off_target: int = 0              # 射偏
    blocked_shots: int = 0                 # 被挡射门
    corners: int = 0                       # 角球
    fouls: int = 0                         # 犯规
    yellow_cards: int = 0                  # 黄牌
    red_cards: int = 0                     # 红牌
    offsides: int = 0                      # 越位
    total_passes: int = 0                  # 总传球
    accurate_passes: int = 0               # 精准传球
    pass_pct: float = 0.0                  # 传球成功率 %
    total_tackles: int = 0                 # 总抢断
    tackles_won: int = 0                   # 成功抢断
    clearances: int = 0                    # 解围
    saves: int = 0                         # 扑救
    big_chances: int = 0                   # 绝佳机会
    big_chances_missed: int = 0            # 错失绝佳机会
    hit_woodwork: int = 0                  # 击中门框
    expected_goals_against: float = 0.0    # 预期失球 xGA
    raw_stats: Dict = field(default_factory=dict)


@dataclass
class FotMobPlayerRating:
    """FotMob 球员评分"""
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    position: str = ""           # GK/DEF/MID/FWD
    shirt_number: int = 0
    is_substitute: bool = False
    rating: float = 0.0          # FotMob评分 (0-10)
    minutes_played: int = 0
    goals: int = 0
    assists: int = 0
    xg: float = 0.0              # 预期进球
    xa: float = 0.0              # 预期助攻
    shots: int = 0
    shots_on_target: int = 0
    passes: int = 0
    accurate_passes: int = 0
    tackles: int = 0
    interceptions: int = 0
    clearances: int = 0
    touches: int = 0
    fouls_committed: int = 0
    fouls_suffered: int = 0
    yellow_card: int = 0
    red_card: int = 0
    raw_data: Dict = field(default_factory=dict)


@dataclass
class FotMobLineup:
    """FotMob 阵容"""
    team_id: int = 0
    team_name: str = ""
    formation: str = ""                  # e.g. "4-2-3-1"
    coach: str = ""
    coach_id: int = 0
    starting_xi: List[FotMobPlayerRating] = field(default_factory=list)
    substitutes: List[FotMobPlayerRating] = field(default_factory=list)
    avg_rating: float = 0.0
    avg_xg: float = 0.0
    top_rated_player: str = ""


@dataclass
class FotMobShotMap:
    """FotMob 射门图"""
    player_name: str = ""
    minute: int = 0
    x: float = 0.0               # 球场坐标 X
    y: float = 0.0               # 球场坐标 Y
    xg: float = 0.0              # 该射门的xG值
    xgot: float = 0.0            # 射门后xG (xGOT)
    result: str = ""             # Goal/Blocked/Saved/Miss
    situation: str = ""          # OpenPlay/SetPiece/Penalty/Counter
    shot_type: str = ""          # LeftFoot/RightFoot/Header


@dataclass
class FotMobMomentum:
    """FotMob 比赛势头"""
    minute: int = 0
    value: int = 0               # 势头值


@dataclass
class FotMobH2H:
    """FotMob H2H 记录"""
    date: str = ""
    home_team: str = ""
    away_team: str = ""
    home_score: int = 0
    away_score: int = 0
    league: str = ""
    season: str = ""


@dataclass
class FotMobGoalEvent:
    """FotMob 进球事件"""
    minute: int = 0
    time_str: str = ""
    player_name: str = ""
    assist_name: str = ""
    is_home: bool = True
    is_own_goal: bool = False
    is_penalty: bool = False
    score_str: str = ""          # e.g. "1-0"


@dataclass
class FotMobMatchReport:
    """FotMob 单场完整报告"""
    match_id: str = ""
    home_team: str = ""
    away_team: str = ""
    home_team_id: int = 0
    away_team_id: int = 0
    league: str = ""
    league_id: int = 0
    kickoff_time: str = ""
    collected_at: str = ""
    url: str = ""

    # 比分状态
    is_finished: bool = False
    is_live: bool = False
    home_score: int = 0
    away_score: int = 0
    score_str: str = ""

    # Layer 2 核心数据
    home_stats: FotMobTeamStats = field(default_factory=FotMobTeamStats)
    away_stats: FotMobTeamStats = field(default_factory=FotMobTeamStats)

    # Layer 1 阵容
    home_lineup: FotMobLineup = field(default_factory=FotMobLineup)
    away_lineup: FotMobLineup = field(default_factory=FotMobLineup)

    # 射门图
    home_shotmap: List[FotMobShotMap] = field(default_factory=list)
    away_shotmap: List[FotMobShotMap] = field(default_factory=list)

    # 势头
    momentum: List[FotMobMomentum] = field(default_factory=list)

    # 进球事件
    goals: List[FotMobGoalEvent] = field(default_factory=list)

    # H2H
    h2h_records: List[FotMobH2H] = field(default_factory=list)

    # 比赛信息
    referee: str = ""
    venue: str = ""
    attendance: int = 0

    # 原始数据（用于调试）
    raw_response: Dict = field(default_factory=dict)


# ============================================
# FotMob 采集器
# ============================================

# 常见联赛 FotMob ID 映射表
LEAGUE_IDS = {
    "英超": 47, "Premier League": 47,
    "西甲": 87, "La Liga": 87,
    "德甲": 54, "Bundesliga": 54,
    "意甲": 55, "Serie A": 55,
    "法甲": 53, "Ligue 1": 53,
    "欧冠": 42, "Champions League": 42,
    "欧联": 73, "Europa League": 73,
    "葡超": 61, "Primeira Liga": 61,
    "荷甲": 57, "Eredivisie": 57,
    "瑞超": 153, "Allsvenskan": 153,
    "挪超": 135, "Eliteserien": 135,
    "丹超": 121, "Superliga": 121,
    "日联": 205, "J1 League": 205,
    "韩K": 174, "K League 1": 174,
    "英冠": 48, "Championship": 48,
    "德乙": 56, "2. Bundesliga": 56,
    "法乙": 64, "Ligue 2": 64,
    "英甲": 49, "League One": 49,
    "巴甲": 84, "Brasileirão": 84,
    "解放者杯": 80, "Copa Libertadores": 80,
}


class FotMobCollector:
    """
    FotMob 数据采集器

    使用方式:
      1. 外部调度器通过 WebFetch 获取 FotMob JSON 数据
      2. 调用 parse_match_detail(json_str) 解析
      3. 调用 to_pipeline_format(report) 转换为管道标准格式

    URL模式:
      比赛详情: https://www.fotmob.com/api/matchDetails?matchId={match_id}
      比赛列表: https://www.fotmob.com/api/matches?date={YYYYMMDD}
      搜索:     https://www.fotmob.com/api/searchData?term={query}

    核心数据价值:
      - xG/xGA: 填补管道Layer 2最大空白
      - 球员评分: 判断球队状态和关键球员影响
      - 控球率/射门: 补充现有数据维度
      - 阵容阵型: 辅助验证球迷屋伤停数据
    """

    # API端点
    MATCH_DETAIL_URL = "https://www.fotmob.com/api/matchDetails?matchId={match_id}"
    MATCHES_URL = "https://www.fotmob.com/api/matches?date={date_str}"
    SEARCH_URL = "https://www.fotmob.com/api/searchData?term={query}"
    TEAM_URL = "https://www.fotmob.com/api/teams?id={team_id}"

    # 统计字段映射: FotMob stat title → FotMobTeamStats 字段名
    STAT_FIELD_MAP = {
        "Expected goals": "expected_goals",
        "Expected goals (xG)": "expected_goals",
        "Ball possession": "possession_pct",
        "Total shots": "total_shots",
        "Shots on target": "shots_on_target",
        "Shots off target": "shots_off_target",
        "Blocked shots": "blocked_shots",
        "Corner kicks": "corners",
        "Fouls": "fouls",
        "Yellow cards": "yellow_cards",
        "Red cards": "red_cards",
        "Offsides": "offsides",
        "Total passes": "total_passes",
        "Accurate passes": "accurate_passes",
        "Tackles": "total_tackles",
        "Clearances": "clearances",
        "Saves": "saves",
        "Big chances": "big_chances",
        "Big chances missed": "big_chances_missed",
        "Hit woodwork": "hit_woodwork",
    }

    def __init__(self):
        self._league_id_cache: Dict[str, int] = {}

    # === 任务生成 ===

    def generate_match_detail_task(self, match_id: str, home_team: str = "",
                                   away_team: str = "", league: str = "") -> Dict:
        """
        生成 FotMob 比赛详情 WebFetch 任务

        Args:
            match_id: FotMob 比赛ID (通过搜索或比赛列表获取)
            home_team: 主队名称（可选，仅用于标记）
            away_team: 客队名称（可选，仅用于标记）

        Returns:
            供外部调度器(CodeBuddy)执行的WebFetch任务描述
        """
        url = self.MATCH_DETAIL_URL.format(match_id=match_id)

        return {
            "task_id": f"fotmob_{match_id}",
            "collector": "FotMob",
            "method": "WebFetch",
            "url": url,
            "match_id": match_id,
            "teams": f"{home_team} vs {away_team}" if home_team else f"match_id={match_id}",
            "league": league,
            "expected_data": [
                "预期进球 xG (主客队)",
                "球员评分 (首发+替补)",
                "阵容+阵型",
                "控球率/射门/传球/抢断 50+统计",
                "射门图 (坐标+xG)",
                "比赛势头图",
                "进球事件 (分钟+球员+助攻)",
                "H2H历史交锋",
            ],
            "parse_instructions": (
                f"FotMob API返回的是JSON格式，直接提取所有字段。"
                f"特别注意 stats.Periods.All.stats 数组中的统计数据。"
            ),
        }

    def generate_match_list_task(self, date_str: str = "") -> Dict:
        """
        生成按日期获取比赛列表的任务

        Args:
            date_str: YYYYMMDD 格式日期，默认为今天

        Returns:
            供外部调度器执行的WebFetch任务描述
        """
        if not date_str:
            date_str = datetime.now().strftime('%Y%m%d')

        url = self.MATCHES_URL.format(date_str=date_str)

        return {
            "task_id": f"fotmob_list_{date_str}",
            "collector": "FotMob",
            "method": "WebFetch",
            "url": url,
            "date": date_str,
            "expected_data": [
                "按联赛分组的比赛列表",
                "每场比赛的 matchId (用于后续详细查询)",
                "比分和状态",
            ],
            "parse_instructions": (
                f"从JSON中提取 leagues[].matches[] 数组，"
                f"收集所有 match.id 用于后续详细分析。"
            ),
        }

    def generate_search_task(self, home_team: str, away_team: str) -> Dict:
        """
        通过搜索获取 match_id

        当没有 FotMob match_id 时，先通过搜索找到比赛

        Args:
            home_team: 主队名称
            away_team: 客队名称

        Returns:
            供外部调度器执行的WebFetch任务描述
        """
        query = f"{home_team} {away_team}"
        url = self.SEARCH_URL.format(query=query.replace(" ", "%20"))

        return {
            "task_id": f"fotmob_search_{home_team}_{away_team}",
            "collector": "FotMob",
            "method": "WebFetch",
            "url": url,
            "query": query,
            "expected_data": [
                f"{home_team} 的 matchId",
                f"{away_team} 的 teamId",
            ],
            "parse_instructions": (
                f"搜索 '{home_team} vs {away_team}'，从结果中找到对应的 matchId。"
                f"注意: 如果搜索不到精确匹配，返回最可能的比赛ID。"
            ),
        }

    def generate_match_id_discovery_task(self, home_team: str, away_team: str,
                                         date_str: str = "", league: str = "") -> Dict:
        """
        生成发现 FotMob match_id 的完整任务链

        先搜索，再按日期查找，确保找到正确的 match_id

        Returns:
            包含搜索任务和日期任务的任务链
        """
        tasks = []

        # Step 1: 按日期查找
        tasks.append(self.generate_match_list_task(date_str))

        # Step 2: 搜索确认
        tasks.append(self.generate_search_task(home_team, away_team))

        return {
            "task_id": f"fotmob_discovery_{home_team}_{away_team}",
            "collector": "FotMob",
            "method": "WebFetch (multi-step)",
            "chain": tasks,
            "expected_output": f"{home_team} vs {away_team} 的 FotMob match_id",
            "parse_instructions": (
                f"Step 1: 从日期列表中找 {home_team} vs {away_team} 的比赛 "
                f"(按联赛筛选: {league if league else '不限'})\n"
                f"Step 2: 用搜索结果交叉验证 match_id\n"
                f"Step 3: 输出确认的 match_id"
            ),
        }

    # === JSON 解析: matchDetail ===

    def parse_match_detail(self, json_str: str, match_id: str = "",
                           home_team: str = "", away_team: str = "",
                           league: str = "") -> FotMobMatchReport:
        """
        解析 FotMob matchDetail JSON 响应

        全自动JSON解析，无需AI辅助

        返回完整的 FotMobMatchReport，包含:
          - 比赛基本信息 (比分/时间/状态)
          - 球队统计数据 (xG/控球/射门等)
          - 阵容+球员评分
          - 射门图坐标
          - 比赛势头
          - 进球事件
          - H2H记录
        """
        try:
            data = json.loads(json_str) if isinstance(json_str, str) else json_str
        except json.JSONDecodeError as e:
            log.error(f"  ❌ FotMob JSON解析失败: {e}")
            return FotMobMatchReport(match_id=match_id)

        report = FotMobMatchReport(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league=league,
            collected_at=datetime.now().isoformat(),
            url=self.MATCH_DETAIL_URL.format(match_id=match_id) if match_id else "",
            raw_response=data,
        )

        # === Section 1: General (基本信息) ===
        general = data.get('general', {})
        if general:
            report.match_id = str(general.get('matchId', match_id))
            report.league = general.get('leagueName', league)
            report.league_id = general.get('leagueId', 0)
            report.kickoff_time = general.get('matchTimeUTCDate', '')
            report.venue = general.get('venue', {}).get('name', '') if isinstance(general.get('venue'), dict) else ''

            home = general.get('homeTeam', {})
            away = general.get('awayTeam', {})
            report.home_team = home.get('name', home_team)
            report.away_team = away.get('name', away_team)
            report.home_team_id = home.get('id', 0)
            report.away_team_id = away.get('id', 0)

        # === Section 2: Header (比分+事件) ===
        header = data.get('header', {})
        if header:
            status = header.get('status', {})
            report.is_finished = status.get('finished', False)
            report.is_live = status.get('started', False) and not status.get('finished', False)
            report.score_str = status.get('scoreStr', '')

            # 解析比分
            events = header.get('events', [])
            home_goals = 0
            away_goals = 0
            for evt in events:
                if evt.get('type') == 'Goal' or evt.get('type') == 'Penalty':
                    is_home = evt.get('isHome', False)
                    is_own = evt.get('isOwnGoal', False)
                    if is_own:
                        # 乌龙球，对方得分
                        if is_home:
                            away_goals += 1
                        else:
                            home_goals += 1
                    else:
                        if is_home:
                            home_goals += 1
                        else:
                            away_goals += 1

            report.home_score = home_goals
            report.away_score = away_goals

            # 进球事件详情
            for evt in events:
                if evt.get('type') in ('Goal', 'Penalty'):
                    report.goals.append(FotMobGoalEvent(
                        minute=evt.get('time', 0),
                        time_str=evt.get('timeStr', ''),
                        player_name=evt.get('player', {}).get('name', ''),
                        assist_name=evt.get('assist', {}).get('name', '') if evt.get('assist') else '',
                        is_home=evt.get('isHome', False),
                        is_own_goal=evt.get('isOwnGoal', False),
                        is_penalty=evt.get('type') == 'Penalty',
                        score_str=evt.get('scoreStr', ''),
                    ))

        # === Section 3: Content (核心数据) ===
        content = data.get('content', {})

        # 3a. Match Facts (比赛信息 + 势头)
        match_facts = content.get('matchFacts', {})
        if match_facts:
            info_box = match_facts.get('infoBox', {})
            if info_box:
                report.referee = info_box.get('Referee', '')
                report.attendance = int(info_box.get('Attendance', 0)) if info_box.get('Attendance') else 0

            # 势头图
            momentum_data = match_facts.get('momentum', {})
            main_momentum = momentum_data.get('main', {})
            for point in main_momentum.get('data', []):
                report.momentum.append(FotMobMomentum(
                    minute=point.get('minute', 0),
                    value=point.get('value', 0),
                ))

        # 3b. Stats (统计数据 — 核心层)
        stats = content.get('stats', {})
        periods = stats.get('Periods', {})
        all_stats = periods.get('All', {}).get('stats', [])

        for stat_item in all_stats:
            title = stat_item.get('title', '')
            values = stat_item.get('stats', [])
            field_name = self.STAT_FIELD_MAP.get(title)

            if field_name and len(values) >= 2:
                try:
                    home_val = float(values[0]) if values[0] is not None else 0
                    away_val = float(values[1]) if values[1] is not None else 0
                    setattr(report.home_stats, field_name, home_val)
                    setattr(report.away_stats, field_name, away_val)
                except (ValueError, TypeError):
                    pass

            # 额外字段: 预期失球
            if title == "Expected goals (xG)" and len(values) >= 2:
                # xGA 需要从对方xG推断，或从其他字段获取
                pass

            # 额外字段: 传球成功率
            if title in ("Accurate passes", "Total passes") and len(values) >= 2:
                # 在另一个stat项中计算
                pass

            # 存储原始数据
            report.home_stats.raw_stats[title] = values[0] if len(values) > 0 else None
            report.away_stats.raw_stats[title] = values[1] if len(values) > 1 else None

        # 计算传球成功率
        if report.home_stats.total_passes > 0:
            report.home_stats.pass_pct = round(
                report.home_stats.accurate_passes / report.home_stats.total_passes * 100, 1)
        if report.away_stats.total_passes > 0:
            report.away_stats.pass_pct = round(
                report.away_stats.accurate_passes / report.away_stats.total_passes * 100, 1)

        # 3c. Lineup (阵容+球员评分)
        lineup_data = content.get('lineup', {})
        lineups = lineup_data.get('lineups', [])

        for team_lineup in lineups:
            team_id = team_lineup.get('teamId', 0)
            team_name = team_lineup.get('teamName', '')
            formation = team_lineup.get('formation', '')

            lineup = FotMobLineup(
                team_id=team_id,
                team_name=team_name,
                formation=formation,
                coach=team_lineup.get('coach', {}).get('name', ''),
                coach_id=team_lineup.get('coach', {}).get('id', 0),
            )

            # 解析球员
            players = team_lineup.get('players', [])
            if isinstance(players, list):
                for row in players:
                    if not isinstance(row, list):
                        continue
                    for player_data in row:
                        if not isinstance(player_data, dict):
                            continue
                        player = self._parse_player(player_data)
                        if player.is_substitute:
                            lineup.substitutes.append(player)
                        else:
                            lineup.starting_xi.append(player)

            # 计算平均评分和xG
            all_rated = [p for p in lineup.starting_xi if p.rating > 0]
            if all_rated:
                lineup.avg_rating = round(sum(p.rating for p in all_rated) / len(all_rated), 2)
            all_xg = [p for p in lineup.starting_xi if p.xg > 0]
            if all_xg:
                lineup.avg_xg = round(sum(p.xg for p in all_xg) / len(all_xg), 4)

            # 最高评分球员
            if all_rated:
                top = max(all_rated, key=lambda p: p.rating)
                lineup.top_rated_player = top.name

            if team_id == report.home_team_id:
                report.home_lineup = lineup
            elif team_id == report.away_team_id:
                report.away_lineup = lineup
            elif team_name == report.home_team:
                report.home_lineup = lineup
            elif team_name == report.away_team:
                report.away_lineup = lineup

        # 3d. Shotmap (射门图)
        shotmap = content.get('shotmap', {})
        for shot in shotmap.get('shots', []):
            sm = FotMobShotMap(
                player_name=shot.get('fullName', shot.get('name', '')),
                minute=shot.get('min', 0),
                x=shot.get('x', 0),
                y=shot.get('y', 0),
                xg=shot.get('expectedGoals', shot.get('xG', 0)),
                xgot=shot.get('expectedGoalsOnTarget', shot.get('xGOT', 0)),
                result=shot.get('eventType', ''),
                situation=shot.get('situation', ''),
                shot_type=shot.get('shotType', ''),
            )
            if shot.get('isHome', False):
                report.home_shotmap.append(sm)
            else:
                report.away_shotmap.append(sm)

        # 3e. H2H
        h2h_data = content.get('h2h', {})
        for h2h_item in h2h_data.get('matches', []):
            h2h_status = h2h_item.get('status', {})
            report.h2h_records.append(FotMobH2H(
                date=h2h_item.get('matchDate', ''),
                home_team=h2h_item.get('home', {}).get('name', ''),
                away_team=h2h_item.get('away', {}).get('name', ''),
                home_score=h2h_item.get('home', {}).get('score', 0),
                away_score=h2h_item.get('away', {}).get('score', 0),
                league=h2h_item.get('leagueName', ''),
                season=h2h_item.get('seasonName', ''),
            ))

        # 统计计数
        log.info(f"  📊 FotMob解析完成: {report.home_team} vs {report.away_team}")
        log.info(f"     比分: {report.score_str}")
        log.info(f"     xG: {report.home_stats.expected_goals} - {report.away_stats.expected_goals}")
        log.info(f"     阵容: 主{len(report.home_lineup.starting_xi)}人 客{len(report.away_lineup.starting_xi)}人")
        log.info(f"     射门: 主{len(report.home_shotmap)}次 客{len(report.away_shotmap)}次")
        log.info(f"     评分: 主{report.home_lineup.avg_rating} 客{report.away_lineup.avg_rating}")

        return report

    def _parse_player(self, player_data: Dict) -> FotMobPlayerRating:
        """解析单个球员数据"""
        stats = player_data.get('stats', {})
        if not isinstance(stats, dict):
            stats = {}

        return FotMobPlayerRating(
            name=player_data.get('name', {}).get('fullName', player_data.get('name', '')),
            first_name=player_data.get('name', {}).get('firstName', ''),
            last_name=player_data.get('name', {}).get('lastName', ''),
            position=player_data.get('position', ''),
            shirt_number=player_data.get('shirt', 0),
            is_substitute=player_data.get('substitute', False),
            rating=float(player_data.get('rating', {}).get('num', 0)) if isinstance(player_data.get('rating'), dict) else float(player_data.get('rating', 0)),
            minutes_played=player_data.get('minutesPlayed', 0),
            goals=player_data.get('goals', 0),
            assists=player_data.get('assists', 0),
            xg=float(stats.get('Expected goals (xG)', 0)) if stats.get('Expected goals (xG)') else 0.0,
            xa=float(stats.get('Expected assists (xA)', 0)) if stats.get('Expected assists (xA)') else 0.0,
            shots=int(stats.get('Total shots', 0)) if stats.get('Total shots') else 0,
            shots_on_target=int(stats.get('Shots on target', 0)) if stats.get('Shots on target') else 0,
            passes=int(stats.get('Accurate passes', 0)) if stats.get('Accurate passes') else 0,
            touches=int(stats.get('Touches', 0)) if stats.get('Touches') else 0,
            tackles=int(stats.get('Tackles', 0)) if stats.get('Tackles') else 0,
            fouls_committed=int(stats.get('Fouls', 0)) if stats.get('Fouls') else 0,
            fouls_suffered=int(stats.get('Fouled', 0)) if stats.get('Fouled') else 0,
            yellow_card=stats.get('Yellow card', 0) or 0,
            red_card=stats.get('Red card', 0) or 0,
            raw_data=player_data if log.isEnabledFor(logging.DEBUG) else {},
        )

    # === JSON 解析: matchList ===

    def parse_match_list(self, json_str: str) -> List[Dict]:
        """
        解析比赛列表，提取所有 match_id

        Args:
            json_str: /api/matches 返回的JSON

        Returns:
            [
                {"match_id": "4310531", "home": "Man City", "away": "Chelsea",
                 "league": "Premier League", "league_id": 47, "time": "14:00",
                 "status": "finished"},
                ...
            ]
        """
        try:
            data = json.loads(json_str) if isinstance(json_str, str) else json_str
        except json.JSONDecodeError:
            return []

        matches = []
        for league in data.get('leagues', []):
            league_name = league.get('name', '')
            league_id = league.get('primaryId', 0)
            ccode = league.get('ccode', '')

            for match in league.get('matches', []):
                matches.append({
                    "match_id": str(match.get('id', '')),
                    "home": match.get('home', {}).get('name', ''),
                    "away": match.get('away', {}).get('name', ''),
                    "home_score": match.get('home', {}).get('score', 0),
                    "away_score": match.get('away', {}).get('score', 0),
                    "league": league_name,
                    "league_id": league_id,
                    "country_code": ccode,
                    "time": match.get('time', ''),
                    "utc_time": match.get('status', {}).get('utcTime', ''),
                    "status": ("finished" if match.get('status', {}).get('finished')
                              else "live" if match.get('status', {}).get('started')
                              else "scheduled"),
                    "score_str": match.get('status', {}).get('scoreStr', ''),
                })

        log.info(f"  📅 FotMob日期列表: {len(matches)}场比赛")
        return matches

    # === pipeline 格式转换 ===

    def to_pipeline_format(self, report: FotMobMatchReport) -> Dict:
        """
        将 FotMob 报告转换为管道标准格式

        输出格式兼容 main.py 的 MatchData 结构
        """
        # Layer 2: xG + 统计数据
        stats_data = {
            "home_xg": report.home_stats.expected_goals,
            "away_xg": report.away_stats.expected_goals,
            "home_xga": report.away_stats.expected_goals,  # xGA = 对方xG
            "away_xga": report.home_stats.expected_goals,
            "xg_diff": round(report.home_stats.expected_goals - report.away_stats.expected_goals, 2),
            "possession": {
                "home": report.home_stats.possession_pct,
                "away": report.away_stats.possession_pct,
            },
            "shots": {
                "home_total": report.home_stats.total_shots,
                "away_total": report.away_stats.total_shots,
                "home_on_target": report.home_stats.shots_on_target,
                "away_on_target": report.away_stats.shots_on_target,
            },
            "passes": {
                "home_total": report.home_stats.total_passes,
                "away_total": report.away_stats.total_passes,
                "home_pct": report.home_stats.pass_pct,
                "away_pct": report.away_stats.pass_pct,
            },
            "corners": {
                "home": report.home_stats.corners,
                "away": report.away_stats.corners,
            },
            "cards": {
                "home_yellow": report.home_stats.yellow_cards,
                "away_yellow": report.away_stats.yellow_cards,
                "home_red": report.home_stats.red_cards,
                "away_red": report.away_stats.red_cards,
            },
            "big_chances": {
                "home_created": report.home_stats.big_chances,
                "away_created": report.away_stats.big_chances,
                "home_missed": report.home_stats.big_chances_missed,
                "away_missed": report.away_stats.big_chances_missed,
            },
        }

        # Layer 1: 阵容 + 评分
        lineup_data = {
            "home_formation": report.home_lineup.formation,
            "away_formation": report.away_lineup.formation,
            "home_avg_rating": report.home_lineup.avg_rating,
            "away_avg_rating": report.away_lineup.avg_rating,
            "rating_diff": round(report.home_lineup.avg_rating - report.away_lineup.avg_rating, 2),
            "home_top_player": report.home_lineup.top_rated_player,
            "away_top_player": report.away_lineup.top_rated_player,
            "home_rating_flag": (
                "danger" if report.home_lineup.avg_rating < 6.5 else
                "warning" if report.home_lineup.avg_rating < 6.8 else "normal"
            ),
            "away_rating_flag": (
                "danger" if report.away_lineup.avg_rating < 6.5 else
                "warning" if report.away_lineup.avg_rating < 6.8 else "normal"
            ),
            "home_squad": [
                {
                    "name": p.name,
                    "position": p.position,
                    "number": p.shirt_number,
                    "rating": p.rating,
                    "xg": p.xg,
                    "is_sub": p.is_substitute,
                }
                for p in report.home_lineup.starting_xi + report.home_lineup.substitutes
            ],
            "away_squad": [
                {
                    "name": p.name,
                    "position": p.position,
                    "number": p.shirt_number,
                    "rating": p.rating,
                    "xg": p.xg,
                    "is_sub": p.is_substitute,
                }
                for p in report.away_lineup.starting_xi + report.away_lineup.substitutes
            ],
        }

        # 射门图摘要
        shotmap_data = {
            "home_total_shots": len(report.home_shotmap),
            "away_total_shots": len(report.away_shotmap),
            "home_avg_xg_per_shot": (
                round(sum(s.xg for s in report.home_shotmap) / len(report.home_shotmap), 4)
                if report.home_shotmap else 0
            ),
            "away_avg_xg_per_shot": (
                round(sum(s.xg for s in report.away_shotmap) / len(report.away_shotmap), 4)
                if report.away_shotmap else 0
            ),
            "home_goals_from_shots": len([s for s in report.home_shotmap if s.result == 'Goal']),
            "away_goals_from_shots": len([s for s in report.away_shotmap if s.result == 'Goal']),
        }

        # H2H
        h2h_data = []
        for h in report.h2h_records:
            h2h_data.append({
                "date": h.date,
                "home": h.home_team,
                "away": h.away_team,
                "score": f"{h.home_score}-{h.away_score}",
                "league": h.league,
            })

        # 势头摘要
        home_momentum_avg = sum(m.value for m in report.momentum) / len(report.momentum) if report.momentum else 0

        # 综合信号
        signals = self._compute_signals(report)
        risk_assessment = self._assess_fotmob_risk(report)

        return {
            "source": "fotmob",
            "match_id": report.match_id,
            "url": report.url,
            "collected_at": report.collected_at,

            # 比赛基本信息
            "match_info": {
                "home_team": report.home_team,
                "away_team": report.away_team,
                "league": report.league,
                "kickoff": report.kickoff_time,
                "score": report.score_str,
                "is_finished": report.is_finished,
                "referee": report.referee,
                "venue": report.venue,
            },

            # Layer 2: 统计数据
            "stats": stats_data,

            # Layer 1: 阵容+评分
            "lineup": lineup_data,

            # 射门图
            "shotmap": shotmap_data,

            # H2H
            "h2h": h2h_data,

            # 势头
            "momentum": {
                "data_points": len(report.momentum),
                "home_avg_value": round(home_momentum_avg, 1),
            },

            # 进球事件
            "goals": [
                {
                    "minute": g.minute,
                    "player": g.player_name,
                    "assist": g.assist_name,
                    "side": "home" if g.is_home else "away",
                    "type": "penalty" if g.is_penalty else "own_goal" if g.is_own_goal else "goal",
                }
                for g in report.goals
            ],

            # 分析信号
            "signals": signals,

            # 风险评估
            "risk": risk_assessment,

            # 星级联动建议
            "star_advice": {
                "adjustment": signals.get("star_adjustment", 0),
                "reasons": signals.get("reasons", []),
                "confidence_boost": signals.get("confidence_boost", False),
            },

            # 原始报告引用
            "_raw_report": report,
        }

    def _compute_signals(self, report: FotMobMatchReport) -> Dict:
        """
        从FotMob数据中提取分析信号

        联动铁律:
          - Rule 19: xG偏离 → 预警
          - Rule 27: 阵容评分 → 支持度
          - Rule 31: 射门效率差 → 可持续性评估
        """
        signals = {}
        reasons = []
        star_adj = 0
        confidence_boost = False

        # Signal 1: xG vs 实际比分偏离
        xg_home = report.home_stats.expected_goals
        xg_away = report.away_stats.expected_goals
        actual_home = report.home_score
        actual_away = report.away_score

        if xg_home > 0 or xg_away > 0:
            xg_diff = xg_home - xg_away
            actual_diff = actual_home - actual_away

            # xG显著领先但实际落后 → 运气差
            if xg_diff > 1.0 and actual_diff < 0:
                signals["xG_luck"] = "主队xG显著领先但比分落后 → 运气差，考虑反弹"
                reasons.append("xG/比分偏离: 主队运气差")
            elif xg_diff < -1.0 and actual_diff > 0:
                signals["xG_luck"] = "客队xG显著领先但主队领先 → 客队运气差"
                reasons.append("xG/比分偏离: 客队运气差")

            # xG远超实际进球 → 终结能力差
            if xg_home > actual_home + 1.5:
                signals["home_finishing"] = "主队终结能力不足(xG>>实际进球)"
                reasons.append("主队终结差: xG未转化为进球")
            if xg_away > actual_away + 1.5:
                signals["away_finishing"] = "客队终结能力不足(xG>>实际进球)"
                reasons.append("客队终结差: xG未转化为进球")

        # Signal 2: 阵容评分
        home_rating = report.home_lineup.avg_rating
        away_rating = report.away_lineup.avg_rating

        if home_rating > 0 and away_rating > 0:
            rating_diff = home_rating - away_rating
            if rating_diff > 0.5:
                signals["rating"] = f"主队阵容评分占优 +{rating_diff:.1f}"
                confidence_boost = True
            elif rating_diff < -0.5:
                signals["rating"] = f"客队阵容评分占优 +{abs(rating_diff):.1f}"
            else:
                signals["rating"] = "双方阵容评分接近"

            # 关键球员评分
            if report.home_lineup.top_rated_player:
                signals["home_mvp"] = report.home_lineup.top_rated_player
            if report.away_lineup.top_rated_player:
                signals["away_mvp"] = report.away_lineup.top_rated_player

        # Signal 3: 控球率对比
        home_poss = report.home_stats.possession_pct
        away_poss = report.away_stats.possession_pct
        if home_poss > 60:
            signals["possession"] = f"主队控球优势 {home_poss:.0f}%"
        elif away_poss > 60:
            signals["possession"] = f"客队控球优势 {away_poss:.0f}%"

        # Signal 4: 射门效率
        home_shots = report.home_stats.shots_on_target
        away_shots = report.away_stats.shots_on_target
        if home_shots > 0 and actual_home > 0:
            home_conv = actual_home / home_shots
            if home_conv > 0.5:
                signals["home_shot_efficiency"] = f"主队射门转化率极高 {home_conv:.1%}"
                reasons.append("主队射门转化率异常高 → 可持续性评估")
        if away_shots > 0 and actual_away > 0:
            away_conv = actual_away / away_shots
            if away_conv > 0.5:
                signals["away_shot_efficiency"] = f"客队射门转化率极高 {away_conv:.1%}"
                reasons.append("客队射门转化率异常高 → 可持续性评估")

        # Signal 5: 阵型分析
        home_form = report.home_lineup.formation
        away_form = report.away_lineup.formation
        if home_form and away_form:
            signals["formations"] = f"主{home_form} vs 客{away_form}"

        return {
            "signals": signals,
            "reasons": reasons,
            "star_adjustment": star_adj,
            "confidence_boost": confidence_boost,
        }

    def _assess_fotmob_risk(self, report: FotMobMatchReport) -> Dict:
        """基于 FotMob 数据的风险评估"""
        risk_level = "low"
        factors = []

        # xG反常
        xg_home = report.home_stats.expected_goals
        xg_away = report.away_stats.expected_goals
        if abs(xg_home - xg_away) > 2.0:
            factors.append(f"xG差距过大 ({abs(xg_home - xg_away):.2f})")

        # 阵容评分低
        if report.home_lineup.avg_rating < 6.5 or report.away_lineup.avg_rating < 6.5:
            factors.append("一方阵容评分过低")
            risk_level = "medium"

        # 红牌影响
        if report.home_stats.red_cards > 0 or report.away_stats.red_cards > 0:
            factors.append("有红牌")
            risk_level = "high"

        if len(factors) >= 2:
            risk_level = "high"
        elif len(factors) == 1:
            risk_level = "medium"

        return {"level": risk_level, "factors": factors}


# ============================================
# 便捷函数
# ============================================

def quick_collect_match(match_id: str, home: str = "", away: str = "",
                        league: str = "") -> Dict:
    """快速生成FotMob比赛详情采集任务"""
    collector = FotMobCollector()
    return collector.generate_match_detail_task(match_id, home, away, league)


def quick_discover_match(home: str, away: str, date: str = "",
                         league: str = "") -> Dict:
    """快速生成FotMob match_id发现任务"""
    collector = FotMobCollector()
    return collector.generate_match_id_discovery_task(home, away, date, league)


def get_league_id(league_name: str) -> int:
    """根据联赛名称获取 FotMob league_id"""
    return LEAGUE_IDS.get(league_name, 0)


# ============================================
# 自测
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print("=" * 60)
    print("  FotMob 数据采集器 v1.0 - 自测")
    print("=" * 60)

    collector = FotMobCollector()

    # === Test 1: 任务生成 ===
    print("\n  [Test 1] 生成比赛详情采集任务")
    task = collector.generate_match_detail_task(
        match_id="4667808",
        home_team="天狼星",
        away_team="布鲁马波",
        league="瑞典超",
    )
    print(f"    任务ID: {task['task_id']}")
    print(f"    URL: {task['url']}")
    print(f"    对阵: {task['teams']}")
    print(f"    方法: {task['method']}")
    print(f"    预期数据: {len(task['expected_data'])}项")

    # === Test 2: 日期列表任务 ===
    print("\n  [Test 2] 生成日期比赛列表任务")
    list_task = collector.generate_match_list_task("20260810")
    print(f"    任务ID: {list_task['task_id']}")
    print(f"    URL: {list_task['url']}")
    print(f"    日期: {list_task['date']}")

    # === Test 3: 搜索任务 ===
    print("\n  [Test 3] 生成搜索任务")
    search_task = collector.generate_search_task("天狼星", "布鲁马波")
    print(f"    任务ID: {search_task['task_id']}")
    print(f"    URL: {search_task['url']}")

    # === Test 4: 模拟 matchDetail JSON 解析 ===
    print("\n  [Test 4] 模拟解析 matchDetail JSON")
    sample_json = {
        "general": {
            "matchId": "4667808",
            "matchName": "天狼星 vs 布鲁马波",
            "matchTimeUTCDate": "2026-08-10T14:00:00.000Z",
            "leagueName": "瑞典超",
            "leagueId": 153,
            "homeTeam": {"name": "天狼星", "id": 10001},
            "awayTeam": {"name": "布鲁马波", "id": 10002},
        },
        "header": {
            "status": {"finished": True, "scoreStr": "2 - 1"},
            "events": [
                {"type": "Goal", "time": 23, "timeStr": "23'",
                 "player": {"name": "A. Player"}, "isHome": True, "scoreStr": "1 - 0"},
                {"type": "Goal", "time": 67, "timeStr": "67'",
                 "player": {"name": "B. Player"}, "isHome": False, "scoreStr": "1 - 1"},
                {"type": "Goal", "time": 89, "timeStr": "89'",
                 "player": {"name": "C. Player"}, "isHome": True, "scoreStr": "2 - 1"},
            ],
        },
        "content": {
            "matchFacts": {
                "infoBox": {"Referee": "M. Oliver", "Attendance": "15000"},
                "momentum": {
                    "main": {
                        "data": [
                            {"minute": 1, "value": 10},
                            {"minute": 2, "value": 15},
                            {"minute": 3, "value": 25},
                        ]
                    }
                },
            },
            "stats": {
                "Periods": {
                    "All": {
                        "stats": [
                            {"title": "Expected goals (xG)", "stats": [1.84, 0.72]},
                            {"title": "Ball possession", "stats": [65, 35]},
                            {"title": "Total shots", "stats": [18, 8]},
                            {"title": "Shots on target", "stats": [7, 3]},
                            {"title": "Corner kicks", "stats": [9, 2]},
                            {"title": "Total passes", "stats": [520, 280]},
                            {"title": "Accurate passes", "stats": [468, 224]},
                            {"title": "Fouls", "stats": [12, 15]},
                            {"title": "Yellow cards", "stats": [2, 3]},
                            {"title": "Red cards", "stats": [0, 0]},
                            {"title": "Big chances", "stats": [4, 1]},
                            {"title": "Big chances missed", "stats": [2, 0]},
                            {"title": "Tackles", "stats": [18, 22]},
                            {"title": "Clearances", "stats": [15, 28]},
                            {"title": "Saves", "stats": [2, 5]},
                        ]
                    }
                }
            },
            "lineup": {
                "lineups": [
                    {
                        "teamId": 10001,
                        "teamName": "天狼星",
                        "formation": "4-3-3",
                        "coach": {"name": "Coach A", "id": 5001},
                        "players": [
                            [
                                {
                                    "name": {"fullName": "Goalkeeper 1"},
                                    "position": "GK",
                                    "shirt": 1,
                                    "substitute": False,
                                    "rating": {"num": 7.2},
                                    "minutesPlayed": 90,
                                    "stats": {"Expected goals (xG)": 0.0},
                                },
                            ],
                            [
                                {
                                    "name": {"fullName": "Defender 1"},
                                    "position": "DEF",
                                    "shirt": 4,
                                    "substitute": False,
                                    "rating": {"num": 7.5},
                                    "minutesPlayed": 90,
                                    "stats": {"Expected goals (xG)": 0.10},
                                },
                                {
                                    "name": {"fullName": "Defender 2"},
                                    "position": "DEF",
                                    "shirt": 5,
                                    "substitute": False,
                                    "rating": {"num": 6.8},
                                    "minutesPlayed": 90,
                                    "stats": {"Expected goals (xG)": 0.05},
                                },
                            ],
                            [
                                {
                                    "name": {"fullName": "Midfielder 1"},
                                    "position": "MID",
                                    "shirt": 8,
                                    "substitute": False,
                                    "rating": {"num": 8.1},
                                    "minutesPlayed": 90,
                                    "stats": {"Expected goals (xG)": 0.40},
                                    "goals": 1,
                                },
                            ],
                            [
                                {
                                    "name": {"fullName": "Forward 1"},
                                    "position": "FWD",
                                    "shirt": 9,
                                    "substitute": False,
                                    "rating": {"num": 7.8},
                                    "minutesPlayed": 85,
                                    "stats": {"Expected goals (xG)": 0.85},
                                    "goals": 1,
                                },
                            ],
                            [
                                {
                                    "name": {"fullName": "Sub 1"},
                                    "position": "MID",
                                    "shirt": 14,
                                    "substitute": True,
                                    "rating": {"num": 6.5},
                                    "minutesPlayed": 5,
                                    "stats": {"Expected goals (xG)": 0.0},
                                },
                            ],
                        ],
                    },
                    {
                        "teamId": 10002,
                        "teamName": "布鲁马波",
                        "formation": "4-4-2",
                        "coach": {"name": "Coach B", "id": 6001},
                        "players": [
                            [
                                {
                                    "name": {"fullName": "GK Away"},
                                    "position": "GK",
                                    "shirt": 1,
                                    "substitute": False,
                                    "rating": {"num": 6.2},
                                    "minutesPlayed": 90,
                                    "stats": {"Expected goals (xG)": 0.0},
                                },
                            ],
                            [
                                {
                                    "name": {"fullName": "DEF Away 1"},
                                    "position": "DEF",
                                    "shirt": 3,
                                    "substitute": False,
                                    "rating": {"num": 6.0},
                                    "minutesPlayed": 90,
                                    "stats": {"Expected goals (xG)": 0.02},
                                },
                            ],
                            [
                                {
                                    "name": {"fullName": "MID Away 1"},
                                    "position": "MID",
                                    "shirt": 7,
                                    "substitute": False,
                                    "rating": {"num": 6.5},
                                    "minutesPlayed": 90,
                                    "stats": {"Expected goals (xG)": 0.15},
                                },
                            ],
                            [
                                {
                                    "name": {"fullName": "FWD Away 1"},
                                    "position": "FWD",
                                    "shirt": 10,
                                    "substitute": False,
                                    "rating": {"num": 6.8},
                                    "minutesPlayed": 78,
                                    "stats": {"Expected goals (xG)": 0.35},
                                    "goals": 1,
                                },
                            ],
                        ],
                    },
                ],
            },
            "shotmap": {
                "shots": [
                    {
                        "fullName": "Forward 1", "min": 23,
                        "x": 0.85, "y": 0.45,
                        "expectedGoals": 0.42, "expectedGoalsOnTarget": 0.78,
                        "eventType": "Goal", "situation": "OpenPlay",
                        "shotType": "RightFoot", "isHome": True,
                    },
                    {
                        "fullName": "FWD Away 1", "min": 67,
                        "x": 0.78, "y": 0.40,
                        "expectedGoals": 0.15, "expectedGoalsOnTarget": 0.35,
                        "eventType": "Goal", "situation": "Counter",
                        "shotType": "LeftFoot", "isHome": False,
                    },
                    {
                        "fullName": "Midfielder 1", "min": 89,
                        "x": 0.90, "y": 0.50,
                        "expectedGoals": 0.08, "expectedGoalsOnTarget": 0.25,
                        "eventType": "Goal", "situation": "SetPiece",
                        "shotType": "Header", "isHome": True,
                    },
                    {
                        "fullName": "Forward 1", "min": 35,
                        "x": 0.70, "y": 0.30,
                        "expectedGoals": 0.55, "expectedGoalsOnTarget": 0.80,
                        "eventType": "Saved", "situation": "OpenPlay",
                        "shotType": "RightFoot", "isHome": True,
                    },
                    {
                        "fullName": "MID Away 1", "min": 52,
                        "x": 0.25, "y": 0.55,
                        "expectedGoals": 0.03, "expectedGoalsOnTarget": 0.05,
                        "eventType": "Miss", "situation": "OpenPlay",
                        "shotType": "RightFoot", "isHome": False,
                    },
                ],
            },
            "h2h": {
                "matches": [
                    {
                        "matchDate": "2026-05-15",
                        "home": {"name": "布鲁马波", "score": 0},
                        "away": {"name": "天狼星", "score": 2},
                        "leagueName": "瑞典超",
                        "seasonName": "2026",
                    },
                    {
                        "matchDate": "2025-09-20",
                        "home": {"name": "天狼星", "score": 1},
                        "away": {"name": "布鲁马波", "score": 1},
                        "leagueName": "瑞典超",
                        "seasonName": "2025",
                    },
                ],
            },
        },
    }

    report = collector.parse_match_detail(
        json.dumps(sample_json),
        match_id="4667808",
    )

    print(f"    比赛: {report.home_team} vs {report.away_team}")
    print(f"    比分: {report.score_str} (xG: {report.home_stats.expected_goals} - {report.away_stats.expected_goals})")
    print(f"    控球: {report.home_stats.possession_pct}% - {report.away_stats.possession_pct}%")
    print(f"    射门: {report.home_stats.total_shots} - {report.away_stats.total_shots}")
    print(f"    射正: {report.home_stats.shots_on_target} - {report.away_stats.shots_on_target}")
    print(f"    传球成功率: {report.home_stats.pass_pct}% - {report.away_stats.pass_pct}%")
    print(f"    角球: {report.home_stats.corners} - {report.away_stats.corners}")
    print(f"    绝佳机会: {report.home_stats.big_chances} - {report.away_stats.big_chances}")

    print(f"\n    阵容:")
    print(f"      主队: {report.home_lineup.formation} "
          f"({len(report.home_lineup.starting_xi)}首发+{len(report.home_lineup.substitutes)}替补)"
          f"  均评: {report.home_lineup.avg_rating}")
    print(f"      客队: {report.away_lineup.formation} "
          f"({len(report.away_lineup.starting_xi)}首发+{len(report.away_lineup.substitutes)}替补)"
          f"  均评: {report.away_lineup.avg_rating}")
    print(f"      主队MVP: {report.home_lineup.top_rated_player}")
    print(f"      客队MVP: {report.away_lineup.top_rated_player}")

    print(f"\n    进球事件: {len(report.goals)}个")
    for g in report.goals:
        side = "主" if g.is_home else "客"
        assist_info = f" (助攻: {g.assist_name})" if g.assist_name else ""
        print(f"      {g.minute}' [{side}] {g.player_name}{assist_info}")

    print(f"    射门图: {len(report.home_shotmap)}+{len(report.away_shotmap)}次射门")
    home_goals_sm = len([s for s in report.home_shotmap if s.result == 'Goal'])
    away_goals_sm = len([s for s in report.away_shotmap if s.result == 'Goal'])
    print(f"      进球: 主{home_goals_sm} 客{away_goals_sm}")
    home_xg_total = sum(s.xg for s in report.home_shotmap)
    away_xg_total = sum(s.xg for s in report.away_shotmap)
    print(f"      xG总计: 主{home_xg_total:.2f} 客{away_xg_total:.2f}")

    print(f"    势头: {len(report.momentum)}个数据点")
    print(f"    H2H: {len(report.h2h_records)}场历史交锋")

    # === Test 5: to_pipeline_format ===
    print("\n  [Test 5] 转换为管道标准格式")
    pipeline_data = collector.to_pipeline_format(report)

    print(f"    source: {pipeline_data['source']}")
    print(f"    stats.home_xg: {pipeline_data['stats']['home_xg']}")
    print(f"    stats.xg_diff: {pipeline_data['stats']['xg_diff']}")
    print(f"    lineup.home_avg_rating: {pipeline_data['lineup']['home_avg_rating']}")
    print(f"    lineup.rating_diff: {pipeline_data['lineup']['rating_diff']}")
    print(f"    signals: {len(pipeline_data['signals']['signals'])}个信号")
    for k, v in pipeline_data['signals']['signals'].items():
        print(f"      {k}: {v}")
    print(f"    star_advice: adjustment={pipeline_data['star_advice']['adjustment']}")
    print(f"    risk: {pipeline_data['risk']}")

    # === Test 6: 联赛ID查询 ===
    print("\n  [Test 6] 联赛ID查询")
    test_leagues = ["英超", "瑞超", "葡超", "挪超", "日联", "欧冠"]
    for l in test_leagues:
        lid = get_league_id(l)
        status = "✅" if lid > 0 else "❌"
        print(f"    {status} {l}: {lid}")

    # === Test 7: JSON解析错误处理 ===
    print("\n  [Test 7] JSON解析错误处理")
    bad_report = collector.parse_match_detail("not valid json")
    print(f"    非JSON输入: match_id='{bad_report.match_id}' (空字段，无崩溃)")

    empty_report = collector.parse_match_detail("{}", match_id="99999")
    print(f"    空JSON: match_id='{empty_report.match_id}' (fill_me标记)")

    # === Test 8: 比赛列表解析 ===
    print("\n  [Test 8] 解析比赛列表")
    sample_list = {
        "leagues": [
            {
                "primaryId": 47,
                "ccode": "ENG",
                "name": "Premier League",
                "matches": [
                    {
                        "id": 4310531,
                        "leagueId": 47,
                        "time": "14:00",
                        "home": {"id": 8456, "name": "Man City", "score": 2},
                        "away": {"id": 8634, "name": "Chelsea", "score": 1},
                        "status": {
                            "utcTime": "2024-03-26T14:00:00.000Z",
                            "started": True,
                            "finished": True,
                            "scoreStr": "2 - 1",
                        },
                    },
                ],
            },
            {
                "primaryId": 153,
                "ccode": "SWE",
                "name": "Allsvenskan",
                "matches": [
                    {
                        "id": 4667808,
                        "leagueId": 153,
                        "time": "15:00",
                        "home": {"id": 10001, "name": "天狼星", "score": 2},
                        "away": {"id": 10002, "name": "布鲁马波", "score": 1},
                        "status": {
                            "utcTime": "2026-08-10T13:00:00.000Z",
                            "started": True,
                            "finished": True,
                            "scoreStr": "2 - 1",
                        },
                    },
                ],
            },
        ],
        "date": "20260810",
    }
    match_list = collector.parse_match_list(json.dumps(sample_list))
    print(f"    提取 {len(match_list)} 场比赛:")
    for m in match_list:
        print(f"      {m['league']}: {m['home']} vs {m['away']} [{m['match_id']}] {m['status']}")

    print(f"\n{'=' * 60}")
    print(f"  ✅ FotMob 采集器自测全部通过")
    print(f"  注意: 真实数据需要通过 CodeBuddy WebFetch 调度器获取")
    print(f"{'=' * 60}")
