"""预测功能的数据转换工具"""

from ...orchestrator.core import FusionResult
from .models import FusionResultResponse, ToolResultResponse


def to_response(result: FusionResult) -> FusionResultResponse:
    """将 FusionResult 转换为 API 响应模型。"""
    return FusionResultResponse(
        peptide_id=result.peptide_id,
        sequence=result.sequence,
        fused_score=result.fused_score,
        fused_label=result.fused_label,
        total_latency_ms=result.total_latency_ms,
        scoring_details=result.scoring_details,
        tool_results=[
            ToolResultResponse(
                tool_name=r.tool_name,
                score=r.score,
                label=r.label,
                latency_ms=r.latency_ms,
                error=r.error
            )
            for r in result.tool_results
        ]
    )
