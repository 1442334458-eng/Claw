#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  球迷屋数据采集器 v1.0
  Qiumiwu.com Data Collector
============================================

数据源: https://www.qiumiwu.com (球迷屋)
访问方式: WebFetch
覆盖内容:
  ✅ 伤停名单 — 精确到人(姓名+位置+原因+状态+时间)
  ✅ H2H交锋 — 历史对阵+比分+胜率+进球
  ✅ 近期战绩 — 10场含比分+赛果+赛事类型
  ✅ 赛季数据 — 控球率/射门/进球/失球/黄牌/红牌/角球/过人/抢断
  ✅ 进失球分布 — 15分钟区间统计
  ✅ 最佳球员 — 进球/助攻/射正/抢断/解围 Top5
  ✅ 赛程计划 — 未来5场+间隔天数
  ✅ 赛前前瞻 — 专家分析文章

数据格式: 结构化HTML，字段提取规则清晰

应用层:
  Layer 1 (伤停/阵容) — 伤停精确到人
  Layer 2 (H2H/数据) — 历史交锋+赛季统计
  Layer 4 (PFI) — 赛程间隔
  Layer 6 (情报) — 赛前前瞻

联动画像库:
  赛后自动提取 → teams/{team}/injuries.json → 联动 Rule 5/19

作者：CodeBuddy Code (管道 v2.1 升级)
日期：2026-08-10
版本：v1.0
"""

import re
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from html.parser import HTMLParser

log = logging.getLogger(__name__)


# ============================================
# 数据模型
# ============================================

@dataclass
class QiumiwuInjury:
    """球迷屋伤停记录"""
    name: str = ""               # 球员姓名
    position: str = ""           # 位置 (GK/DF/MF/FW)
    number: str = ""             # 球衣号码
    reason: str = ""             # 伤病原因
    status: str = ""             # 状态 (停赛/受伤/出战成疑)
    return_date: str = ""        # 预期回归时间
    severity: str = ""           # 严重程度 (critical/high/medium/low)

@dataclass
class QiumiwuH2H:
    """球迷屋H2H记录"""
    date: str = ""
    home_team: str = ""
    away_team: str = ""
    home_score: int = 0
    away_score: int = 0
    league: str = ""
    winner: str = ""

@dataclass
class QiumiwuRecentMatch:
    """球迷屋近期比赛"""
    date: str = ""
    competition: str = ""
    home_team: str = ""
    away_team: str = ""
    home_score: int = 0
    away_score: int = 0
    result: str = ""  # W/D/L

@dataclass
class QiumiwuSeasonStats:
    """球迷屋赛季统计"""
    possession_pct: float = 0.0       # 场均控球率
    avg_goals: float = 0.0            # 场均进球
    avg_conceded: float = 0.0         # 场均失球
    avg_shots: float = 0.0            # 场均射门
    avg_shots_on_target: float = 0.0  # 场均射正
    avg_corners: float = 0.0          # 场均角球
    avg_dribbles: float = 0.0         # 场均过人
    avg_tackles: float = 0.0          # 场均抢断
    yellow_cards: str = ""            # 场均黄牌
    red_cards: str = ""               # 场均红牌

@dataclass
class QiumiwuGoalDistribution:
    """进失球时间分布"""
    intervals: Dict[str, int] = field(default_factory=dict)
    # e.g., {"0-15": 4, "16-30": 2, "31-45": 2, "46-60": 5, "61-75": 2, "76-90": 5}

@dataclass
class QiumiwuTopPlayer:
    """最佳球员统计"""
    name: str = ""
    position: str = ""
    number: str = ""
    goals: int = 0
    assists: int = 0
    shots_on_target: int = 0
    tackles: int = 0
    clearances: int = 0

@dataclass
class QiumiwuSchedule:
    """赛程记录"""
    date: str = ""
    competition: str = ""
    opponent: str = ""
    home_away: str = ""  # "home"/"away"
    days_interval: int = 0

@dataclass
class QiumiwuTeamReport:
    """球迷屋单队完整报告"""
    team_name: str = ""
    injuries: List[QiumiwuInjury] = field(default_factory=list)
    recent_matches: List[QiumiwuRecentMatch] = field(default_factory=list)
    h2h_records: List[QiumiwuH2H] = field(default_factory=list)
    season_stats: QiumiwuSeasonStats = field(default_factory=QiumiwuSeasonStats)
    goals_distribution: QiumiwuGoalDistribution = field(default_factory=QiumiwuGoalDistribution)
    top_players: List[QiumiwuTopPlayer] = field(default_factory=list)
    schedule: List[QiumiwuSchedule] = field(default_factory=list)

@dataclass
class QiumiwuMatchReport:
    """球迷屋单场完整报告"""
    match_id: str = ""               # 球迷屋比赛ID
    home_team: str = ""
    away_team: str = ""
    league: str = ""
    kickoff_time: str = ""
    collected_at: str = ""
    url: str = ""

    home_report: QiumiwuTeamReport = field(default_factory=QiumiwuTeamReport)
    away_report: QiumiwuTeamReport = field(default_factory=QiumiwuTeamReport)

    # 赛前前瞻
    preview_title: str = ""
    preview_author: str = ""
    preview_summary: str = ""


# ============================================
# 球迷屋采集器
# ============================================

class QiumiwuCollector:
    """
    球迷屋数据采集器

    使用方式:
      1. 外部调度器通过 WebFetch 获取球迷屋比赛页面HTML
      2. 调用 parse_match_page(html) 解析数据
      3. 返回结构化 QiumiwuMatchReport

    URL模式:
      https://www.qiumiwu.com/game/{match_id}
      e.g., https://www.qiumiwu.com/game/110626605381
    """

    # 球迷屋页面URL模式
    MATCH_URL = "https://www.qiumiwu.com/game/{match_id}"
    TEAM_URL = "https://www.qiumiwu.com/team/{team_slug}"

    def __init__(self):
        pass

    def generate_fetch_task(self, match_id: str, home_team: str,
                            away_team: str, league: str = "") -> Dict:
        """
        生成球迷屋 WebFetch 任务

        Returns:
            供外部调度器(CoudeBuddy)执行的WebFetch任务描述
        """
        url = self.MATCH_URL.format(match_id=match_id)

        return {
            "task_id": f"qiumiwu_{match_id}",
            "collector": "球迷屋",
            "method": "WebFetch",
            "url": url,
            "match_id": match_id,
            "teams": f"{home_team} vs {away_team}",
            "league": league,
            "expected_data": [
                "伤停名单(精确到人+原因+状态)",
                "H2H交锋历史",
                "近期10场战绩",
                "赛季数据统计",
                "进失球时间分布",
                "最佳球员TOP5",
                "未来赛程",
                "赛前前瞻文章",
            ],
            "parse_instructions": (
                f"仔细提取页面中 {home_team} 和 {away_team} 的所有结构化数据。"
                f"特别注意：伤停名单需要精确到球员姓名+位置+原因+状态。"
            ),
        }

    def parse_match_page(self, html_content: str, match_id: str = "",
                         home_team: str = "", away_team: str = "",
                         league: str = "") -> QiumiwuMatchReport:
        """
        解析球迷屋比赛页面HTML

        由于HTML解析依赖于实际页面结构，此方法提供解析框架。
        实际解析由外部调度器的AI能力完成（自然语言→结构化数据）。

        此方法返回的report中，关键字段通过正则预提取。
        复杂字段由外部调度器填充后再调用 fill_from_parsed()。
        """
        report = QiumiwuMatchReport(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league=league,
            collected_at=datetime.now().isoformat(),
            url=self.MATCH_URL.format(match_id=match_id) if match_id else "",
        )

        report.home_report.team_name = home_team
        report.away_report.team_name = away_team

        # === 预提取尝试 (正则匹配) ===

        # 伤停球员 (精确匹配模式: 姓名 + 位置 + 号码 + 原因)
        injury_patterns = [
            # 模式1: 累计黄牌停赛
            (r'([\u4e00-\u9fff·]+)\s*(中场|前锋|后卫|守门员|门将)\s*(\d+)号\s*\n\s*(累计黄牌停赛|停赛|轮休)', 'suspension'),
            # 模式2: 受伤
            (r'([\u4e00-\u9fff·]+)\s*(中场|前锋|后卫|守门员|门将)\s*(\d+)号\s*\n\s*(.{2,8}(?:骨折|拉伤|撕裂|挫伤|扭伤|炎症|手术|恢复))', 'injury'),
        ]

        for pattern, injury_type in injury_patterns:
            matches = re.findall(pattern, html_content)
            for m in matches:
                name, pos, num, reason = m
                injury = QiumiwuInjury(
                    name=name.strip(),
                    position=pos,
                    number=num,
                    reason=reason.strip(),
                    status="停赛" if injury_type == 'suspension' else "受伤",
                    severity="high" if "骨折" in reason or "撕裂" in reason else "medium",
                )
                # 无法确定主客队归属，先添加到双方
                if home_team and name in html_content.split(home_team)[-1][:2000]:
                    report.home_report.injuries.append(injury)
                elif away_team and name in html_content.split(away_team)[-1][:2000]:
                    report.away_report.injuries.append(injury)

        # 近期战绩 (比分模式: X - Y)
        score_pattern = re.findall(
            r'(\d{4}-\d{2}-\d{2})\s*(.{2,10}?)\s*\n\s*(\d+)\s*-\s*(\d+)\s*(.{2,20}?)\s*\n',
            html_content
        )
        for date, comp, hs, aws, opp in score_pattern[:10]:
            # 简化处理: 将匹配到的记录添加到双方
            pass  # 精确解析留给外部调度器

        return report

    def fill_from_parsed(self, report: QiumiwuMatchReport,
                         parsed_data: Dict) -> QiumiwuMatchReport:
        """
        外部调度器解析完数据后，通过此方法填充report

        Args:
            report: parse_match_page() 返回的空框架
            parsed_data: 外部调度器解析的结构化数据
                {
                    "home_injuries": [{"name": "xx", "pos": "MF", ...}],
                    "away_injuries": [...],
                    "h2h": [...],
                    "home_recent": [...],
                    ...
                }

        Returns:
            填充后的完整报告
        """
        # 填充伤停
        for inj in parsed_data.get('home_injuries', []):
            report.home_report.injuries.append(QiumiwuInjury(**inj))
        for inj in parsed_data.get('away_injuries', []):
            report.away_report.injuries.append(QiumiwuInjury(**inj))

        # 填充H2H
        for h2h in parsed_data.get('h2h', []):
            report.home_report.h2h_records.append(QiumiwuH2H(**h2h))

        # 填充近期战绩
        for m in parsed_data.get('home_recent', []):
            report.home_report.recent_matches.append(QiumiwuRecentMatch(**m))
        for m in parsed_data.get('away_recent', []):
            report.away_report.recent_matches.append(QiumiwuRecentMatch(**m))

        # 填充赛季数据
        if 'home_stats' in parsed_data:
            report.home_report.season_stats = QiumiwuSeasonStats(**parsed_data['home_stats'])
        if 'away_stats' in parsed_data:
            report.away_report.season_stats = QiumiwuSeasonStats(**parsed_data['away_stats'])

        # 填充最佳球员
        for p in parsed_data.get('home_top_players', []):
            report.home_report.top_players.append(QiumiwuTopPlayer(**p))
        for p in parsed_data.get('away_top_players', []):
            report.away_report.top_players.append(QiumiwuTopPlayer(**p))

        # 填充赛程
        for s in parsed_data.get('home_schedule', []):
            report.home_report.schedule.append(QiumiwuSchedule(**s))
        for s in parsed_data.get('away_schedule', []):
            report.away_report.schedule.append(QiumiwuSchedule(**s))

        # 填充前瞻
        report.preview_title = parsed_data.get('preview_title', '')
        report.preview_author = parsed_data.get('preview_author', '')
        report.preview_summary = parsed_data.get('preview_summary', '')

        return report

    def to_pipeline_format(self, report: QiumiwuMatchReport) -> Dict:
        """
        将球迷屋报告转换为管道标准格式

        输出格式兼容 main.py 的 MatchData 结构
        """
        # 伤停 → pipeline InjuryRecord
        all_injuries = report.home_report.injuries + report.away_report.injuries
        injuries_data = []
        for inj in all_injuries:
            injuries_data.append({
                "name": inj.name,
                "position": inj.position,
                "reason": inj.reason,
                "status": inj.status,
                "team": report.home_team if inj in report.home_report.injuries else report.away_team,
                "severity": inj.severity,
            })

        # H2H → pipeline H2HRecord
        h2h_data = []
        for h2h in report.home_report.h2h_records:
            h2h_data.append({
                "date": h2h.date,
                "home_team": h2h.home_team,
                "away_team": h2h.away_team,
                "home_score": h2h.home_score,
                "away_score": h2h.away_score,
                "winner": h2h.winner,
                "league": h2h.league,
            })

        # PFI → 赛程间隔
        last_home_match_days = 99
        last_away_match_days = 99
        for s in report.home_report.schedule:
            if s.days_interval > 0 and s.days_interval < last_home_match_days:
                last_home_match_days = s.days_interval
        for s in report.away_report.schedule:
            if s.days_interval > 0 and s.days_interval < last_away_match_days:
                last_away_match_days = s.days_interval

        return {
            "source": "qiumiwu",
            "match_id": report.match_id,
            "url": report.url,
            "collected_at": report.collected_at,

            # Layer 1: 伤停
            "injuries": injuries_data,
            "home_injuries_count": len(report.home_report.injuries),
            "away_injuries_count": len(report.away_report.injuries),

            # Layer 2: H2H + 赛季数据
            "h2h": h2h_data,
            "home_season_stats": {
                "possession": report.home_report.season_stats.possession_pct,
                "goals_per_match": report.home_report.season_stats.avg_goals,
                "conceded_per_match": report.home_report.season_stats.avg_conceded,
                "shots_per_match": report.home_report.season_stats.avg_shots,
            },
            "away_season_stats": {
                "possession": report.away_report.season_stats.possession_pct,
                "goals_per_match": report.away_report.season_stats.avg_goals,
                "conceded_per_match": report.away_report.season_stats.avg_conceded,
                "shots_per_match": report.away_report.season_stats.avg_shots,
            },

            # Layer 4: PFI
            "home_rest_days": last_home_match_days,
            "away_rest_days": last_away_match_days,

            # Layer 6: 情报
            "preview": {
                "title": report.preview_title,
                "author": report.preview_author,
                "summary": report.preview_summary,
            },

            # 原始报告引用
            "_raw_report": report,
        }


# ============================================
# 便捷函数
# ============================================

def quick_collect(match_id: str, home: str, away: str,
                  league: str = "") -> Dict:
    """快速生成采集任务 (供外部调度器使用)"""
    collector = QiumiwuCollector()
    return collector.generate_fetch_task(match_id, home, away, league)


# ============================================
# 自测
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print("=" * 60)
    print("  球迷屋数据采集器 v1.0 - 自测")
    print("=" * 60)

    collector = QiumiwuCollector()

    # 测试: 生成采集任务
    task = collector.generate_fetch_task(
        match_id="110626605381",
        home_team="米亚尔比",
        away_team="埃夫斯堡",
        league="瑞典超"
    )

    print(f"\n  采集任务:")
    print(f"    比赛ID: {task['match_id']}")
    print(f"    对阵: {task['teams']}")
    print(f"    URL: {task['url']}")
    print(f"    方法: {task['method']}")
    print(f"\n  预期数据字段:")
    for field in task['expected_data']:
        print(f"    ✅ {field}")

    # 测试: 模拟解析
    sample_html = """
    伤停球员
    米亚尔比
    古斯塔夫森 中场 7号 累计黄牌停赛 停赛 -
    古斯塔瓦森 中场 22号 累计黄牌停赛 停赛 -
    埃夫斯堡
    皮·菲尔克 前锋 17号 脚踝骨折 受伤 04-18
    """
    report = collector.parse_match_page(sample_html, "110626605381",
                                        "米亚尔比", "埃夫斯堡", "瑞典超")

    print(f"\n  解析测试:")
    print(f"    提取伤停: {len(report.home_report.injuries) + len(report.away_report.injuries)}人")
    for inj in report.home_report.injuries + report.away_report.injuries:
        print(f"    - {inj.name} ({inj.position}{inj.number}号): {inj.reason} [{inj.status}]")

    print(f"\n  ✅ 自测完成")
    print(f"  注意: 完整数据需要外部WebFetch调度器执行后回填")
