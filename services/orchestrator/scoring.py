"""
services/orchestrator/scoring.py
================================
Scoring Engine — 融合评分引擎。

多工具结果融合策略：
- 默认：加权平均 + 安全惩罚
- 后期升级：ML 模型融合、Pareto 最优筛选
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .core import ToolResult


# ═══════════════════════════════════════════════════════════════════════════
# 评分权重配置
# ═══════════════════════════════════════════════════════════════════════════

# 各工具的功能权重（数值越高 = 在融合时权重越大）
# 安全性工具（毒性/溶血/过敏原）权重更高，因为安全是底线
TOOL_WEIGHTS: dict[str, float] = {
    # ── 核心功效工具 ────────────────────────────────────
    "anoxpepred":   1.0,   # 抗氧化（核心护肤功效）
    "tipred":       1.0,   # 酪氨酸酶抑制（核心护肤功效）

    # ── 安全性工具（权重更高）──────────────────────────
    "toxipred3":    1.5,   # 毒性（安全门槛，必须低毒）
    "hemopi2":      1.5,   # 溶血（安全门槛，必须低溶血）
    "algpred2":     1.3,   # 过敏原性（安全门槛）

    # ── 免疫原性参考工具 ──────────────────────────────
    "mhcflurry":    0.8,   # MHC 结合亲和力（免疫原性风险）
    "bepipred3":    0.5,   # B 细胞表位（参考指标）

    # ── 递送相关工具 ────────────────────────────────────
    "plm4cpps":     0.9,   # CPP 预测（递送潜力）
    "graphcpp":     0.7,   # CPP 预测（备选）
    "mlcpp":        0.5,   # CPP 预测（备选）
}


# ═══════════════════════════════════════════════════════════════════════════
# 评分配置
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ScoringConfig:
    """
    融合评分策略配置。

    Attributes
    ----------
    toxicity_penalty : float
        毒性超标惩罚系数。分数 > threshold 时开始惩罚
    toxicity_threshold : float
        毒性惩罚起始阈值（默认 0.5）
    hemolytic_penalty : float
        溶血超标惩罚系数
    hemolytic_threshold : float
        溶血惩罚起始阈值
    allergenicity_penalty : float
        过敏原性超标惩罚系数
    allergenicity_threshold : float
        过敏原性惩罚起始阈值
    min_safety_score : float
        安全分数下限（低于此值直接淘汰）
    use_pareto : bool
        是否使用 Pareto 最优筛选
    """
    # 毒性惩罚（分数 > 0.5 视为有风险）
    toxicity_penalty: float = 2.0
    toxicity_threshold: float = 0.5

    # 溶血惩罚
    hemolytic_penalty: float = 2.0
    hemolytic_threshold: float = 0.5

    # 过敏原性惩罚
    allergenicity_penalty: float = 2.0
    allergenicity_threshold: float = 0.5

    # 安全下限
    min_safety_score: float = 0.2

    # Pareto 优化（暂未实现）
    use_pareto: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# 核心评分函数
# ═══════════════════════════════════════════════════════════════════════════

def compute_fused_score(
    results: list[ToolResult],
    config: ScoringConfig | None = None
) -> tuple[float | None, str | None, dict[str, Any]]:
    """
    计算融合分数。

    策略：
    1. 过滤掉失败的结果（error != None）
    2. 计算各工具的加权分数
    3. 对安全性超标的结果应用惩罚
    4. 加权平均得到最终分数
    5. 标签采用多数投票

    Parameters
    ----------
    results : list[ToolResult]
        各工具的预测结果
    config : ScoringConfig | None
        评分策略配置

    Returns
    -------
    tuple[float | None, str | None, dict[str, Any]]
        (融合分数, 融合标签, 详细分解字典)
    """
    if config is None:
        config = ScoringConfig()

    valid_results = [r for r in results if r.error is None and r.score is not None]

    if not valid_results:
        return None, "no_valid_results", {"error": "No valid tool results"}

    details: dict[str, Any] = {}
    score_components: dict[str, dict[str, float]] = {}

    # ── Step 1: 计算各工具的加权分数 ──────────────────────
    for r in valid_results:
        weight = TOOL_WEIGHTS.get(r.tool_name, 1.0)
        raw_score = r.score if r.score is not None else 0.0
        score_components[r.tool_name] = {
            "raw_score": raw_score,
            "weight": weight,
            "weighted_score": raw_score * weight
        }

    # ── Step 2: 计算基础融合分数（加权平均） ───────────────
    total_weight = sum(score_components[tool_name]["weight"] for tool_name in score_components)
    weighted_sum = sum(score_components[tool_name]["weighted_score"] for tool_name in score_components)
    base_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # ── Step 3: 应用安全性惩罚 ────────────────────────────
    penalty_multiplier = 1.0
    penalty_reasons: list[str] = []

    for r in valid_results:
        score = r.score
        if score is None:
            continue

        tool_name = r.tool_name

        # 毒性惩罚
        if tool_name == "toxipred3" and score > config.toxicity_threshold:
            excess = score - config.toxicity_threshold
            penalty = config.toxicity_penalty * excess * 2
            penalty_multiplier *= max(0.0, 1.0 - penalty)
            penalty_reasons.append(f"toxicity_penalty:{penalty:.3f}")

        # 溶血惩罚
        if tool_name == "hemopi2" and score > config.hemolytic_threshold:
            excess = score - config.hemolytic_threshold
            penalty = config.hemolytic_penalty * excess * 2
            penalty_multiplier *= max(0.0, 1.0 - penalty)
            penalty_reasons.append(f"hemolytic_penalty:{penalty:.3f}")

        # 过敏原性惩罚
        if tool_name == "algpred2" and score > config.allergenicity_threshold:
            excess = score - config.allergenicity_threshold
            penalty = config.allergenicity_penalty * excess * 2
            penalty_multiplier *= max(0.0, 1.0 - penalty)
            penalty_reasons.append(f"allergenicity_penalty:{penalty:.3f}")

    # ── Step 4: 计算最终分数 ─────────────────────────────
    final_score = max(0.0, base_score * penalty_multiplier)

    # 安全下限检查
    if final_score < config.min_safety_score:
        final_score = 0.0

    # ── Step 5: 标签投票 ────────────────────────────────────
    labels = [r.label for r in valid_results if r.label]
    if labels:
        # 简单多数投票
        label_counts: dict[str, int] = {}
        for label in labels:
            label_counts[label] = label_counts.get(label, 0) + 1
        fused_label = max(label_counts.items(), key=lambda item: item[1])[0]
    else:
        fused_label = "unknown"

    # ── Step 6: 组装详细信息 ─────────────────────────────
    details = {
        "base_score": round(base_score, 4),
        "penalty_multiplier": round(penalty_multiplier, 4),
        "penalty_reasons": penalty_reasons,
        "score_components": {
            tool_name: {k: round(v, 4) for k, v in comp.items()}
            for tool_name, comp in score_components.items()
        },
        "tool_count": len(valid_results),
        "failed_count": len(results) - len(valid_results)
    }

    return round(final_score, 4), fused_label, details


def rank_candidates(
    results: list,
    top_k: int = 50,
    sort_key: str = "fused_score"
) -> list:
    """
    对候选肽排序，取 top_k。

    Parameters
    ----------
    results : list[FusionResult]
        融合结果列表
    top_k : int
        返回前 k 个
    sort_key : str
        排序字段（支持 fused_score, fused_label, total_latency_ms）

    Returns
    -------
    list
        排序后的前 k 个结果
    """
    # 过滤掉没有分数的结果
    valid = [r for r in results if getattr(r, sort_key, None) is not None]
    valid.sort(key=lambda x: getattr(x, sort_key, 0), reverse=True)
    return valid[:top_k]


# ═══════════════════════════════════════════════════════════════════════════
# 辅助：快速检查候选是否通过安全阈值
# ═══════════════════════════════════════════════════════════════════════════

def is_safe_candidate(
    results: list[ToolResult],
    toxicity_threshold: float = 0.5,
    hemolytic_threshold: float = 0.5,
    allergenicity_threshold: float = 0.5
) -> tuple[bool, list[str]]:
    """
    快速检查候选是否通过安全阈值。

    Parameters
    ----------
    results : list[ToolResult]
        各工具的预测结果
    toxicity_threshold : float
        毒性阈值
    hemolytic_threshold : float
        溶血阈值
    allergenicity_threshold : float
        过敏原性阈值

    Returns
    -------
    tuple[bool, list[str]]
        (是否安全, 不满足条件的工具列表)
    """
    failed_checks = []

    for r in results:
        if r.error is not None or r.score is None:
            continue

        if r.tool_name == "toxipred3" and r.score > toxicity_threshold:
            failed_checks.append(f"toxipred3:score={r.score:.3f}>threshold={toxicity_threshold}")

        if r.tool_name == "hemopi2" and r.score > hemolytic_threshold:
            failed_checks.append(f"hemopi2:score={r.score:.3f}>threshold={hemolytic_threshold}")

        if r.tool_name == "algpred2" and r.score > allergenicity_threshold:
            failed_checks.append(f"algpred2:score={r.score:.3f}>threshold={allergenicity_threshold}")

    return len(failed_checks) == 0, failed_checks