"""
services/orchestrator/__init__.py
==================================
Orchestrator 调度核心模块。

导出主要类：
- Orchestrator: 调度核心
- PredictionRequest: 预测请求
- FusionResult: 融合结果
- ToolResult: 单工具结果
"""

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