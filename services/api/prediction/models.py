"""预测功能的数据模型"""

from typing import Any
from pydantic import BaseModel, Field


class SinglePredictRequest(BaseModel):
    """单序列预测请求。"""
    sequence: str = Field(..., min_length=1, max_length=5000, description="氨基酸序列")
    peptide_id: str | None = Field(None, description="肽 ID")
    tools: list[str] | None = Field(None, description="指定工具列表，None=所有 P0 工具")


class BatchPredictRequest(BaseModel):
    """批量预测请求。"""
    sequences: list[SinglePredictRequest] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="序列列表（最多 1000 条）"
    )
    tools: list[str] | None = Field(None, description="指定工具列表")
    top_k: int = Field(50, ge=1, le=1000, description="返回 top k 结果")


class ToolResultResponse(BaseModel):
    """单个工具的预测结果。"""
    tool_name: str
    score: float | None
    label: str | None
    latency_ms: float
    error: str | None


class FusionResultResponse(BaseModel):
    """融合结果（用于 API 响应）。"""
    peptide_id: str
    sequence: str
    fused_score: float | None
    fused_label: str | None
    total_latency_ms: float
    scoring_details: dict[str, Any] | None
    tool_results: list[ToolResultResponse]


class BatchPredictResponse(BaseModel):
    """批量预测响应。"""
    success: bool
    total: int
    returned: int
    results: list[FusionResultResponse]
