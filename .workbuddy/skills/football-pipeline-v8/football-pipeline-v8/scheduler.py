#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  数据管道调度器 v1.0
  Pipeline Scheduler v1.0
============================================

功能：
  实现三轮渐进式数据采集策略（基于维京/博德100%命中验证的方法论）

  Round 1 (T-12h): 基线数据收集（伤停/H2H/PFI）
  Round 2 (T-6h):  动态信号跟进（阵容/赔率/天气）
  Round 3 (T-3h):  最终校准（新闻/首发/临盘赔率）

使用方法：
  python scheduler.py --matches "Viking vs Sarpsborg" --kickoff "2026-08-10 20:00"
  python scheduler.py --file matches_tomorrow.txt
  python scheduler.py --auto  (自动扫描未来48h比赛)

定时执行：
  Windows任务计划程序 → schtasks 创建定时任务
  或直接运行本脚本（内部支持延迟执行）

作者：CodeBuddy Code (铁律系统 v7.5.2.7)
日期：2026-08-09
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# 添加父目录到路径（用于导入 main.py 的模块）
sys.path.insert(0, str(Path(__file__).parent))

from main import DataAggregator, parse_match_input, CONFIG, log

BASE_DIR = Path(__file__).parent
SCHEDULE_FILE = BASE_DIR / "schedule_state.json"


class PipelineScheduler:
    """
    数据管道调度器

    管理多轮次、多比赛的自动化数据采集
    """

    def __init__(self):
        self.aggregator = DataAggregator()
        self.schedule_state = self._load_schedule_state()

    def _load_schedule_state(self) -> Dict:
        """加载调度状态（用于断点续传）"""
        if SCHEDULE_FILE.exists():
            try:
                with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {
            "last_run": None,
            "pending_matches": [],
            "completed_rounds": {},
            "statistics": {
                "total_runs": 0,
                "total_matches_processed": 0,
                "success_rate": 0.0
            }
        }

    def _save_schedule_state(self):
        """保存调度状态"""
        self.schedule_state["last_run"] = datetime.now().isoformat()
        with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.schedule_state, f, ensure_ascii=False, indent=2)

    def calculate_rounds(self, kickoff_time: str) -> Dict[int, Dict]:
        """
        根据比赛开球时间计算三轮执行时间

        返回：
          {
            1: {"scheduled_at": "2026-08-09T08:00:00", "status": "pending", "templates": [1,2,5,9,10]},
            2: {"scheduled_at": "2026-08-09T14:00:00", "status": "pending", "templates": [3,4,6,7,8,11]},
            3: {"scheduled_at": "2026-08-09T17:00:00", "status": "pending", "templates": [12,13,14,7,8]}
          }
        """
        try:
            kickoff_dt = datetime.fromisoformat(kickoff_time.replace('Z', '+00:00'))
        except:
            kickoff_dt = datetime.now() + timedelta(hours=24)

        now = datetime.now()

        round_config = {
            1: {"hours_before": 12, "name": "基线数据", "description": "伤停/H2H/PFI"},
            2: {"hours_before": 6,  "name": "动态信号", "description": "阵容/赔率/天气"},
            3: {"hours_before": 3,  "name": "最终校准", "description": "新闻/首发/临盘"},
        }

        rounds = {}
        for round_id, config in round_config.items():
            scheduled_time = kickoff_dt - timedelta(hours=config["hours_before"])
            rounds[round_id] = {
                "scheduled_at": scheduled_time.isoformat(),
                "scheduled_at_readable": scheduled_time.strftime("%Y-%m-%d %H:%M"),
                "status": "pending",
                "name": config["name"],
                "description": config["description"],
                "is_overdue": scheduled_time < now,
                "can_execute_now": scheduled_time <= now <= (scheduled_time + timedelta(hours=config["hours_before"]//2))
            }

        return rounds

    def execute_round_for_match(self, home: str, away: str, league: str,
                                city: str, kickoff: str, round_id: int) -> bool:
        """
        为指定比赛执行某一轮的数据采集

        返回：是否成功
        """
        log.info(f"\n{'='*60}")
        log.info(f"🎯 执行 Round {round_id}: {home} vs {away}")
        log.info(f"   联赛: {league} | 开球: {kickoff}")
        log.info(f"{'='*60}")

        try:
            # 调用聚合器的核心方法
            match_data = self.aggregator.aggregate_match(
                home_name=home,
                away_name=away,
                league=league,
                kickoff=kickoff,
                city=city
            )

            # 保存结果
            filepath = self.aggregator.save_match(match_data)

            # 更新状态
            match_key = f"{home}_{away}_{kickoff[:10]}"
            if match_key not in self.schedule_state["completed_rounds"]:
                self.schedule_state["completed_rounds"][match_key] = []
            self.schedule_state["completed_rounds"][match_key].append({
                "round_id": round_id,
                "executed_at": datetime.now().isoformat(),
                "confidence": match_data.confidence,
                "data_sources_count": len(match_data.data_sources),
                "cache_file": str(filepath)
            })

            self._save_schedule_state()
            self.schedule_state["statistics"]["total_matches_processed"] += 1

            log.info(f"\n✅ Round {round_id} 执行完成！")
            log.info(f"   置信度: {match_data.confidence}")
            log.info(f"   数据源: {len(match_data.data_sources)}个")
            return True

        except Exception as e:
            log.error(f"\n❌ Round {round_id} 执行失败: {e}")
            return False

    def run_full_pipeline(self, matches: List[tuple], league: str = "",
                          city: str = "", kickoff_override: str = ""):
        """
        对多场比赛运行完整的三轮数据采集

        这是主要的对外接口
        """
        log.info("\n" + "=" * 70)
        log.info("🚀 数据管道调度器启动 — 三轮渐进式采集模式")
        log.info(f"   时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info(f"   比赛数: {len(matches)} 场")
        log.info("=" * 70)

        success_count = 0

        for i, (home, away) in enumerate(matches, 1):
            log.info(f"\n⚽ [{i}/{len(matches)}] 处理: {home} vs {away}")

            # 计算三轮时间
            kickoff = kickoff_override or (datetime.now() + timedelta(hours=24)).isoformat()
            rounds = self.calculate_rounds(kickoff)

            # 显示时间表
            log.info(f"\n📅 三轮采集时间表:")
            for rid, rinfo in rounds.items():
                status_icon = "✅" if rinfo["can_execute_now"] else ("⏰" if not rinfo["is_overdue"] else "⏰ 过期")
                log.info(f"   Round {rid} ({rinfo['name']}): {rinfo['scheduled_at_readable']} {status_icon}")

            # 判断应该执行哪几轮
            rounds_to_execute = []
            for rid, rinfo in rounds.items():
                if rinfo["can_execute_now"] or rinfo["is_overdue"]:
                    rounds_to_execute.append(rid)

            if not rounds_to_execute:
                log.info(f"\n⏳ 所有轮次尚未到执行时间，跳过")
                continue

            log.info(f"\n🔄 即将执行轮次: {rounds_to_execute}")

            # 执行每一轮
            for round_id in rounds_to_execute:
                success = self.execute_round_for_match(
                    home=home, away=away,
                    league=league, city=city,
                    kickoff=kickoff, round_id=round_id
                )
                if success:
                    success_count += 1

                # 轮次间隔（避免请求过快）
                if round_id < max(rounds_to_execute):
                    wait_time = 5
                    log.info(f"\n⏳ 等待 {wait_time}s 后执行下一轮...")
                    time.sleep(wait_time)

            # 比赛间隔
            if i < len(matches):
                wait_time = 10
                log.info(f"\n⏳ 等待 {wait_time}s 后处理下一场比赛...")
                time.sleep(wait_time)

        # 输出汇总
        total_attempts = len(matches) * len([r for r in rounds.values() if r["can_execute_now"] or r["is_overdue"]])
        if total_attempts > 0:
            rate = (success_count / total_attempts) * 100
        else:
            rate = 0

        self.schedule_state["statistics"]["success_rate"] = rate
        self.schedule_state["statistics"]["total_runs"] += 1
        self._save_schedule_state()

        log.info("\n" + "=" * 70)
        log.info(f"📊 调度完成！成功率: {success_count}/{total_attempts} ({rate:.1f}%)")
        log.info("=" * 70)

    def show_status(self):
        """显示当前调度状态"""
        print("\n" + "=" * 60)
        print("📋 数据管道调度器状态")
        print("=" * 60)

        stats = self.schedule_state["statistics"]
        print(f"\n📈 统计:")
        print(f"   总运行次数: {stats.get('total_runs', 0)}")
        print(f"   已处理比赛: {stats.get('total_matches_processed', 0)}")
        print(f"   成功率: {stats.get('success_rate', 0):.1f}%")

        last_run = self.schedule_state.get("last_run")
        if last_run:
            print(f"   上次运行: {last_run}")

        completed = self.schedule_state.get("completed_rounds", {})
        if completed:
            print(f"\n✅ 已完成的采集:")
            for match_key, rounds in list(completed.items())[-5:]:  # 只显示最近5场
                print(f"   • {match_key}: {len(rounds)} 轮")

        pending = self.schedule_state.get("pending_matches", [])
        if pending:
            print(f"\n⏳ 待处理比赛 ({len(pending)} 场):")
            for m in pending[:5]:
                print(f"   • {m}")


def main():
    parser = argparse.ArgumentParser(
        description='数据管道调度器 v1.0 - 三轮渐进式自动采集',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 单场比赛，指定开球时间
  python scheduler.py --matches "Arsenal vs Coventry" --kickoff "2026-08-21T19:00:00"

  # 从文件读取多场比赛
  python scheduler.py --file matches_tomorrow.txt

  # 自动模式（需要配合 cron/任务计划程序）
  python scheduler.py --auto

  # 查看当前状态
  python scheduler.py --status

三轮策略说明:
  Round 1 (T-12h): 收集伤停名单、H2H交锋、PFI疲劳度基线数据
  Round 2 (T-6h):  跟进阵容预测、赔率变动、天气预报
  Round 3 (T-3h):  最终校准——新闻动因、首发曝光、临盘赔率

Windows 定时任务设置:
  schtasks /create /tn "FootballPipeline-Round1" \\
    /tr "python D:\\1\\Claw\\data-pipeline\\scheduler.py --file matches.txt --round 1" \\
    /sc daily /st 08:00

  schtasks /create /tn "FootballPipeline-Round2" \\
    /tr "python D:\\1\\Claw\\data-pipeline\\scheduler.py --file matches.txt --round 2" \\
    /sc daily /st 14:00

  schtasks /create /tn "FootballPipeline-Round3" \\
    /tr "python D:\\1\\Claw\\data-pipeline\\scheduler.py --file matches.txt --round 3" \\
    /sc daily /st 17:00
        """
    )

    parser.add_argument('--matches', '-m', type=str,
                        help='比赛列表，逗号分隔')
    parser.add_argument('--file', '-f', type=str,
                        help='从文件读取比赛列表')
    parser.add_argument('--league', '-l', type=str, default='',
                        help='联赛名称')
    parser.add_argument('--city', '-c', type=str, default='',
                        help='比赛城市')
    parser.add_argument('--kickoff', '-k', type=str, default='',
                        help='开球时间 (ISO格式: 2026-08-21T19:00:00)')
    parser.add_argument('--round', '-r', type=int, choices=[1, 2, 3],
                        help='只执行指定的轮次 (1/2/3)')
    parser.add_argument('--auto', action='store_true',
                        help='自动模式（从文件读取并智能判断执行哪些轮）')
    parser.add_argument('--status', action='store_true',
                        help='显示当前调度状态')

    args = parser.parse_args()

    scheduler = PipelineScheduler()

    if args.status:
        scheduler.show_status()
        return

    # 加载比赛列表
    matches = []

    if args.matches:
        matches = parse_match_input(args.matches)
    elif args.file:
        filepath = Path(args.file)
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            matches = parse_match_input(content)
        else:
            log.error(f"❌ 文件不存在: {filepath}")
            sys.exit(1)
    elif args.auto:
        # 自动模式：查找待处理的比赛
        state_file = Path("schedule_state.json")
        if state_file.exists():
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            matches = [(m['home'], m['away']) for m in state.get('pending_matches', [])]
            if not matches:
                log.warning("⚠️ 无待处理比赛，请先添加比赛到 schedule_state.json")
                return
        else:
            log.error("❌ 未找到 schedule_state.json，请先使用 --matches 或 --file 参数")
            sys.exit(1)
    else:
        parser.print_help()
        log.error("\n❌ 请指定输入方式 (--matches / --file / --auto / --status)")
        sys.exit(1)

    if not matches:
        log.error("❌ 未找到任何比赛")
        sys.exit(1)

    # 执行管道
    scheduler.run_full_pipeline(
        matches=matches,
        league=args.league,
        city=args.city,
        kickoff_override=args.kickoff
    )


if __name__ == '__main__':
    main()
