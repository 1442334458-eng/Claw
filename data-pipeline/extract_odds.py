"""
快速提取全部27场关键赔率 - 使用修正后的 team_name_map
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from main import DataAggregator

MATCHES = [
    # 日职联
    ("东京绿茵", "川崎前锋", "日职联"),
    ("长崎航海", "京都不死鸟", "日职联"),
    # 日职乙
    ("山形山神", "枥木城", "日职乙"),
    # 荷甲
    ("鹿特丹斯巴达", "费耶诺德", "荷甲"),
    ("兹沃勒", "阿贾克斯", "荷甲"),
    ("格罗宁根", "乌德勒支", "荷甲"),
    ("海伦芬", "特温特", "荷甲"),
    # 德乙
    ("圣保利", "菲尔特", "德乙"),
    ("纽伦堡", "德累斯顿", "德乙"),
    # 瑞典超
    ("哈马比", "赫根", "瑞典超"),
    ("哈尔姆斯塔德", "哥德堡盖斯", "瑞典超"),
    ("IFK哥德堡", "卡尔马", "瑞典超"),
    ("马尔默", "代格福什", "瑞典超"),
    ("天狼星", "布洛马波卡纳", "瑞典超"),
    ("米亚尔比", "埃尔夫斯堡", "瑞典超"),
    ("奥尔格里特", "索尔纳", "瑞典超"),
    ("瓦斯特拉斯", "尤尔加登", "瑞典超"),
    # 芬超
    ("库奥皮奥", "TPS图尔", "芬超"),
    ("AC奥卢", "赫尔辛基", "芬超"),
    # 挪超
    ("汉坎", "奥勒松", "挪超"),
    ("克里斯蒂安松", "莫尔德", "挪超"),
    # 葡超
    ("波尔图", "阿尔维卡", "葡超"),
    ("本菲卡", "维塞乌", "葡超"),
    ("吉维森特", "里奥阿维", "葡超"),
    ("摩雷伦斯", "布拉加", "葡超"),
    # 澳超
    ("墨尔本胜利", "麦克阿瑟FC", "澳超"),
    # 英冠
    ("诺丁汉森林", "富勒姆", "英冠"),
]

def main():
    agg = DataAggregator(force_websearch=True)
    results = []

    for home, away, league in MATCHES:
        try:
            match = agg.aggregate_match(home, away, league)
            results.append({
                "match": f"{home} vs {away}",
                "league": league,
                "tier": match.data_quality_tier or "?",
                "spf": {
                    "home": match.odds.home_win,
                    "draw": match.odds.draw,
                    "away": match.odds.away_win,
                },
                "asian": match.odds.asian_line if match.odds.asian_line else 0,
                "sources": match.data_sources,
            })
            print(f"  {home} vs {away:8s} [{league:4s}] {match.data_quality_tier or '?'} "
                  f"主{match.odds.home_win:.2f}/平{match.odds.draw:.2f}/客{match.odds.away_win:.2f}")
        except Exception as e:
            results.append({
                "match": f"{home} vs {away}",
                "league": league,
                "tier": "ERROR",
                "spf": {"home": 0, "draw": 0, "away": 0},
                "asian": 0,
                "error": str(e),
            })
            print(f"  {home} vs {away} [{league}] ERROR: {e}")

    # Save results
    output = {
        "extract_time": __import__('datetime').datetime.now().isoformat(),
        "total": len(results),
        "matches": results,
    }

    os.makedirs("cache", exist_ok=True)
    outpath = os.path.join("cache", "27场赔率提取.json")
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    aaa_count = sum(1 for r in results if r["tier"] == "🟢 AAA")
    print(f"\n总计: {len(results)}场, 🟢AAA: {aaa_count}场")
    print(f"已保存: {outpath}")

if __name__ == "__main__":
    main()
