"""
services/orchestrator/scoring.py
=================================

【这个文件是什么？】
--------------------
scoring.py 是整个系统的"评分引擎"。

想象一下：一个学生（肽序列）参加了 10 门考试（10 个工具的预测）。
每门考试的分值范围都是 0-100，但重要性不一样：
  - 语文（抗氧化）占 1.0 倍权重
  - 数学（毒性检测）因为太重要，占 1.5 倍权重
  - 历史（过敏原性）也很重要，占 1.3 倍权重

最终这个学生有一门考试分数很高（抗氧化 95 分），
但另一门考试分数很低（毒性 80 分，表示有毒），
这时候要"惩罚"他，因为安全性比功效更重要。

这个文件就是干这件事的：把多个工具的预测结果"融合"成一个综合分数。

【核心概念：什么是"融合"？】
--------------------------
"融合"就是把多个工具的结果合并成一个。

举例：一个肽序列 "YVPLPNVPQG" 的预测结果：

  工具           | 预测分数 | 标签         | 权重
  --------------|---------|-------------|------
  anoxpepred    | 0.82    | antioxidant | 1.0
  toxipred3    | 0.15    | non-toxic   | 1.5
  hemopi2      | 0.22    | non-hemolytic| 1.5
  algpred2     | 0.10    | non-allergen| 1.3

融合的思路：
  1. 加权平均：考虑每个工具的重要性
  2. 安全惩罚：如果毒性/溶血/过敏原超标，综合分数要扣减
  3. 多数投票：最终标签看哪个标签出现次数最多

【为什么需要"惩罚"机制？】
--------------------------
因为在护肤领域，"安全性"比"功效"更重要。

举例：
  - 一个肽抗氧化能力很强（0.95 分），但有毒（0.8 分）
  - 另一个肽抗氧化能力一般（0.70 分），但完全安全（0.0 分）

如果只做加权平均：0.95 可能排第一，但这是危险的。
加上惩罚机制后：第二个肽因为安全，会排在前面。

【什么是"多数投票"？】
----------------------
有 3 个工具都说这个肽是 "antioxidant"，只有 1 个说是 "non-antioxidant"。
那最终标签就是 "antioxidant"（多数胜出）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .core import ToolResult


# ═══════════════════════════════════════════════════════════════════════════════
# 第一部分：工具权重配置（TOOL_WEIGHTS）
# ═══════════════════════════════════════════════════════════════════════════════
#
#【什么是"权重"？】
#----------------
# 权重就像是一本书的"重要程度"。
# 如果语文权重是 1.0，数学权重是 1.5，
# 那么数学考 100 分，相当于语文考 150 分的效果。
#
# 在这个系统里：
#   - 安全性工具（toxipred3、hemopi2、algpred2）权重更高（1.3-1.5）
#     因为"安全是底线"
#   - 核心功效工具（anoxpepred、tipred）权重 1.0
#   - 辅助工具（mhcflurry、bepipred3）权重较低（0.5-0.8）
#     因为它们是参考性的，不是决定性的

TOOL_WEIGHTS: dict[str, float] = {
    # ── 核心功效工具 ────────────────────────────────────────────
    # 这些工具直接决定肽的护肤功效（抗氧化、酪氨酸酶抑制）
    # 如果分数高，说明这个肽确实有效果

    "anoxpepred":   1.0,
    # 抗氧化肽预测。如果预测为抗氧化，说明这个肽有护肤功效。
    # 权重 1.0 是"基准"，其他工具与之比较。

    "tipred":       1.0,
    # 酪氨酸酶抑制肽预测。如果分数高，说明能抑制黑色素生成。
    # 权重也是 1.0，因为这也是核心功效。

    # ── 安全性工具（权重更高）────────────────────────────────────
    # 这些工具决定肽能不能用。如果安全性分数太高，直接淘汰。
    # 为什么权重更高？因为"安全第一"——无效的肽最多浪费钱，
    # 但有毒的肽会害人！

    "toxipred3":    1.5,
    # 毒性检测。分数越低越好（0=无毒，1=有毒）。
    # 权重 1.5 表示：毒性检测比抗氧化更重要。
    # 如果有毒，哪怕抗氧化满分也不能用。

    "hemopi2":      1.5,
    # 溶血检测。分数越低越好（0=不溶血，1=完全溶血）。
    # 权重 1.5，与毒性同等重要。
    # 如果会溶血（破坏红细胞），绝对不能用。

    "algpred2":     1.3,
    # 过敏原性检测。分数越低越好（0=不过敏，1=强过敏原）。
    # 权重 1.3，比核心功效稍高，但比毒性/溶血低一点。

    # ── 免疫原性参考工具 ─────────────────────────────────────────
    # 这些工具提供参考信息，帮助全面评估，
    # 但不是决定性因素（权重较低）

    "mhcflurry":    0.8,
    # MHC 结合亲和力预测。主要看会不会被免疫系统识别。
    # 权重 0.8，低于核心功效。因为对于外用护肤来说，
    # 免疫原性没有抗氧化/安全性重要。

    "bepipred3":    0.5,
    # B 细胞表位预测。这个指标与护肤功效关系较小，
    # 主要用于科研参考，权重最低（0.5）。

    # ── 递送相关工具 ─────────────────────────────────────────────
    # 这些工具预测肽能不能穿透细胞膜（细胞穿膜肽，CPP）
    # 如果能穿透，效果更好（权重稍高）

    "plm4cpps":     0.9,
    # pLM4CPPs 是"主要的"CPP 预测工具（优先级 P1），
    # 权重 0.9，接近核心功效。因为如果肽穿不透细胞膜，
    # 抗氧化能力再好也没用（无法到达作用靶点）。

    "graphcpp":     0.7,
    # GraphCPP 是 CPP 备选工具（优先级 P2），权重 0.7。
    # 作为 plm4cpps 的备选，不承担主要预测任务。

    "mlcpp":        0.5,
    # MLCPP 是最弱的 CPP 工具，权重 0.5。
    # 主要用于快速初筛，正规评估主要靠 plm4cpps。
}


# ═══════════════════════════════════════════════════════════════════════════════
# 第二部分：评分配置（ScoringConfig）
# ═══════════════════════════════════════════════════════════════════════════════
#
#【什么是"惩罚系数"？】
#--------------------
# 惩罚系数决定了"如果安全性超标，要扣多少分"。
#
# 举例：toxicity_penalty = 2.0 意思是：
#   如果毒性分数超过阈值（比如 0.5），每超 0.1 分，综合分数打 8 折
#   超 0.2 分 → 打 6 折
#   超 0.3 分 → 打 4 折
#   ...以此类推
#
# 换句话说：毒性越高，最终分数越低，低到一定程度直接淘汰

@dataclass
class ScoringConfig:
    """
    融合评分策略的配置参数。

    【什么时候用？】
    如果默认的评分策略不满足需求（比如想要更严格的安全标准），
    可以创建自定义的 ScoringConfig 对象。

    【例子】
    # 默认配置（所有阈值都是 0.5，惩罚系数都是 2.0）
    config = ScoringConfig()

    # 更严格的配置（更注重安全性）
    strict_config = ScoringConfig(
        toxicity_penalty=3.0,    # 毒性超标惩罚更重
        min_safety_score=0.3     # 安全分数下限更高
    )
    """

    # ── 毒性惩罚配置 ────────────────────────────────────────────

    toxicity_penalty: float = 2.0
    """
    毒性超标惩罚系数。
    数值越大，毒性超标时扣分越狠。
    默认 2.0 意味着：毒性每超过阈值 0.1，分数打 8 折（1-2*0.1*2=0.6）
    """

    toxicity_threshold: float = 0.5
    """
    毒性惩罚起始阈值。
    只有当毒性分数 > 0.5 时才开始惩罚。
    低于 0.5 说明相对安全，不惩罚。
    """

    # ── 溶血惩罚配置 ────────────────────────────────────────────

    hemolytic_penalty: float = 2.0
    """
    溶血超标惩罚系数。与毒性惩罚类似。
    """

    hemolytic_threshold: float = 0.5
    """
    溶血惩罚起始阈值。
    """

    # ── 过敏原性惩罚配置 ─────────────────────────────────────────

    allergenicity_penalty: float = 2.0
    """
    过敏原性超标惩罚系数。
    """

    allergenicity_threshold: float = 0.5
    """
    过敏原性惩罚起始阈值。
    """

    # ── 安全下限配置 ────────────────────────────────────────────

    min_safety_score: float = 0.2
    """
    安全分数下限。
    如果最终综合分数低于 0.2，直接淘汰（设为 0.0）。

    这个参数防止"毒性很高但其他分数拉高平均值"的情况。
    """

    # ── 高级配置 ────────────────────────────────────────────────

    use_pareto: bool = False
    """
    是否使用 Pareto 最优筛选（暂未实现）。
    Pareto 筛选的意思是：找出"无法再改进"的候选序列。
    比如序列 A 在所有维度都比序列 B 差，那序列 B 就不用比了。
    """


# ═══════════════════════════════════════════════════════════════════════════════
# 第三部分：核心评分函数
# ═══════════════════════════════════════════════════════════════════════════════
#
#【compute_fused_score 是做什么的？】
#------------------------------------
# 这是整个评分模块的核心函数。
# 输入：多个工具的预测结果（ToolResult 列表）
# 输出：融合后的综合分数、标签、详细分解

def compute_fused_score(
    results: list[ToolResult],
    config: ScoringConfig | None = None
) -> tuple[float | None, str | None, dict[str, Any]]:
    """
    计算多工具预测结果的融合分数。

    【输入】
    - results: 多个 ToolResult 的列表，比如 [anoxpepred结果, toxipred3结果, hemopi2结果]
    - config: 评分配置（如果不提供，使用默认配置）

    【输出】（元组格式）
    - 第1个值：融合分数（0.0 ~ 1.0），如果无法计算则是 None
    - 第2个值：融合标签（比如 "antioxidant" 或 "non-antioxidant"），无法确定则是 None
    - 第3个值：详细分解（包含每一步计算的过程，方便调试）

    【计算流程】
    ════════════════════════════════════════════════════════════════════
    ║  Step 1: 过滤无效结果                                          ║
    ║  - 去掉调用失败的（error != None）                             ║
    ║  - 去掉没有分数的（score is None）                              ║
    ║  → 如果没有有效结果，返回错误                                   ║
    ╠═══════════════════════════════════════════════════════════════════
    ║  Step 2: 计算各工具的加权分数                                    ║
    ║  - 查 TOOL_WEIGHTS 获取每个工具的权重                           ║
    ║  - 加权分数 = 原始分数 × 权重                                    ║
    ║  例：anoxpepred 分数 0.82，权重 1.0 → 加权分数 0.82            ║
    ║      toxipred3 分数 0.15，权重 1.5 → 加权分数 0.225             ║
    ╠═══════════════════════════════════════════════════════════════════
    ║  Step 3: 计算基础融合分数                                        ║
    ║  - 总权重 = 所有工具权重之和                                     ║
    ║  - 加权和 = 所有工具加权分数之和                                  ║
    ║  - 基础分数 = 加权和 / 总权重                                     ║
    ╠═══════════════════════════════════════════════════════════════════
    ║  Step 4: 应用安全性惩罚                                          ║
    ║  - 如果毒性 > 阈值，分数打折                                      ║
    ║  - 如果溶血 > 阈值，分数打折                                      ║
    ║  - 如果过敏原性 > 阈值，分数打折                                  ║
    ║  乘法叠加：toxipred3打折0.8 × hemopi2打折0.9 = 整体0.72         ║
    ╠═══════════════════════════════════════════════════════════════════
    ║  Step 5: 计算最终分数                                            ║
    ║  - 最终分数 = 基础分数 × 惩罚乘数                                 ║
    ║  - 如果最终分数 < min_safety_score，直接设为 0.0                  ║
    ╠═══════════════════════════════════════════════════════════════════
    ║  Step 6: 标签多数投票                                            ║
    ║  - 统计所有工具返回的标签                                        ║
    ║  - 出现次数最多的标签作为最终标签                                ║
    ╚═══════════════════════════════════════════════════════════════════

    【实际例子】
    ════════════════════════════════════════════════════════════════════

    输入 results：
        ToolResult(tool_name="anoxpepred", score=0.82, label="antioxidant")
        ToolResult(tool_name="toxipred3", score=0.15, label="non-toxic")
        ToolResult(tool_name="hemopi2", score=0.22, label="non-hemolytic")
        ToolResult(tool_name="algpred2", score=0.10, label="non-allergen")

    Step 2 - 计算加权分数：
        anoxpepred: 0.82 × 1.0 = 0.82
        toxipred3:  0.15 × 1.5 = 0.225
        hemopi2:    0.22 × 1.5 = 0.33
        algpred2:   0.10 × 1.3 = 0.13

        总权重 = 1.0 + 1.5 + 1.5 + 1.3 = 5.3
        加权和 = 0.82 + 0.225 + 0.33 + 0.13 = 1.505

    Step 3 - 基础融合分数：
        1.505 / 5.3 = 0.284

    Step 4 - 检查惩罚：
        toxipred3: 0.15 < 0.5，不惩罚
        hemopi2:   0.22 < 0.5，不惩罚
        algpred2:   0.10 < 0.5，不惩罚
        → 惩罚乘数 = 1.0

    Step 5 - 最终分数：
        0.284 × 1.0 = 0.284

    Step 6 - 标签投票：
        labels = ["antioxidant", "non-toxic", "non-hemolytic", "non-allergen"]
        计数：每个标签都只出现 1 次
        → 无法判断，选择 "unknown"

    输出：(0.284, "unknown", {...})

    【关于"惩罚"的实际效果】
    ════════════════════════════════════════════════════════════════════

    假设 toxipred3 预测分数是 0.7（超过 0.5 阈值）：
        excess = 0.7 - 0.5 = 0.2
        penalty = 2.0 × 0.2 × 2 = 0.8
        penalty_multiplier = max(0.0, 1.0 - 0.8) = 0.2

    意思是：基础分数打 2 折！

    如果同时 toxipred3 和 hemopi2 都超标：
        toxipred3 打折 0.2
        hemopi2   打折 0.2（假设也超标）
        → 整体惩罚乘数 = 0.2 × 0.2 = 0.04

    意思是：基础分数打 4 折再打 5 折，只有原来的 4%！

    这确保了：哪怕抗氧化分数再高，只要安全性有问题，分数就会被压得很低。
    """
    if config is None:
        config = ScoringConfig()

    # Step 1: 过滤无效结果
    # 去掉：调用失败的（error != None）、没有分数的（score is None）
    valid_results = [r for r in results if r.error is None and r.score is not None]

    # 如果没有有效结果，无法计算融合分数
    if not valid_results:
        return None, "no_valid_results", {"error": "No valid tool results"}

    details: dict[str, Any] = {}
    score_components: dict[str, dict[str, float]] = {}

    # ── Step 2: 计算各工具的加权分数 ─────────────────────────────

    for r in valid_results:
        # 从 TOOL_WEIGHTS 获取权重，默认 1.0（如果没配置这个工具）
        weight = TOOL_WEIGHTS.get(r.tool_name, 1.0)
        # 如果没有分数，当作 0.0 处理
        raw_score = r.score if r.score is not None else 0.0
        # 记录：原始分数、权重、加权分数
        score_components[r.tool_name] = {
            "raw_score": raw_score,
            "weight": weight,
            "weighted_score": raw_score * weight
        }

    # ── Step 3: 计算基础融合分数（加权平均） ───────────────────────

    total_weight = sum(score_components[tool_name]["weight"] for tool_name in score_components)
    weighted_sum = sum(score_components[tool_name]["weighted_score"] for tool_name in score_components)
    base_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # ── Step 4: 应用安全性惩罚 ────────────────────────────────────
    #
    # 惩罚的逻辑：
    #   1. 如果毒性分数超过阈值（0.5），说明这个肽有毒，要扣分
    #   2. 扣多少？用 (toxicity_penalty × excess × 2) 来计算
    #   3. 惩罚是"乘法"的：基础分数 × 惩罚系数
    #   4. 如果多个工具都超标，惩罚会叠加（连乘）
    #
    # 举例：toxipred3 分数 0.7，阈值 0.5
    #   excess = 0.7 - 0.5 = 0.2
    #   penalty = 2.0 × 0.2 × 2 = 0.8
    #   multiplier = max(0, 1 - 0.8) = 0.2
    #   → 分数打 2 折

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

    # ── Step 5: 计算最终分数 ─────────────────────────────────────

    final_score = max(0.0, base_score * penalty_multiplier)

    # 安全下限检查：如果分数低于 0.2，直接淘汰（设为 0.0）
    if final_score < config.min_safety_score:
        final_score = 0.0

    # ── Step 6: 标签多数投票 ─────────────────────────────────────
    #
    # 投票逻辑：
    #   统计每个标签出现的次数
    #   出现次数最多的标签就是最终标签
    #
    # 如果所有标签都只出现一次（平票），选择字典序第一个

    labels = [r.label for r in valid_results if r.label]
    if labels:
        label_counts: dict[str, int] = {}
        for label in labels:
            label_counts[label] = label_counts.get(label, 0) + 1
        fused_label = max(label_counts.items(), key=lambda item: item[1])[0]
    else:
        fused_label = "unknown"

    # ── Step 7: 组装详细信息 ─────────────────────────────────────
    #
    # 返回一个字典，包含所有计算细节，方便调试和解释：
    #   - base_score: 加权平均分数（惩罚前）
    #   - penalty_multiplier: 惩罚乘数
    #   - penalty_reasons: 哪些工具触发了惩罚
    #   - score_components: 每个工具的详细分数
    #   - tool_count: 成功调用的工具数量
    #   - failed_count: 失败的工具数量

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
    对候选肽序列进行排序，返回 top_k 个最优候选。

    【使用场景】
    当我们有 100 条候选肽序列，需要选出最好的 10 条时使用。

    【参数】
    - results: FusionResult 列表（每条肽的融合预测结果）
    - top_k: 返回前几名（默认 50）
    - sort_key: 按什么字段排序（默认 "fused_score"，也可选 "fused_label" 等）

    【返回值】
    - 排序后的前 k 个 FusionResult

    【例子】
    # 假设有 100 个候选肽
    all_candidates = [fusion_result_1, fusion_result_2, ...]

    # 选出分数最高的 10 个
    top_10 = rank_candidates(all_candidates, top_k=10)

    # 打印结果
    for i, candidate in enumerate(top_10, 1):
        print(f"第{i}名: {candidate.peptide_id} - 分数: {candidate.fused_score}")
    """
    # 过滤掉没有分数的结果（排序时这些没有意义）
    valid = [r for r in results if getattr(r, sort_key, None) is not None]
    # 按 sort_key 降序排序（分数高的在前）
    valid.sort(key=lambda x: getattr(x, sort_key, 0), reverse=True)
    # 返回前 top_k 个
    return valid[:top_k]


def is_safe_candidate(
    results: list[ToolResult],
    toxicity_threshold: float = 0.5,
    hemolytic_threshold: float = 0.5,
    allergenicity_threshold: float = 0.5
) -> tuple[bool, list[str]]:
    """
    快速检查候选肽是否通过安全阈值（不涉及融合分数计算）。

    【与 compute_fused_score 的区别】
    - compute_fused_score：计算综合分数（加权平均 + 惩罚）
    - is_safe_candidate：只检查"安全性工具是否超标"

    【使用场景】
    在计算融合分数之前，先快速检查一下是否有明显的安全问题。
    如果安全性工具都超标，可能直接跳过这个候选，不用浪费算力。

    【参数】
    - results: 各工具的预测结果（ToolResult 列表）
    - toxicity_threshold: 毒性阈值（默认 0.5）
    - hemolytic_threshold: 溶血阈值（默认 0.5）
    - allergenicity_threshold: 过敏原性阈值（默认 0.5）

    【返回值】
    - (是否安全, 不满足条件的工具列表)
    - 如果所有安全性工具都低于阈值，返回 (True, [])

    【例子】
    results = [
        ToolResult(tool_name="toxipred3", score=0.15, ...),   # 低于 0.5，安全
        ToolResult(tool_name="hemopi2", score=0.22, ...),     # 低于 0.5，安全
        ToolResult(tool_name="algpred2", score=0.10, ...),    # 低于 0.5，安全
    ]

    is_safe, failed = is_safe_candidate(results)
    print(is_safe)  # True
    print(failed)   # []

    ---

    results = [
        ToolResult(tool_name="toxipred3", score=0.75, ...),   # 超过 0.5，不安全！
        ToolResult(tool_name="hemopi2", score=0.22, ...),     # 低于 0.5，安全
    ]

    is_safe, failed = is_safe_candidate(results)
    print(is_safe)  # False
    print(failed)   # ["toxipred3:score=0.750>threshold=0.5"]
    """
    failed_checks = []

    for r in results:
        # 跳过调用失败或没有分数的
        if r.error is not None or r.score is None:
            continue

        # 毒性检查：分数越高越危险
        if r.tool_name == "toxipred3" and r.score > toxicity_threshold:
            failed_checks.append(f"toxipred3:score={r.score:.3f}>threshold={toxicity_threshold}")

        # 溶血检查：分数越高越危险
        if r.tool_name == "hemopi2" and r.score > hemolytic_threshold:
            failed_checks.append(f"hemopi2:score={r.score:.3f}>threshold={hemolytic_threshold}")

        # 过敏原性检查：分数越高越危险
        if r.tool_name == "algpred2" and r.score > allergenicity_threshold:
            failed_checks.append(f"algpred2:score={r.score:.3f}>threshold={allergenicity_threshold}")

    # 如果没有任何失败检查，说明通过安全阈值
    return len(failed_checks) == 0, failed_checks