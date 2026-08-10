#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================
  多源交叉验证引擎 v1.0
  Cross-Validation Engine
============================================

核心功能：
  1. 共识度计算 — CV变异系数法，4档分级
  2. 单源异常检测 — 2σ偏离检测，自动标记
  3. 加权隐含概率合并 — Pinnacle权重最高35%
  4. DOIT多源增强版 — 均值+标准差取代单源估算
  5. 综合风险评估 — low/medium/high 联动星级调整

数据输入：
  MultiSourceOddsReport (来自 multi_source_odds.py)

数据输出：
  CrossValidationReport → 供分析引擎(Rule 14/Rule 25/Rule 27)消费

联动铁律：
  Rule 14: 赔率单源交叉验证 (核心)
  Rule 25: 赔率异动捕捉
  Rule 27: 亚盘降盘联动
  Rule 29: 赔率盘口交叉验证+多源共识检测
  Rule 13: DOIT三角 (多源增强)

设计原则：
  - 可独立运行，不依赖外部服务
  - 输入结构宽松，有多少家赔率就用多少家
  - 异常检测规则透明，每条判定附带解释

作者：CodeBuddy Code (管道 v2.1 升级)
日期：2026-08-10
版本：v1.0
"""

import math
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


# ============================================
# 数据模型
# ============================================

class ConsensusLevel(Enum):
    HIGH = "high"           # CV < 0.03 — 多源高度共识
    MEDIUM = "medium"       # CV 0.03-0.08 — 正常范围
    LOW = "low"             # CV 0.08-0.15 — 分歧较大
    DIVERGENT = "divergent" # CV > 0.15 — 严重分歧

class RiskLevel(Enum):
    LOW = "low"             # 无异常信号
    MEDIUM = "medium"       # 有异常信号，需关注
    HIGH = "high"           # 严重异常，触发降星/双选

@dataclass
class ConsensusResult:
    """共识度分析结果"""
    level: ConsensusLevel = ConsensusLevel.MEDIUM
    cv_coefficient: float = 0.0         # 变异系数
    mean_home: float = 0.0              # 平均主胜赔率
    mean_draw: float = 0.0
    mean_away: float = 0.0
    std_home: float = 0.0               # 标准差
    std_draw: float = 0.0
    std_away: float = 0.0
    implied_home_prob: float = 0.0      # 隐含主胜概率(加权)
    implied_draw_prob: float = 0.0
    implied_away_prob: float = 0.0
    source_count: int = 0               # 参与计算的数据源数量
    sources_used: List[str] = field(default_factory=list)

@dataclass
class OutlierResult:
    """异常检测结果"""
    bookmaker_name: str = ""
    deviation_sigma: float = 0.0        # 偏离标准差倍数
    field: str = ""                     # 异常字段 (home_win/draw/away_win)
    value: float = 0.0
    expected_range: Tuple[float, float] = (0, 0)
    recommendation: str = ""

@dataclass
class DOITEnhanced:
    """DOIT多源增强版"""
    doit_raw: float = 0.0               # 原始DOIT值
    doit_mean: float = 0.0              # 多源均值DOIT
    doit_std: float = 0.0               # 多源标准差
    doit_range: Tuple[float, float] = (0, 0)  # DOIT置信区间
    confidence: str = ""                # 置信度评估 (多源)
    signal_strength: str = ""           # 信号强度 (strong/moderate/weak/noise)

    # === 竞彩官方独立 DOIT (v1.1 修复) ===
    # 竞彩返奖率~71%，与国际博彩公司(~93-98%)体系不同
    # 竞彩DOIT需独立计算，作为主信号源
    jc_doit: float = 0.0                # 竞彩官方DOIT值
    jc_signal_strength: str = ""        # 竞彩信号强度
    jc_confidence: str = ""             # 竞彩信号置信度
    jc_warning: bool = False            # 竞彩DOIT是否触发防平
    jc_warning_level: str = ""          # P0/P1/P2 防平级别

@dataclass
class CrossValidationReport:
    """交叉验证完整报告"""
    match_id: str = ""
    home_team: str = ""
    away_team: str = ""
    validated_at: str = ""

    # 共识度
    consensus: ConsensusResult = field(default_factory=ConsensusResult)

    # 异常检测
    outliers: List[OutlierResult] = field(default_factory=list)

    # 加权隐含概率
    weighted_implied: Dict[str, float] = field(default_factory=dict)

    # DOIT增强
    doit_enhanced: DOITEnhanced = field(default_factory=DOITEnhanced)

    # 亚盘变动检测
    asian_movement_detected: bool = False
    asian_movement_magnitude: float = 0.0
    asian_movement_bookmakers: List[str] = field(default_factory=list)

    # 综合风险
    risk_level: RiskLevel = RiskLevel.LOW
    risk_factors: List[str] = field(default_factory=list)

    # 星级联动建议
    star_adjustment: int = 0            # 建议调整星级 (-2 ~ +1)
    star_reasons: List[str] = field(default_factory=list)

    # 竞彩建议
    betting_advice: str = ""


# ============================================
# 交叉验证引擎
# ============================================

class CrossValidator:
    """
    多源赔率交叉验证引擎

    输入格式 (宽松):
      赔率数据 = [
        {"bookmaker": "竞彩", "home": 1.19, "draw": 5.80, "away": 8.55},
        {"bookmaker": "Pinnacle", "home": 1.22, "draw": 5.50, "away": 7.80},
        {"bookmaker": "澳彩", "home": 1.18, "draw": 6.00, "away": 9.00},
        ...
      ]

    权重配置 (基于历史准确率):
      Pinnacle:     35%  (锋线庄家，市场效率最高)
      Bet365:       20%  (全球最大，流动性最强)
      竞彩官方:     15%  (中国市场基准)
      澳彩:         10%  (亚盘水位锚定)
      威廉希尔:     10%  (英国传统)
      立博:          5%  (欧洲传统)
      其他:          5%  (百家平均参考)
    """

    # 权重配置
    WEIGHTS = {
        "pinnacle": 0.35,
        "平博": 0.35,
        "bet365": 0.20,
        "竞彩官方": 0.15,
        "竞彩": 0.15,
        "澳门彩票": 0.10,
        "澳彩": 0.10,
        "macau slot": 0.10,
        "william hill": 0.10,
        "威廉希尔": 0.10,
        "立博": 0.05,
        "ladbrokes": 0.05,
        "盈禾": 0.03,
        "wewbet": 0.03,
    }

    DEFAULT_WEIGHT = 0.02  # 未识别博彩公司的默认权重

    def __init__(self):
        pass

    def validate(self, match_id: str, home_team: str, away_team: str,
                 odds_sources: List[Dict]) -> CrossValidationReport:
        """
        主验证入口

        Args:
            match_id: 比赛ID
            home_team: 主队名称
            away_team: 客队名称
            odds_sources: 多源赔率列表

        Returns:
            CrossValidationReport
        """
        report = CrossValidationReport(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            validated_at=datetime.now().isoformat()
        )

        # 过滤有效数据
        valid_sources = [
            s for s in odds_sources
            if s.get('home', 0) > 1.0 and s.get('draw', 0) > 1.0 and s.get('away', 0) > 1.0
        ]

        if len(valid_sources) < 2:
            report.consensus.level = ConsensusLevel.LOW
            report.risk_level = RiskLevel.HIGH
            report.risk_factors.append("数据源不足(<2家)")
            report.star_adjustment = -1
            report.star_reasons.append("多源验证不可用")
            report.betting_advice = "⚠️ 数据源不足，建议人工判断"
            return report

        # === Step 1: 共识度计算 ===
        report.consensus = self._calculate_consensus(valid_sources)

        # === Step 2: 单源异常检测 ===
        report.outliers = self._detect_outliers(valid_sources, report.consensus)

        # === Step 3: 加权隐含概率 ===
        report.weighted_implied = self._calculate_weighted_implied(valid_sources)

        # === Step 4: DOIT 多源增强 ===
        report.doit_enhanced = self._calculate_doit_enhanced(valid_sources)

        # === Step 5: 亚盘变动检测 ===
        asian_sources = [s for s in valid_sources if s.get('asian_opening', 0) != 0]
        report.asian_movement_detected, report.asian_movement_magnitude, report.asian_movement_bookmakers = \
            self._detect_asian_movement(asian_sources)

        # === Step 6: 综合风险评估 + 星级联动 ===
        report.risk_level, report.risk_factors = self._assess_risk(report)
        report.star_adjustment, report.star_reasons = self._calculate_star_adjustment(report)
        report.betting_advice = self._generate_advice(report)

        return report

    # === Step 1: 共识度计算 ===

    def _calculate_consensus(self, sources: List[Dict]) -> ConsensusResult:
        """CV变异系数法共识度计算"""
        n = len(sources)
        home_vals = [s['home'] for s in sources]
        draw_vals = [s['draw'] for s in sources]
        away_vals = [s['away'] for s in sources]

        mean_h = sum(home_vals) / n
        mean_d = sum(draw_vals) / n
        mean_a = sum(away_vals) / n

        # 标准差
        std_h = math.sqrt(sum((x - mean_h) ** 2 for x in home_vals) / n) if n > 1 else 0
        std_d = math.sqrt(sum((x - mean_d) ** 2 for x in draw_vals) / n) if n > 1 else 0
        std_a = math.sqrt(sum((x - mean_a) ** 2 for x in away_vals) / n) if n > 1 else 0

        # 变异系数 CV = σ/μ
        cv_h = std_h / mean_h if mean_h > 0 else 0

        # 共识等级判定
        if cv_h < 0.03:
            level = ConsensusLevel.HIGH
        elif cv_h < 0.08:
            level = ConsensusLevel.MEDIUM
        elif cv_h < 0.15:
            level = ConsensusLevel.LOW
        else:
            level = ConsensusLevel.DIVERGENT

        # 隐含概率 (简单平均，不含权重)
        implied_h = (1 / mean_h) / (1 / mean_h + 1 / mean_d + 1 / mean_a)
        implied_d = (1 / mean_d) / (1 / mean_h + 1 / mean_d + 1 / mean_a)
        implied_a = (1 / mean_a) / (1 / mean_h + 1 / mean_d + 1 / mean_a)

        return ConsensusResult(
            level=level,
            cv_coefficient=round(cv_h, 4),
            mean_home=round(mean_h, 2),
            mean_draw=round(mean_d, 2),
            mean_away=round(mean_a, 2),
            std_home=round(std_h, 4),
            std_draw=round(std_d, 4),
            std_away=round(std_a, 4),
            implied_home_prob=round(implied_h, 4),
            implied_draw_prob=round(implied_d, 4),
            implied_away_prob=round(implied_a, 4),
            source_count=n,
            sources_used=[s.get('bookmaker', '?') for s in sources]
        )

    # === Step 2: 单源异常检测 ===

    def _detect_outliers(self, sources: List[Dict],
                         consensus: ConsensusResult) -> List[OutlierResult]:
        """2σ偏离检测"""
        outliers = []

        if consensus.std_home == 0:
            return outliers

        for s in sources:
            bm_name = s.get('bookmaker', 'unknown')

            for field, mean_val, std_val in [
                ('home', consensus.mean_home, consensus.std_home),
                ('draw', consensus.mean_draw, consensus.std_draw),
                ('away', consensus.mean_away, consensus.std_away),
            ]:
                val = s.get(field, 0)
                if val == 0 or std_val == 0:
                    continue

                z_score = abs(val - mean_val) / std_val

                if z_score > 2.0:
                    lower = mean_val - 2 * std_val
                    upper = mean_val + 2 * std_val
                    outliers.append(OutlierResult(
                        bookmaker_name=bm_name,
                        deviation_sigma=round(z_score, 2),
                        field=field,
                        value=val,
                        expected_range=(round(lower, 2), round(upper, 2)),
                        recommendation=f"{bm_name} {field}赔率偏离市场{2*std_val:.2f}以上，建议排除或人工审核"
                    ))

        return outliers

    # === Step 3: 加权隐含概率 ===

    def _calculate_weighted_implied(self, sources: List[Dict]) -> Dict[str, float]:
        """加权隐含概率合并"""
        total_weight = 0
        weighted_home_inv = 0
        weighted_draw_inv = 0
        weighted_away_inv = 0

        for s in sources:
            bm_name = s.get('bookmaker', '').lower()
            weight = self._get_weight(bm_name)

            weighted_home_inv += weight / s['home']
            weighted_draw_inv += weight / s['draw']
            weighted_away_inv += weight / s['away']
            total_weight += weight

        if total_weight == 0:
            return {"home": 0, "draw": 0, "away": 0}

        # 归一化
        total_inv = weighted_home_inv + weighted_draw_inv + weighted_away_inv

        return {
            "home": round(weighted_home_inv / total_inv, 4),
            "draw": round(weighted_draw_inv / total_inv, 4),
            "away": round(weighted_away_inv / total_inv, 4),
            "home_odds_implied": round(total_weight / weighted_home_inv, 2),
            "draw_odds_implied": round(total_weight / weighted_draw_inv, 2),
            "away_odds_implied": round(total_weight / weighted_away_inv, 2),
            "total_weight": round(total_weight, 2),
        }

    def _get_weight(self, bm_name_lower: str) -> float:
        for key, w in self.WEIGHTS.items():
            if key in bm_name_lower:
                return w
        return self.DEFAULT_WEIGHT

    # === Step 4: DOIT 多源增强 ===

    def _calculate_doit_enhanced(self, sources: List[Dict]) -> DOITEnhanced:
        """
        DOIT = Draw Odds Implied Threat (平局赔率隐含威胁)

        标准DOIT: DOIT = |1/Draw - 1/Home|
          含义: 平局隐含概率与主胜隐含概率的差距
          差距越小 → 平局威胁越大 → DOIT越大
          DOIT > 0.8  → P0级防平 (差距小，平局高度威胁)
          DOIT > 0.5  → 二星防平 (差距中，平局较有威胁)
          DOIT > 0.3  → 一星防平 (差距中等，平局有威胁)

        注意: 公式中 1/Draw - 1/Home 对于深盘主队为负值
        取绝对值后，深盘主队(主1.19/平5.80)的DOIT=|0.17-0.84|=0.67 → 触发P1

        多源增强:
          计算每家博彩公司的DOIT，取均值和标准差
          doit_mean ± 1.96*doit_std = 95% 置信区间

        v1.1 修复: 竞彩官方DOIT独立计算
          竞彩返奖率~71%，与国际博彩公司(~93-98%)体系不同
          竞彩平赔相对较低(隐含平局概率更高) → 竞彩DOIT天然偏高
          多源均值会稀释竞彩信号 → 竞彩DOIT作为独立主信号源
        """
        doit_values = []
        jc_doit_value = 0.0
        jc_found = False

        for s in sources:
            h = s.get('home', 0)
            d = s.get('draw', 0)
            if h > 1 and d > 1:
                # DOIT = |1/Draw - 1/Home| = 平局与主胜的隐含概率差距绝对值
                doit = abs((1 / d) - (1 / h))
                doit_values.append(doit)

                # 单独记录竞彩官方 DOIT
                bm_name = s.get('bookmaker', '').lower()
                if any(kw in bm_name for kw in ('竞彩', 'jc', 'sporttery')):
                    jc_doit_value = doit
                    jc_found = True

        if not doit_values:
            return DOITEnhanced(confidence="数据不足")

        n = len(doit_values)
        doit_mean = sum(doit_values) / n
        doit_std = math.sqrt(sum((x - doit_mean) ** 2 for x in doit_values) / n) if n > 1 else 0

        # 95% 置信区间
        ci_lower = doit_mean - 1.96 * doit_std
        ci_upper = doit_mean + 1.96 * doit_std

        # 信号强度判定 (基于多源均值)
        if doit_mean > 0.8:
            strength = "strong"
        elif doit_mean > 0.5:
            strength = "moderate"
        elif doit_mean > 0.3:
            strength = "weak"
        else:
            strength = "noise"

        # 多源置信度评估
        if doit_std < 0.05:
            confidence = "high"
        elif doit_std < 0.10:
            confidence = "medium"
        else:
            confidence = "low"

        # === 竞彩官方独立 DOIT 判定 ===
        jc_signal = ""
        jc_conf = ""
        jc_warning = False
        jc_level = ""

        if jc_found and jc_doit_value > 0:
            # 竞彩DOIT信号强度 (竞彩专用阈值，因返奖率不同)
            if jc_doit_value > 0.8:
                jc_signal = "strong"
                jc_warning = True
                jc_level = "P0"
            elif jc_doit_value > 0.5:
                jc_signal = "moderate"
                jc_warning = True
                jc_level = "P1"
            elif jc_doit_value > 0.3:
                jc_signal = "weak"
                jc_warning = True
                jc_level = "P2"
            else:
                jc_signal = "noise"

            # 竞彩置信度: 单源但权威
            jc_conf = "high"  # 竞彩官方是出票依据，置信度=高

        return DOITEnhanced(
            doit_raw=round(doit_values[0], 4) if doit_values else 0,
            doit_mean=round(doit_mean, 4),
            doit_std=round(doit_std, 4),
            doit_range=(round(ci_lower, 4), round(ci_upper, 4)),
            confidence=confidence,
            signal_strength=strength,
            # 竞彩独立字段
            jc_doit=round(jc_doit_value, 4),
            jc_signal_strength=jc_signal,
            jc_confidence=jc_conf,
            jc_warning=jc_warning,
            jc_warning_level=jc_level,
        )

    # === Step 5: 亚盘变动检测 ===

    def _detect_asian_movement(self, sources: List[Dict]) -> Tuple[bool, float, List[str]]:
        """
        检测亚盘变动 ≥0.25球 且 ≥2家同步

        Rule 27: 亚盘降盘-信心联动
        ≥0.25球变动且≥4/5家bookmaker同步 = 强信号
        """
        movers = []
        max_movement = 0.0

        for s in sources:
            opening = s.get('asian_opening', 0)
            current = s.get('asian_current', 0)
            if opening == 0:
                continue

            change = abs(current - opening)
            if change >= 0.25:
                movers.append(s.get('bookmaker', '?'))
                max_movement = max(max_movement, change)

        total_bookmakers = len(sources)
        if total_bookmakers == 0:
            return False, 0.0, []

        consensus_ratio = len(movers) / total_bookmakers
        detected = len(movers) >= 2 and consensus_ratio >= 0.4

        if detected:
            log.info(f"  ⚡ 亚盘变动检测: {len(movers)}/{total_bookmakers}家 "
                     f"({consensus_ratio:.0%}) 变动≥0.25球 → 触发 Rule 27")

        return detected, max_movement, movers

    # === Step 6: 综合风险评估 ===

    def _assess_risk(self, report: CrossValidationReport) -> Tuple[RiskLevel, List[str]]:
        """综合风险打分"""
        factors = []
        risk_score = 0

        # 因子1: 共识度
        if report.consensus.level == ConsensusLevel.DIVERGENT:
            risk_score += 4
            factors.append("赔率严重分歧(CV>0.15)")
        elif report.consensus.level == ConsensusLevel.LOW:
            risk_score += 2
            factors.append("赔率分歧较大(CV>0.08)")
        elif report.consensus.level == ConsensusLevel.HIGH:
            risk_score -= 1  # 高共识降低风险
            factors.append("赔率高度共识 → 正向信号")

        # 因子2: 异常源数量
        outlier_count = len(report.outliers)
        if outlier_count >= 3:
            risk_score += 3
            factors.append(f"检测到{outlier_count}个异常源(≥3)→高风险")
        elif outlier_count >= 1:
            risk_score += outlier_count
            names = [o.bookmaker_name for o in report.outliers]
            factors.append(f"检测到{outlier_count}个异常源: {', '.join(names)}")

        # 因子3: 亚盘变动
        if report.asian_movement_detected:
            risk_score += 2
            factors.append(f"亚盘变动≥0.25球 ({report.asian_movement_magnitude}球)")

        # 因子4: DOIT置信度 (多源)
        if report.doit_enhanced.confidence == "low":
            risk_score += 1
            factors.append("DOIT多源分歧大(σ>0.10)")
        elif report.doit_enhanced.confidence == "high":
            risk_score -= 1
            factors.append("DOIT多源高度一致 → 信号可靠")

        # 因子5: 竞彩官方DOIT独立信号 (v1.1 新增)
        if report.doit_enhanced.jc_warning:
            jc_level = report.doit_enhanced.jc_warning_level
            jc_doit = report.doit_enhanced.jc_doit
            if jc_level == "P0":
                risk_score += 3
                factors.append(f"竞彩DOIT={jc_doit:.4f} → P0级防平(独立信号,不受多源稀释)")
            elif jc_level == "P1":
                risk_score += 2
                factors.append(f"竞彩DOIT={jc_doit:.4f} → P1级防平(独立信号)")
            elif jc_level == "P2":
                risk_score += 1
                factors.append(f"竞彩DOIT={jc_doit:.4f} → P2级防平(独立信号)")

        # 判定风险等级
        if risk_score >= 4:
            level = RiskLevel.HIGH
        elif risk_score >= 2:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return level, factors

    def _calculate_star_adjustment(self, report: CrossValidationReport) -> Tuple[int, List[str]]:
        """星级联动计算"""
        adjustment = 0
        reasons = []

        # 共识度联动
        if report.consensus.level == ConsensusLevel.DIVERGENT:
            adjustment -= 2
            reasons.append("多源分歧 → 降2星 + 强制双选")
        elif report.consensus.level == ConsensusLevel.LOW:
            adjustment -= 1
            reasons.append("多源分歧较大 → 降1星")

        # 异常源联动
        if len(report.outliers) >= 2:
            adjustment -= 1
            reasons.append("多源异常 → 额外降1星")

        # DOIT信号联动 (多源)
        if report.doit_enhanced.signal_strength == "strong":
            if report.doit_enhanced.confidence in ("high", "medium"):
                reasons.append("DOIT多源强防平信号 → 建议双选防平")

        # 高共识+无异常 → 正向加成 (在竞彩DOIT覆盖之前)
        if (report.consensus.level == ConsensusLevel.HIGH and
            len(report.outliers) == 0 and
            report.risk_level == RiskLevel.LOW):
            adjustment = min(adjustment + 1, 1)
            reasons.append("多源高度共识+零异常 → +1星信心加持")

        # 竞彩官方DOIT独立信号联动 (v1.1 新增，最后执行，优先级最高)
        # 竞彩DOIT是终极覆盖 — 即使多源高分，竞彩P0/P1也能拉回
        if report.doit_enhanced.jc_warning:
            jc_level = report.doit_enhanced.jc_warning_level
            jc_doit = report.doit_enhanced.jc_doit
            if jc_level == "P0":
                # 竞彩P0防平 → 强制降1星 + 强制双选
                prev_adj = adjustment
                adjustment -= 1
                if prev_adj > 0:
                    reasons.append(f"竞彩DOIT={jc_doit:.4f}(P0防平) → 覆盖正向加成+强制降星({prev_adj:+d}→{adjustment:+d})")
                else:
                    reasons.append(f"竞彩DOIT={jc_doit:.4f} → P0级防平(强制降星+双选)")
            elif jc_level == "P1":
                # P1防平 → 抵消任何正向加成，保持原星级
                if adjustment > 0:
                    reasons.append(f"竞彩DOIT={jc_doit:.4f}(P1防平) → 抵消正向加成({adjustment:+d}→0)")
                    adjustment = 0
                reasons.append(f"竞彩DOIT={jc_doit:.4f} → P1级防平(强制双选)")
            elif jc_level == "P2":
                if adjustment > 0:
                    reasons.append(f"竞彩DOIT={jc_doit:.4f}(P2防平) → 抵消正向加成({adjustment:+d}→0)")
                    adjustment = 0
                reasons.append(f"竞彩DOIT={jc_doit:.4f} → P2级防平(注意平局)")

        return adjustment, reasons

    def _generate_advice(self, report: CrossValidationReport) -> str:
        """生成投注建议"""
        parts = []

        if report.risk_level == RiskLevel.HIGH:
            parts.append("🔴 高风险")
            parts.append("建议等待临场赔率稳定后再分析")
        elif report.risk_level == RiskLevel.MEDIUM:
            parts.append("🟡 中风险")
            parts.append("建议双选防平或降低注码")
        else:
            parts.append("🟢 低风险")

        # 竞彩DOIT信号优先显示
        if report.doit_enhanced.jc_warning:
            jc_level = report.doit_enhanced.jc_warning_level
            jc_doit = report.doit_enhanced.jc_doit
            if jc_level == "P0":
                parts.append(f"竞彩DOIT={jc_doit:.3f}(P0) → 必须双选防平")
            elif jc_level == "P1":
                parts.append(f"竞彩DOIT={jc_doit:.3f}(P1) → 强烈建议双选")
            elif jc_level == "P2":
                parts.append(f"竞彩DOIT={jc_doit:.3f}(P2) → 关注平局")
        elif report.doit_enhanced.signal_strength in ("strong", "moderate"):
            parts.append("多源DOIT防平信号 → 建议双选")
        else:
            parts.append("赔率信号清晰，可正常投注")

        if report.star_adjustment < 0:
            parts.append(f"星级调整: {report.star_adjustment}")
        elif report.star_adjustment > 0:
            parts.append(f"星级加成: +{report.star_adjustment}")

        return " | ".join(parts)


# ============================================
# 便捷函数
# ============================================

def quick_validate(match_id: str, home: str, away: str,
                   odds_list: List[Dict]) -> Dict:
    """快速验证并返回JSON"""
    validator = CrossValidator()
    report = validator.validate(match_id, home, away, odds_list)

    return {
        "match": f"{home} vs {away}",
        "consensus": {
            "level": report.consensus.level.value,
            "cv": report.consensus.cv_coefficient,
            "mean_spf": [report.consensus.mean_home,
                         report.consensus.mean_draw,
                         report.consensus.mean_away],
            "sources_used": report.consensus.sources_used,
        },
        "outliers": [
            {
                "bookmaker": o.bookmaker_name,
                "field": o.field,
                "sigma": o.deviation_sigma,
                "recommendation": o.recommendation,
            }
            for o in report.outliers
        ],
        "weighted_prob": report.weighted_implied,
        "doit": {
            "mean": report.doit_enhanced.doit_mean,
            "std": report.doit_enhanced.doit_std,
            "signal": report.doit_enhanced.signal_strength,
            "confidence": report.doit_enhanced.confidence,
            "range_95ci": list(report.doit_enhanced.doit_range),
            "jc_doit": report.doit_enhanced.jc_doit,
            "jc_signal": report.doit_enhanced.jc_signal_strength,
            "jc_warning": report.doit_enhanced.jc_warning,
            "jc_level": report.doit_enhanced.jc_warning_level,
        },
        "risk": report.risk_level.value,
        "risk_factors": report.risk_factors,
        "star_adjustment": report.star_adjustment,
        "advice": report.betting_advice,
    }


# ============================================
# 自测
# ============================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    print("=" * 60)
    print("  多源交叉验证引擎 v1.0 - 自测")
    print("=" * 60)

    validator = CrossValidator()

    # 测试数据: 天狼星 vs 布鲁马波 (多源赔率)
    test_odds = [
        {"bookmaker": "竞彩官方",  "home": 1.19, "draw": 5.80, "away": 8.55,
         "asian_opening": -1.5, "asian_current": -1.5},
        {"bookmaker": "Pinnacle",   "home": 1.22, "draw": 5.50, "away": 7.80,
         "asian_opening": -1.5, "asian_current": -1.5},
        {"bookmaker": "Bet365",     "home": 1.25, "draw": 5.75, "away": 8.00},
        {"bookmaker": "澳彩",       "home": 1.18, "draw": 6.00, "away": 9.00,
         "asian_opening": -1.5, "asian_current": -1.5},
        {"bookmaker": "威廉希尔",   "home": 1.24, "draw": 5.80, "away": 8.20},
    ]

    report = validator.validate("1001", "天狼星", "布鲁马波", test_odds)

    print(f"\n  比赛: 天狼星 vs 布鲁马波")
    print(f"  ─────────────────────────────")
    print(f"  共识度: {report.consensus.level.value} (CV={report.consensus.cv_coefficient})")
    print(f"  平均赔率: {report.consensus.mean_home}/{report.consensus.mean_draw}/{report.consensus.mean_away}")
    print(f"  数据源: {report.consensus.source_count}家 ({', '.join(report.consensus.sources_used)})")

    print(f"\n  异常检测: {len(report.outliers)}个异常源")
    for o in report.outliers:
        print(f"    ⚠️ {o.bookmaker_name}: {o.field}={o.value} "
              f"(期望[{o.expected_range[0]}-{o.expected_range[1]}], {o.deviation_sigma}σ)")

    print(f"\n  加权隐含概率:")
    for k, v in report.weighted_implied.items():
        print(f"    {k}: {v}")

    print(f"\n  DOIT多源增强:")
    print(f"    多源均值: {report.doit_enhanced.doit_mean:.4f}")
    print(f"    多源标准差: {report.doit_enhanced.doit_std:.4f}")
    print(f"    多源信号: {report.doit_enhanced.signal_strength}")
    print(f"    多源置信度: {report.doit_enhanced.confidence}")
    print(f"    95%CI: [{report.doit_enhanced.doit_range[0]:.4f}, {report.doit_enhanced.doit_range[1]:.4f}]")
    print(f"    ─────────────────────────")
    print(f"    竞彩DOIT: {report.doit_enhanced.jc_doit:.4f}")
    print(f"    竞彩信号: {report.doit_enhanced.jc_signal_strength}")
    print(f"    竞彩防平: {'⚠️ ' + report.doit_enhanced.jc_warning_level if report.doit_enhanced.jc_warning else '✅ 无'}")

    print(f"\n  亚盘变动: {'检测到' if report.asian_movement_detected else '无变动'}")
    print(f"  综合风险: {report.risk_level.value}")
    print(f"  风险因子: {'; '.join(report.risk_factors)}")
    print(f"  星级调整: {report.star_adjustment}")
    print(f"  投注建议: {report.betting_advice}")

    # 第二组测试: 制造异常源
    print(f"\n{'─' * 60}")
    print(f"  测试2: 含异常源的赔率")
    test_odds_anomaly = test_odds[:4] + [
        {"bookmaker": "异常庄家X", "home": 1.80, "draw": 3.50, "away": 3.50},  # 明显偏离
    ]
    report2 = validator.validate("1002", "韦斯特罗斯", "尤尔加登", test_odds_anomaly)

    print(f"  共识度: {report2.consensus.level.value} (CV={report2.consensus.cv_coefficient})")
    print(f"  异常检测: {len(report2.outliers)}个异常源")
    for o in report2.outliers:
        print(f"    ⚠️ {o.bookmaker_name}: {o.field}={o.value} "
              f"({o.deviation_sigma}σ) → {o.recommendation}")
    print(f"  竞彩DOIT: {report2.doit_enhanced.jc_doit:.4f} "
          f"(信号:{report2.doit_enhanced.jc_signal_strength} "
          f"防平:{'⚠️'+report2.doit_enhanced.jc_warning_level if report2.doit_enhanced.jc_warning else '无'})")
    print(f"  星级调整: {report2.star_adjustment}")
    print(f"  投注建议: {report2.betting_advice}")

    print(f"\n{'─' * 60}")
    print(f"  ✅ 交叉验证引擎自测完成")
