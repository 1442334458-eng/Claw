#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  管道 v2.1 集成测试
  三场比赛: 1001天狼星 / 1002韦斯特罗斯 / 1003圣克拉拉
============================================

测试范围:
  1. multi_source_odds.py — 多源赔率采集(模拟)
  2. cross_validate.py — 交叉验证引擎
  3. qiumiwu_collector.py — 球迷屋数据采集
  4. fotmob_collector.py — FotMob数据采集
  5. 集成数据流: 采集→验证→信号提取→风险评估

模拟数据来源:
  - 竞彩官方赔率来自 8-9 实际分析报告
  - 百家赔率基于合理范围估算
  - 球迷屋/FotMob 使用模拟数据

日期: 2026-08-10
"""

import json
import sys
import logging
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from multi_source_odds import (
    MultiSourceOddsEngine, BookmakerOdds, SourceType, Freshness,
    quick_collect as odds_quick_collect,
)
from cross_validate import CrossValidator, quick_validate
from qiumiwu_collector import QiumiwuCollector
from fotmob_collector import FotMobCollector

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)


# ============================================
# 三场比赛定义
# ============================================

MATCHES = [
    {
        "match_id": "1001",
        "home": "天狼星",
        "away": "布鲁马波",
        "home_cn": "布鲁马波卡纳",
        "league": "瑞典超",
        "league_id": 153,
        "kickoff": "2026-08-10T22:00",
        # 实际竞彩赔率 (来自8-9分析报告)
        "jc_odds": {"home_win": 1.19, "draw": 5.80, "away_win": 8.55},
        # 百家估算
        "estimated_odds": [
            {"bookmaker": "竞彩官方", "home": 1.19, "draw": 5.80, "away": 8.55},
            {"bookmaker": "Pinnacle", "home": 1.22, "draw": 5.50, "away": 7.80, "asian_opening": -1.5, "asian_current": -1.5},
            {"bookmaker": "Bet365", "home": 1.25, "draw": 5.75, "away": 8.00},
            {"bookmaker": "澳彩", "home": 1.18, "draw": 6.00, "away": 9.00, "asian_opening": -1.5, "asian_current": -1.5},
            {"bookmaker": "威廉希尔", "home": 1.24, "draw": 5.80, "away": 8.20},
            {"bookmaker": "立博", "home": 1.21, "draw": 5.90, "away": 8.40},
            {"bookmaker": "盈禾", "home": 1.20, "draw": 5.85, "away": 8.60},
        ],
    },
    {
        "match_id": "1002",
        "home": "韦斯特罗斯",
        "away": "尤尔加登",
        "league": "瑞典超",
        "league_id": 153,
        "kickoff": "2026-08-10T22:00",
        "jc_odds": {"home_win": 2.40, "draw": 3.20, "away_win": 2.65},
        "estimated_odds": [
            {"bookmaker": "竞彩官方", "home": 2.40, "draw": 3.20, "away": 2.65},
            {"bookmaker": "Pinnacle", "home": 2.45, "draw": 3.15, "away": 2.70},
            {"bookmaker": "Bet365", "home": 2.42, "draw": 3.25, "away": 2.68},
            {"bookmaker": "澳彩", "home": 2.38, "draw": 3.28, "away": 2.60},
            {"bookmaker": "威廉希尔", "home": 2.45, "draw": 3.22, "away": 2.65},
            {"bookmaker": "立博", "home": 2.43, "draw": 3.18, "away": 2.70},
            {"bookmaker": "盈禾", "home": 2.42, "draw": 3.20, "away": 2.68},
        ],
    },
    {
        "match_id": "1003",
        "home": "圣克拉拉",
        "away": "葡萄牙国民",
        "league": "葡超",
        "league_id": 61,
        "kickoff": "2026-08-10T22:00",
        "jc_odds": {"home_win": 1.45, "draw": 3.80, "away_win": 6.00},
        "estimated_odds": [
            {"bookmaker": "竞彩官方", "home": 1.45, "draw": 3.80, "away": 6.00},
            {"bookmaker": "Pinnacle", "home": 1.48, "draw": 3.75, "away": 5.80},
            {"bookmaker": "Bet365", "home": 1.47, "draw": 3.85, "away": 5.90},
            {"bookmaker": "澳彩", "home": 1.42, "draw": 4.00, "away": 6.20},
            {"bookmaker": "威廉希尔", "home": 1.48, "draw": 3.78, "away": 5.85},
            {"bookmaker": "立博", "home": 1.46, "draw": 3.82, "away": 5.95},
            {"bookmaker": "盈禾", "home": 1.44, "draw": 3.85, "away": 6.10},
        ],
    },
]


# ============================================
# 测试 Runner
# ============================================

def test_multi_source_odds(match):
    """测试1: 多源赔率采集"""
    home, away, mid, league = match['home'], match['away'], match['match_id'], match['league']
    odds_list = match['estimated_odds']

    print(f"\n  ┌─ 多源赔率采集")
    result = odds_quick_collect(mid, home, away, league)

    print(f"  │  数据源: {result['sources']} ({', '.join(result['source_types'])})")
    print(f"  │  百家范围: 主{result['home_win_range']} 平{result['draw_range']} 客{result['away_win_range']}")

    bm_list = result['bookmakers']
    filled = [b for b in bm_list if b['spf'][0] > 0]
    unfilled = [b for b in bm_list if b['spf'][0] == 0]
    print(f"  │  已填充: {len(filled)}家 | 待采集: {len(unfilled)}家")

    for bm in filled[:5]:
        print(f"  │    {bm['name']:8s}: {bm['spf'][0]:.2f} / {bm['spf'][1]:.2f} / {bm['spf'][2]:.2f}  [{bm['source']}]")

    # 手动填充实际赔率
    od = {b['bookmaker']: b for b in odds_list}
    engine = MultiSourceOddsEngine()
    engine.fill_report = lambda r, d: r  # skip for now

    return result


def test_cross_validate(match):
    """测试2: 交叉验证"""
    home, away, mid = match['home'], match['away'], match['match_id']
    odds_list = match['estimated_odds']

    print(f"\n  ┌─ 多源交叉验证")
    result = quick_validate(mid, home, away, odds_list)

    print(f"  │  共识度: {result['consensus']['level']} (CV={result['consensus']['cv']})")
    print(f"  │  均赔: {result['consensus']['mean_spf']}")
    print(f"  │  数据源: {len(result['consensus']['sources_used'])}家")

    print(f"  │  异常检测: {len(result['outliers'])}个异常源")
    for o in result['outliers']:
        print(f"  │    ⚠️ {o['bookmaker']}: {o['field']}={o['sigma']}σ → {o['recommendation'][:50]}")

    print(f"  │  加权隐含概率:")
    wp = result['weighted_prob']
    print(f"  │    主: {wp['home']:.2%}  平: {wp['draw']:.2%}  客: {wp['away']:.2%}")

    print(f"  │  DOIT增强:")
    d = result['doit']
    print(f"  │    mean={d['mean']:.4f}  std={d['std']:.4f}  signal={d['signal']}  confidence={d['confidence']}")
    print(f"  │    95%CI: [{d['range_95ci'][0]:.4f}, {d['range_95ci'][1]:.4f}]")

    print(f"  │  风险: {result['risk']}")
    print(f"  │  因子: {'; '.join(result['risk_factors'])}")
    print(f"  │  星级调整: {result['star_adjustment']}")
    print(f"  │  建议: {result['advice']}")

    return result


def test_qiumiwu(match):
    """测试3: 球迷屋数据采集"""
    home, away, mid, league = match['home'], match['away'], match['match_id'], match['league']

    print(f"\n  ┌─ 球迷屋数据采集")
    collector = QiumiwuCollector()

    # 生成采集任务
    task = collector.generate_fetch_task(mid, home, away, league)

    print(f"  │  URL: {task['url']}")
    print(f"  │  方法: {task['method']}")
    print(f"  │  预期数据: {len(task['expected_data'])}项")
    for f in task['expected_data']:
        print(f"  │    ✅ {f}")

    # 模拟解析 (用self-test中的sample数据)
    sample_html = f"""
    伤停球员
    {home}
    球员A 中场 7号 累计黄牌停赛 停赛 -
    {away}
    球员B 前锋 17号 脚踝骨折 受伤 04-18
    """
    report = collector.parse_match_page(sample_html, mid, home, away, league)

    print(f"  │  伤停提取: 主{len(report.home_report.injuries)}人 客{len(report.away_report.injuries)}人")

    return task


def test_fotmob(match):
    """测试4: FotMob 数据采集"""
    home, away, mid, league = match['home'], match['away'], match['match_id'], match['league']

    print(f"\n  ┌─ FotMob 数据采集")
    collector = FotMobCollector()

    # 生成任务
    task = collector.generate_match_detail_task(mid, home, away, league)
    discovery = collector.generate_match_id_discovery_task(home, away, "20260810", league)

    print(f"  │  详情URL: {task['url']}")
    print(f"  │  方法: {task['method']}")
    print(f"  │  预期数据: {len(task['expected_data'])}项")
    for f in task['expected_data'][:4]:
        print(f"  │    ✅ {f}")
    print(f"  │    ... 共{len(task['expected_data'])}项")

    print(f"  │  ID发现链: {len(discovery['chain'])}步")

    return task


def test_integration(match):
    """测试5: 数据流集成"""
    home, away, mid, league = match['home'], match['away'], match['match_id'], match['league']
    odds_list = match['estimated_odds']
    jc = match['jc_odds']

    print(f"\n  ┌─ 集成数据流")

    # Step 1: 赔率采集
    print(f"  │  [1/5] 赔率采集 → {len(odds_list)}家")

    # Step 2: 交叉验证
    cv = quick_validate(mid, home, away, odds_list)
    consensus = cv['consensus']['level']
    risk = cv['risk']
    doit = cv['doit']
    print(f"  │  [2/5] 交叉验证 → 共识:{consensus} 风险:{risk} DOIT:{doit['mean']:.4f}({doit['signal']})")

    # Step 3: 球迷屋 (生成任务标记)
    qiwu = QiumiwuCollector()
    qw_task = qiwu.generate_fetch_task(mid, home, away, league)
    print(f"  │  [3/5] 球迷屋 → 任务已生成 ({qw_task['url'][:40]}...)")

    # Step 4: FotMob (生成任务标记)
    fotmob = FotMobCollector()
    fm_task = fotmob.generate_match_detail_task(mid, home, away, league)
    print(f"  │  [4/5] FotMob → 任务已生成 ({fm_task['url'][:40]}...)")

    # Step 5: 综合信号汇总
    print(f"  │  [5/5] 信号汇总 →")

    signals = []

    # 赔率信号
    if odd_diff := jc['home_win'] - jc['away_win']:
        if jc['home_win'] < 1.30:
            signals.append(f"深盘 (主胜{jc['home_win']:.2f})")

    # 共识度信号
    if consensus == "divergent":
        signals.append("多源分歧 → 降2星+双选")
    elif consensus == "low":
        signals.append("多源分歧较大 → 降1星")

    # DOIT信号
    if doit['signal'] == "strong":
        signals.append(f"DOIT强防平 ({doit['mean']:.4f} > 0.8)")
    elif doit['signal'] == "moderate":
        signals.append(f"DOIT二星防平 ({doit['mean']:.4f} > 0.5)")

    # 异常源
    if len(cv['outliers']) > 0:
        signals.append(f"异常源{len(cv['outliers'])}个 → 额外降星")

    # 联赛特殊
    if league == "葡超":
        signals.append("葡超首轮黑名单 → 最高⭐⭐⭐")

    if not signals:
        signals.append("无明显异常信号")

    for s in signals:
        print(f"  │      📶 {s}")

    # 星级联动
    star_adj = cv['star_adjustment']
    base_stars = 4  # 假设基础4星
    final_stars = max(1, base_stars + star_adj)
    print(f"  │  星级: {base_stars} → {final_stars} (调整{star_adj:+d})")

    # 综合建议
    advice_parts = [cv['advice']]
    if "深盘" in str(signals):
        advice_parts.append("深盘防平")
    if doit['signal'] in ("strong", "moderate"):
        advice_parts.append("建议双选")
    print(f"  │  建议: {' | '.join(advice_parts)}")

    return {
        "consensus": consensus,
        "risk": risk,
        "doit": doit,
        "signals": signals,
        "star_adjustment": star_adj,
        "final_stars": final_stars,
    }


# ============================================
# 主测试流程
# ============================================

def main():
    print("=" * 70)
    print("  管道 v2.1 集成测试 — 三场比赛")
    print(f"  日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 70)

    all_results = {}

    for i, match in enumerate(MATCHES):
        home, away, mid = match['home'], match['away'], match['match_id']
        league = match['league']

        print(f"\n{'─' * 70}")
        print(f"  [{i+1}/3] {mid}  {home} vs {away} ({league})")
        print(f"{'─' * 70}")

        # 模块测试
        test_multi_source_odds(match)
        cv_result = test_cross_validate(match)
        test_qiumiwu(match)
        test_fotmob(match)

        # 集成数据流
        int_result = test_integration(match)

        all_results[mid] = int_result

    # === 汇总 ===
    print(f"\n\n{'═' * 70}")
    print(f"  📊 三场汇总对比")
    print(f"{'═' * 70}")

    print(f"\n  {'比赛':<25s} {'共识':<10s} {'DOIT':<8s} {'DOIT信号':<10s} {'风险':<8s} {'星级':<6s}")
    print(f"  {'─' * 25} {'─' * 10} {'─' * 8} {'─' * 10} {'─' * 8} {'─' * 6}")

    for match in MATCHES:
        mid = match['match_id']
        home = match['home']
        away = match['away']
        r = all_results[mid]

        name = f"{home} vs {away}"
        cons = r['consensus']
        doit_mean = r['doit']['mean']
        doit_sig = r['doit']['signal']
        risk = r['risk']
        stars = r['final_stars']

        print(f"  {name:<25s} {cons:<10s} {doit_mean:<8.4f} {doit_sig:<10s} {risk:<8s} {'⭐'*stars:<6s}")

    # 信号汇总
    print(f"\n  📶 全部信号:")
    for match in MATCHES:
        mid = match['match_id']
        r = all_results[mid]
        name = f"{match['home']} vs {match['away']}"
        print(f"    [{mid}] {name}:")
        for s in r['signals']:
            print(f"      {s}")

    print(f"\n{'═' * 70}")
    print(f"  ✅ 集成测试完成")
    print(f"  模块: multi_source_odds + cross_validate + qiumiwu + fotmob")
    print(f"  数据流: 采集 → 验证 → 信号 → 星级 → 建议")
    print(f"{'═' * 70}")

    return all_results


if __name__ == "__main__":
    main()
