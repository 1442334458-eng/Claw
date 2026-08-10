"""
27场全量批量测试 - 使用修复后的 main.py
"""
import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from main import DataAggregator

# 全部27场比赛 (来自竞彩截图)
ALL_MATCHES = [
    # 日职联
    ("东京绿茵", "川崎前锋", "日职联", "Tokyo"),
    ("长崎航海", "京都不死鸟", "日职联", "Nagasaki"),
    # 日职乙
    ("山形山神", "枥木城", "日职乙", "Yamagata"),
    # 荷甲
    ("鹿特丹斯巴达", "费耶诺德", "荷甲", "Rotterdam"),
    ("兹沃勒", "阿贾克斯", "荷甲", "Zwolle"),
    ("格罗宁根", "乌德勒支", "荷甲", "Groningen"),
    ("海伦芬", "特温特", "荷甲", "Heerenveen"),
    # 德乙
    ("圣保利", "菲尔特", "德乙", "Hamburg"),
    ("纽伦堡", "德累斯顿", "德乙", "Nuremberg"),
    # 瑞典超
    ("哈马比", "赫根", "瑞典超", "Stockholm"),
    ("哈尔姆斯塔德", "哥德堡盖斯", "瑞典超", "Halmstad"),
    ("IFK哥德堡", "卡尔马", "瑞典超", "Gothenburg"),
    ("马尔默", "代格福什", "瑞典超", "Malmo"),
    ("天狼星", "布洛马波卡纳", "瑞典超", "Uppsala"),
    ("米亚尔比", "埃尔夫斯堡", "瑞典超", "Hallevik"),
    ("奥尔格里特", "索尔纳", "瑞典超", "Gothenburg"),
    ("瓦斯特拉斯", "尤尔加登", "瑞典超", "Vasteras"),
    # 芬超
    ("库奥皮奥", "TPS图尔", "芬超", "Kuopio"),
    ("AC奥卢", "赫尔辛基", "芬超", "Oulu"),
    # 挪超
    ("汉坎", "奥勒松", "挪超", "Hamar"),
    ("克里斯蒂安松", "莫尔德", "挪超", "Kristiansund"),
    # 葡超
    ("波尔图", "阿尔维卡", "葡超", "Porto"),
    ("本菲卡", "维塞乌", "葡超", "Lisbon"),
    ("吉维森特", "里奥阿维", "葡超", "Barcelos"),
    ("摩雷伦斯", "布拉加", "葡超", "Moreira de Conegos"),
    # 澳超
    ("墨尔本胜利", "麦克阿瑟FC", "澳超", "Melbourne"),
    # 友谊赛(英冠背景)
    ("诺丁汉森林", "富勒姆", "英冠", "Nottingham"),
]

def main():
    aggregator = DataAggregator(force_websearch=True)
    
    results = []
    start_time = time.time()
    
    for i, (home, away, league, city) in enumerate(ALL_MATCHES):
        elapsed = time.time() - start_time
        eta = (elapsed / (i + 1)) * (len(ALL_MATCHES) - i - 1) if i > 0 else 0
        
        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(ALL_MATCHES)}] {home} vs {away} ({league}) | 已用{elapsed:.0f}s | 剩余{eta:.0f}s")
        print(f"{'='*60}")
        
        try:
            match = aggregator.aggregate_match(home, away, league, city=city)
            aggregator.save_match(match)
            
            # 提取质量元数据
            qm = match._quality_meta if hasattr(match, '_quality_meta') and match._quality_meta else {}
            tier = match.data_quality_tier
            
            results.append({
                "match": f"{home} vs {away}",
                "league": league,
                "tier": tier,
                "ws_pct": qm.get("ws_success_rate", 0),
                "ws_ok": qm.get("ws_success_count", 0),
                "ws_total": qm.get("ws_total_count", 0),
                "has_odds": qm.get("has_realtime_odds", False),
            })
            
            print(f"  ✅ {tier} | WS:{qm.get('ws_success_rate',0):.0f}% | 赔率:{'✅' if qm.get('has_realtime_odds') else '❌'}")
            
        except Exception as e:
            print(f"  ❌ 失败: {e}")
            results.append({
                "match": f"{home} vs {away}",
                "league": league,
                "tier": "❌ 异常",
                "ws_pct": 0,
                "ws_ok": 0,
                "ws_total": 0,
                "has_odds": False,
                "error": str(e)[:100]
            })
    
    # 输出汇总
    total_time = time.time() - start_time
    print(f"\n{'='*70}")
    print(f"📊 27场全量测试结果")
    print(f"总耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"{'='*70}")
    
    tier_counts = {"🟢 AAA": 0, "🟢 AA": 0, "🟡 A": 0, "🟠 B": 0, "⚪ C": 0, "❌ 异常": 0}
    for r in results:
        t = r.get("tier", "❌ 异常")
        tier_counts[t] = tier_counts.get(t, 0) + 1
    
    print("\n数据质量分布:")
    for tier, count in tier_counts.items():
        if count > 0:
            bar = "█" * count
            print(f"  {tier}: {count:2d}场 {bar}")
    
    ws_avg = sum(r["ws_pct"] for r in results if r["tier"] != "❌ 异常") / max(1, len([r for r in results if r["tier"] != "❌ 异常"]))
    odds_count = sum(1 for r in results if r.get("has_odds"))
    print(f"\n  WebSearch平均成功率: {ws_avg:.1f}%")
    print(f"  The Odds API覆盖: {odds_count}/{len(ALL_MATCHES)}场")
    
    # 保存汇总
    summary = {
        "test_time": datetime.now().isoformat(),
        "total_matches": len(ALL_MATCHES),
        "total_time_seconds": round(total_time),
        "tier_distribution": tier_counts,
        "avg_websarch_success": round(ws_avg, 1),
        "odds_api_coverage": f"{odds_count}/{len(ALL_MATCHES)}",
        "details": results
    }
    
    output_path = os.path.join("cache", "27场全量测试汇总.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n💾 汇总已保存: {output_path}")

if __name__ == "__main__":
    main()
