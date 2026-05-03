# =============================================================================
# services/orchestrator/__init__.py
# =============================================================================
#
# 【模块说明】
# ------------
# orchestrator/ 是整个微服务的"调度中心"。
# 想象一下：你要请 10 个专家来评估一个候选人，
# 你需要：
#   1. 知道每个专家的联系方式（registry）
#   2. 同时请他们来评估（core）
#   3. 收集他们的意见，打一个综合分（scoring）
# 这个文件夹就是干这三件事的。
#
# 【三个子文件的作用】
# -------------------
# registry.py   → 10个专家的联系方式本（叫什么名字？在哪里办公？）
# core.py       → 同时请 10 个专家来评估，收集结果
# scoring.py    → 综合每个专家的意见，给出最终评分
#
# 【核心概念：什么是"融合"？】
# --------------------------
# 一个肽序列的"抗氧化能力"，需要综合考虑：
#   - AnOxPePred 的预测值（权重 1.0）
#   - 毒性检测结果（毒性高则扣分）
#   - 溶血检测结果（溶血性高则扣分）
# 最终的 0.0~1.0 分数，就是把这 3 个结果"融合"出来的。
#
# 【重要类/函数导出】
# ------------------
# - Orchestrator           : 调度核心，同时调用多个工具
# - PredictionRequest      : 预测请求（要预测什么序列？调用哪些工具？）
# - ToolResult             : 单个工具的预测结果
# - FusionResult           : 融合后的最终结果
# - TOOL_REGISTRY          : 工具配置表（所有工具的 URL、权重等）
# - compute_fused_score()  : 计算融合分数
# - rank_candidates()      : 对多个候选序列排序

from .core import Orchestrator, PredictionRequest, FusionResult, ToolResult
from .registry import TOOL_REGISTRY, get_tool, get_tools_by_type, get_p0_tools, ToolConfig
from .scoring import compute_fused_score, rank_candidates, is_safe_candidate, ScoringConfig

__all__ = [
    "Orchestrator",
    "PredictionRequest",
    "FusionResult",
    "ToolResult",
    "TOOL_REGISTRY",
    "get_tool",
    "get_tools_by_type",
    "get_p0_tools",
    "ToolConfig",
    "compute_fused_score",
    "rank_candidates",
    "is_safe_candidate",
    "ScoringConfig",
]