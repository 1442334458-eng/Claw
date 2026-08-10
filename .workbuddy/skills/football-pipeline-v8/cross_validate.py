#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  多源赔率交叉验证引擎 v1.0
  Cross-Validation Engine
============================================

核心功能：
  1. 赔率共识度计算（多源一致性）
  2. 单源异常检测（某博彩公司大幅偏离）
  3. 多源隐含概率合并（加权平均）
  4. 分歧信号标注与风险评级
  5. DOIT 多源增强版（多源 DOIT 交叉验证）

输入：MatchOdds 列表（来自 multi_source_odds.py）
输出：CrossValidationReport + 分析建议

使用方法：
  python cross_validate.py --input multi_source_output.json --output report.json

作者：CodeBuddy Code
日期：2026-08-10
版本：v1.0
"""

import json
import math
import logging
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)


# ============================================
# 数据模型
# ============================================

@dataclass
class OddsEntry:
    """单条赔率记录"""
    source: str
    home: float
    draw: float
    away: float
    handicap: Optional[float] = None
    handicap_home: Optional[float] = None
    handicap_away: Optional[float] = None
    return_rate: Optional[float] = None
    timestamp: str = ""


@dataclass
class ConsensusResult:
    """单场比赛的共识度分析结果"""
    match_id: str
    home_team: str
    away_team: str
    league: str = ""

    # 基本统计
    source_count: int = 0
    sources_list: List[str] = field(default_factory=list)

    # 主胜统计
    home_mean: float = 0.0
    home_std: float = 0.0
    home_min: float = 0.0
    home_max: float = 0.0
    home_range_pct: float = 0.0  # (max-min)/mean * 100%

    # 平局统计
    draw_mean: float = 0.0
    draw_std: float = 0.0
    draw_min: float = 0.0
    draw_max: float = 0.0
    draw_range_pct: float = 0.0

    # 客胜统计
    away_mean: float = 0.0
    away_std: float = 0.0
    away_min: float = 0.0
    away_max: float = 0.0
    away_range_pct: float = 0.0

    # 共识等级
    consensus_level: str = "unknown"  # high / medium / low / divergent
    max_coefficient_of_variation: float = 0.0

    # 异常检测
    anomalies: List[Dict] = field(default_factory=list)
    has_anomaly: bool = False

    # 合并概率（加权平均去水）
    merged_home_prob: float = 0.0
    merged_draw_prob: float = 0.0
    merged_away_prob: float = 0.0

    # DOIT 增强（多源）
    doit_mean: float = 0.0
    doit_std: float = 0.0
    doit_values: List[Dict] = field(default_factory=list)  # [{source, value}]
    doit_consensus: str = "unknown"

    # 综合信号
    signals: List[str] = field(default_factory=list)  # ['doit_trigger', 'draw_thick', 'home_anomaly', ...]
    risk_level: str = "unknown"  # low / medium / high

    # 来源完整度
    has_sporttery: bool = False
    has_500com: bool = False
    has_theodds: bool = False
    has_international: bool = False  # 有非竞彩的国际赔率


@dataclass
class CrossValidationReport:
    """完整的交叉验证报告"""
    generated_at: str = ""
    total_matches: int = 0
    summary: Dict = field(default_factory=dict)
    results: List[ConsensusResult] = field(default_factory=list)
    global_signals: List[Dict] = field(default_factory=list)


# ============================================
# 核心算法
# ============================================

class CrossValidator:
    """多源交叉验证器"""

    # 权重配置（各数据源在合并概率中的权重）
    SOURCE_WEIGHTS = {
        "sporttery": 0.25,       # 竞彩官方（返奖率低，权重下调）
        "theodds_bet365": 0.30,  # Bet365（返奖率高，可信度高）
        "theodds_pinnacle": 0.35, # Pinnacle（返奖率最高，权重最高）
        "500com_bet365": 0.20,
        "500com_william_hill": 0.20,
        "500com_macau": 0.15,
        "500com_ladbrokes": 0.20,
        "500com_pinnacle": 0.25,
        "websearch": 0.10,       # 搜索引擎兜底（权重最低）
    }
    DEFAULT_WEIGHT = 0.15
    DEFAULT_SPORTTERY_WEIGHT = 0.20

    def compute_consensus(self, entries: List[OddsEntry]) -> ConsensusResult:
        """计算单场比赛的多源共识"""
        if not entries:
            return ConsensusResult(match_id="unknown", home_team="", away_team="")

        result = ConsensusResult(
            match_id="unknown",
            home_team="",
            away_team="",
            source_count=len(entries),
            sources_list=[e.source for e in entries],
        )

        # 基本统计
        homes = [e.home for e in entries if e.home > 0]
        draws = [e.draw for e in entries if e.draw > 0]
        aways = [e.away for e in entries if e.away > 0]

        def calc_stats(vals: List[float]) -> Tuple[float, float, float, float]:
            if not vals:
                return 0, 0, 0, 0
            if len(vals) == 1:
                return vals[0], 0, vals[0], vals[0]
            mean = sum(vals) / len(vals)
            variance = sum((v - mean) ** 2 for v in vals) / len(vals)
            std = math.sqrt(variance)
            return mean, std, min(vals), max(vals)

        result.home_mean, result.home_std, result.home_min, result.home_max = calc_stats(homes)
        result.draw_mean, result.draw_std, result.draw_min, result.draw_max = calc_stats(draws)
        result.away_mean, result.away_std, result.away_min, result.away_max = calc_stats(aways)

        # 波动幅度百分比
        if result.home_mean > 0:
            result.home_range_pct = (result.home_max - result.home_min) / result.home_mean * 100
        if result.draw_mean > 0:
            result.draw_range_pct = (result.draw_max - result.draw_min) / result.draw_mean * 100
        if result.away_mean > 0:
            result.away_range_pct = (result.away_max - result.away_min) / result.away_mean * 100

        # 变异性系数（CV = std / mean），取三种结果的最大值
        cvs = []
        if result.home_mean > 0:
            cvs.append(result.home_std / result.home_mean)
        if result.draw_mean > 0:
            cvs.append(result.draw_std / result.draw_mean)
        if result.away_mean > 0:
            cvs.append(result.away_std / result.away_mean)

        result.max_coefficient_of_variation = max(cvs) if cvs else 0

        # 共识等级判定
        if result.source_count < 2:
            result.consensus_level = "single_source"
        elif result.max_coefficient_of_variation > 0.10:
            result.consensus_level = "divergent"
        elif result.max_coefficient_of_variation > 0.05:
            result.consensus_level = "low"
        elif result.max_coefficient_of_variation > 0.02:
            result.consensus_level = "medium"
        else:
            result.consensus_level = "high"

        # 异常检测（2倍标准差）
        for e in entries:
            for outcome, val, mean, std in [
                ("主胜", e.home, result.home_mean, result.home_std),
                ("平局", e.draw, result.draw_mean, result.draw_std),
                ("客胜", e.away, result.away_mean, result.away_std),
            ]:
                if std > 0.01 and abs(val - mean) > 2 * std:
                    result.anomalies.append({
                        "source": e.source,
                        "outcome": outcome,
                        "value": round(val, 3),
                        "mean": round(mean, 3),
                        "deviation": round(val - mean, 3),
                        "deviation_sigma": round(abs(val - mean) / std, 2),
                    })

        result.has_anomaly = len(result.anomalies) > 0

        # 来源检测
        for e in entries:
            if "sporttery" in e.source:
                result.has_sporttery = True
            if "500com" in e.source:
                result.has_500com = True
            if "theodds" in e.source:
                result.has_theodds = True
            if "pinnacle" in e.source.lower() and e.source != "sporttery":
                result.has_international = True

        # 合并概率（加权平均 + 去水）
        result.merged_home_prob, result.merged_draw_prob, result.merged_away_prob = \
            self._merge_probabilities(entries)

        # DOIT 多源计算
        self._compute_multisource_doit(result, entries)

        # 信号生成
        self._generate_signals(result)

        # 风险评估
        self._assess_risk(result)

        return result

    def _get_source_weight(self, source: str) -> float:
        """获取数据源权重"""
        # 精确匹配
        if source in self.SOURCE_WEIGHTS:
            return self.SOURCE_WEIGHTS[source]
        # 模糊匹配
        for key, w in self.SOURCE_WEIGHTS.items():
            if key in source.lower():
                return w
        if "sporttery" in source:
            return self.DEFAULT_SPORTTERY_WEIGHT
        return self.DEFAULT_WEIGHT

    def _merge_probabilities(self, entries: List[OddsEntry]) -> Tuple[float, float, float]:
        """多源隐含概率加权合并（去水后）"""
        if not entries:
            return 0, 0, 0

        weighted_probs = {"home": 0.0, "draw": 0.0, "away": 0.0}
        total_weight = 0.0

        for e in entries:
            w = self._get_source_weight(e.source)
            total_weight += w

            # 计算隐含概率
            inv_sum = (1.0 / e.home if e.home > 0 else 0) + \
                      (1.0 / e.draw if e.draw > 0 else 0) + \
                      (1.0 / e.away if e.away > 0 else 0)
            
            if inv_sum > 0:
                weighted_probs["home"] += w * (1.0 / e.home) / inv_sum
                weighted_probs["draw"] += w * (1.0 / e.draw) / inv_sum
                weighted_probs["away"] += w * (1.0 / e.away) / inv_sum

        if total_weight > 0:
            return (
                round(weighted_probs["home"] / total_weight, 4),
                round(weighted_probs["draw"] / total_weight, 4),
                round(weighted_probs["away"] / total_weight, 4),
            )
        return 0, 0, 0

    def _compute_multisource_doit(self, result: ConsensusResult, entries: List[OddsEntry]):
        """多源 DOIT 计算
        
        DOIT = √(主胜赔 × 客胜赔) / 平赔
        多源版本：每个数据源算一个DOIT，然后计算均值和标准差。
        多源 DOIT 的 CV 反映了平赔在各博彩公司间的分歧程度。
        """
        doit_values = []
        for e in entries:
            if e.home > 0 and e.draw > 0 and e.away > 0:
                doit = math.sqrt(e.home * e.away) / e.draw
                doit_values.append({
                    "source": e.source,
                    "value": round(doit, 4),
                })

        result.doit_values = doit_values

        if doit_values:
            vals = [d["value"] for d in doit_values]
            result.doit_mean = round(sum(vals) / len(vals), 4)
            if len(vals) > 1:
                variance = sum((v - result.doit_mean) ** 2 for v in vals) / len(vals)
                result.doit_std = round(math.sqrt(variance), 4)

            # DOIT 共识（基于 CV）
            if result.doit_mean > 0:
                doit_cv = result.doit_std / result.doit_mean if result.doit_mean > 0 else 0
                if result.source_count < 2:
                    result.doit_consensus = "single_source"
                elif doit_cv > 0.08:
                    result.doit_consensus = "divergent"
                elif doit_cv > 0.04:
                    result.doit_consensus = "low"
                else:
                    result.doit_consensus = "high"

    def _generate_signals(self, result: ConsensusResult):
        """生成分析信号"""
        signals = []

        # DOIT 信号
        if result.doit_mean > 0:
            if result.doit_mean < 0.82:
                signals.append("doit_strong_warning")
            elif result.doit_mean < 0.88:
                signals.append("doit_trigger")
            elif result.doit_mean < 0.92:
                signals.append("doit_watch")

        # 赔率共识信号
        if result.consensus_level == "divergent":
            signals.append("odds_divergent")
        elif result.consensus_level == "low":
            signals.append("odds_low_consensus")

        # 平赔分歧（特别关注：平赔分歧大可能意味着庄家对平局看法不一致）
        if result.draw_range_pct > 15:
            signals.append("draw_high_divergence")

        # 主胜/客胜异常
        for anomaly in result.anomalies:
            if anomaly["outcome"] == "主胜":
                signals.append("home_odds_anomaly")
            elif anomaly["outcome"] == "平局":
                signals.append("draw_odds_anomaly")
            elif anomaly["outcome"] == "客胜":
                signals.append("away_odds_anomaly")

        # 竞彩 vs 国际对比
        if result.has_sporttery and result.has_international:
            # 检查竞彩平赔是否明显偏高（竞彩平赔通常更厚）
            signals.append("sporttery_vs_international_available")

        # 数据源丰富度
        if result.source_count >= 4:
            signals.append("rich_data")
        elif result.source_count == 1:
            signals.append("single_source_risk")

        result.signals = signals

    def _assess_risk(self, result: ConsensusResult):
        """综合风险评估"""
        risk_score = 0

        # 单源 +2
        if result.source_count < 2:
            risk_score += 2
        # 分歧 +2
        if result.consensus_level == "divergent":
            risk_score += 2
        elif result.consensus_level == "low":
            risk_score += 1
        # DOIT 警告 +2
        if "doit_strong_warning" in result.signals:
            risk_score += 2
        elif "doit_trigger" in result.signals:
            risk_score += 1
        # 异常 +1 each
        risk_score += len(result.anomalies)

        if risk_score >= 4:
            result.risk_level = "high"
        elif risk_score >= 2:
            result.risk_level = "medium"
        else:
            result.risk_level = "low"

    def validate_matches(self, matches: List[Dict]) -> CrossValidationReport:
        """批量交叉验证"""
        report = CrossValidationReport(
            generated_at=datetime.now().isoformat(),
            total_matches=len(matches),
        )

        summary = {
            "total": len(matches),
            "multi_source": 0,
            "single_source": 0,
            "high_consensus": 0,
            "medium_consensus": 0,
            "low_consensus": 0,
            "divergent": 0,
            "high_risk": 0,
            "medium_risk": 0,
            "low_risk": 0,
            "doit_triggered": 0,
            "anomaly_detected": 0,
        }

        for match_data in matches:
            # 转换数据格式
            entries = []
            for s in match_data.get("sources", []):
                if isinstance(s, dict):
                    entries.append(OddsEntry(
                        source=s.get("name", s.get("source", "unknown")),
                        home=s.get("home", s.get("home_win", 0)),
                        draw=s.get("draw", 0),
                        away=s.get("away", s.get("away_win", 0)),
                    ))

            match_id = match_data.get("match_id", "unknown")
            home = match_data.get("home_team", "")
            away = match_data.get("away_team", "")
            league = match_data.get("league", "")

            result = self.compute_consensus(entries)
            result.match_id = match_id
            result.home_team = home
            result.away_team = away
            result.league = league

            report.results.append(result)

            # 汇总统计
            if result.source_count >= 2:
                summary["multi_source"] += 1
            else:
                summary["single_source"] += 1

            summary[f"{result.consensus_level}_consensus"] += 1
            summary[f"{result.risk_level}_risk"] += 1

            if result.doit_mean > 0 and result.doit_mean < 0.88:
                summary["doit_triggered"] += 1
            if result.has_anomaly:
                summary["anomaly_detected"] += 1

        report.summary = summary

        # 全局信号
        if summary["divergent"] > summary["total"] * 0.3:
            report.global_signals.append({
                "signal": "high_divergence_day",
                "message": f"当日 {summary['divergent']}/{summary['total']} 场比赛出现严重分歧，今日整体不确定性高，建议降低仓位",
            })

        if summary["doit_triggered"] > summary["total"] * 0.4:
            report.global_signals.append({
                "signal": "doit_cluster",
                "message": f"当日 {summary['doit_triggered']} 场 DOIT 触发，可能存在博彩公司整体调整策略，建议谨慎",
            })

        return report


# ============================================
# 格式化输出
# ============================================

def format_consensus_table(results: List[ConsensusResult]) -> str:
    """生成共识度汇总表格"""
    lines = []
    lines.append("| 场次 | 对阵 | 联赛 | 源数 | 共识等级 | DOIT均值 | 风险 | 信号 |")
    lines.append("|------|------|------|:----:|:--------:|:--------:|:----:|------|")

    for r in results:
        signals_str = ", ".join(r.signals[:3]) if r.signals else "—"
        signals_str = signals_str[:40] + "..." if len(signals_str) > 40 else signals_str
        
        # 共识等级图标
        level_icon = {
            "high": "✅",
            "medium": "🟡",
            "low": "🟠",
            "divergent": "🔴",
            "single_source": "⚪",
        }.get(r.consensus_level, "❓")

        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(r.risk_level, "❓")

        line = f"| {r.match_id} | {r.home_team}vs{r.away_team} | {r.league} | {r.source_count} | {level_icon}{r.consensus_level} | {r.doit_mean:.3f}±{r.doit_std:.3f} | {risk_icon} | {signals_str} |"
        lines.append(line)

    return "\n".join(lines)


def format_anomaly_report(results: List[ConsensusResult]) -> str:
    """生成异常赔率报告"""
    lines = []
    has_any = False

    for r in results:
        if r.anomalies:
            has_any = True
            lines.append(f"\n### {r.home_team} vs {r.away_team} ({r.league})")
            for a in r.anomalies:
                direction = "偏高" if a["deviation"] > 0 else "偏低"
                lines.append(
                    f"- **{a['source']}** {a['outcome']}赔率 {direction}: "
                    f"{a['value']} (均值{a['mean']}, 偏离{a['deviation_sigma']:.1f}σ)"
                )

    if not has_any:
        lines.append("✅ 无异常赔率检测")

    return "\n".join(lines)


# ============================================
# 命令行入口
# ============================================

def main():
    parser = argparse.ArgumentParser(description="多源赔率交叉验证引擎")
    parser.add_argument("--input", type=str, required=True, help="输入JSON文件（多源采集器输出）")
    parser.add_argument("--output", type=str, help="输出报告文件")
    parser.add_argument("--format", type=str, default="json", choices=["json", "text"], help="输出格式")
    
    args = parser.parse_args()

    # 读取输入
    input_path = Path(args.input)
    if not input_path.exists():
        log.error(f"输入文件不存在: {args.input}")
        sys.exit(1)

    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 提取比赛列表
    matches = []
    if isinstance(data, dict):
        if "report" in data and "matches" in data.get("report", {}):
            matches = data["report"]["matches"]
        elif "matches" in data:
            matches = data["matches"]
        elif "results" in data:
            # 已经是报告格式
            matches = data["results"] if isinstance(data["results"], list) else [data]
    elif isinstance(data, list):
        matches = data

    # 执行验证
    validator = CrossValidator()
    report = validator.validate_matches(matches)

    if args.format == "text":
        # 文本格式输出
        output_lines = []
        output_lines.append("=" * 60)
        output_lines.append(f"  多源交叉验证报告 ({report.generated_at})")
        output_lines.append("=" * 60)
        output_lines.append(f"")
        output_lines.append(f"总场次: {report.summary['total']}")
        output_lines.append(f"多源(>=2): {report.summary['multi_source']} | 单源: {report.summary['single_source']}")
        output_lines.append(f"共识: 高{report.summary['high_consensus']} | 中{report.summary['medium_consensus']} | 低{report.summary['low_consensus']} | 分歧{report.summary['divergent']}")
        output_lines.append(f"风险: 低{report.summary['low_risk']} | 中{report.summary['medium_risk']} | 高{report.summary['high_risk']}")
        output_lines.append(f"DOIT触发: {report.summary['doit_triggered']} | 异常检测: {report.summary['anomaly_detected']}")
        output_lines.append("")
        
        # 全局信号
        if report.global_signals:
            output_lines.append("⚠️ 全局信号:")
            for sig in report.global_signals:
                output_lines.append(f"  [{sig['signal']}] {sig['message']}")
            output_lines.append("")

        # 详细表格
        output_lines.append(format_consensus_table(report.results))
        output_lines.append("")
        
        # 异常报告
        output_lines.append("## 异常赔率检测")
        output_lines.append(format_anomaly_report(report.results))

        text_output = "\n".join(output_lines)
        
        if args.output:
            Path(args.output).write_text(text_output, encoding='utf-8')
            print(f"文本报告已保存: {args.output}")
        else:
            print(text_output)
    else:
        # JSON格式
        output_data = {
            "generated_at": report.generated_at,
            "summary": report.summary,
            "global_signals": report.global_signals,
            "results": [
                {
                    "match_id": r.match_id,
                    "home_team": r.home_team,
                    "away_team": r.away_team,
                    "league": r.league,
                    "source_count": r.source_count,
                    "sources": r.sources_list,
                    "consensus_level": r.consensus_level,
                    "odds_stats": {
                        "home": {"mean": r.home_mean, "std": r.home_std, "min": r.home_min, "max": r.home_max},
                        "draw": {"mean": r.draw_mean, "std": r.draw_std, "min": r.draw_min, "max": r.draw_max},
                        "away": {"mean": r.away_mean, "std": r.away_std, "min": r.away_min, "max": r.away_max},
                    },
                    "merged_probabilities": {
                        "home": r.merged_home_prob,
                        "draw": r.merged_draw_prob,
                        "away": r.merged_away_prob,
                    },
                    "doit": {
                        "mean": r.doit_mean,
                        "std": r.doit_std,
                        "consensus": r.doit_consensus,
                        "values": r.doit_values,
                    },
                    "anomalies": r.anomalies,
                    "signals": r.signals,
                    "risk_level": r.risk_level,
                }
                for r in report.results
            ],
        }

        json_output = json.dumps(output_data, ensure_ascii=False, indent=2)
        
        if args.output:
            Path(args.output).write_text(json_output, encoding='utf-8')
            print(f"JSON报告已保存: {args.output}")
        else:
            print(json_output)


if __name__ == "__main__":
    import sys
    main()
