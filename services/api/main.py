"""
services/api/main.py
====================
Orchestrator REST API — 对外暴露的统一 HTTP 接口。

启动方式：
---------
uvicorn services.api.main:app --port 8000 --host 0.0.0.0
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..orchestrator.core import Orchestrator, PredictionRequest, FusionResult
from ..orchestrator.scoring import rank_candidates


# ═══════════════════════════════════════════════════════════════════════════
# 请求 / 响应模型
# ═══════════════════════════════════════════════════════════════════════════

class SinglePredictRequest(BaseModel):
    """单序列预测请求"""
    sequence: str = Field(..., min_length=1, max_length=5000, description="氨基酸序列")
    peptide_id: str | None = Field(None, description="肽 ID")
    tools: list[str] | None = Field(None, description="指定工具列表，None=所有 P0 工具")


class BatchPredictRequest(BaseModel):
    """批量预测请求"""
    sequences: list[SinglePredictRequest] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="序列列表（最多 1000 条）"
    )
    tools: list[str] | None = Field(None, description="指定工具列表")
    top_k: int = Field(50, ge=1, le=1000, description="返回 top k 结果")


class ToolResultResponse(BaseModel):
    """单个工具结果"""
    tool_name: str
    score: float | None
    label: str | None
    latency_ms: float
    error: str | None


class FusionResultResponse(BaseModel):
    """融合结果"""
    peptide_id: str
    sequence: str
    fused_score: float | None
    fused_label: str | None
    total_latency_ms: float
    scoring_details: dict[str, Any] | None
    tool_results: list[ToolResultResponse]


class BatchPredictResponse(BaseModel):
    """批量预测响应"""
    success: bool
    total: int
    returned: int
    results: list[FusionResultResponse]


class HealthResponse(BaseModel):
    """健康检查"""
    status: str
    service: str


class ToolInfo(BaseModel):
    """工具信息"""
    name: str
    url: str
    type: str
    priority: int
    requires_gpu: bool


class ToolListResponse(BaseModel):
    """工具列表响应"""
    tools: list[ToolInfo]


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="iGEM-silk Orchestrator",
    description="丝素蛋白融合功能肽设计平台的调度核心 API",
    version="1.0.0"
)

# CORS 中间件（允许前端跨域访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局 Orchestrator 实例
_orchestrator: Orchestrator | None = None


@app.on_event("startup")
async def startup():
    """启动时初始化 Orchestrator"""
    global _orchestrator
    _orchestrator = Orchestrator()
    print("[Orchestrator API] Started on http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    """关闭时清理资源"""
    global _orchestrator
    if _orchestrator:
        await _orchestrator.close()
        print("[Orchestrator API] Shutdown")


def _to_response(result: FusionResult) -> FusionResultResponse:
    """将 FusionResult 转换为 API 响应模型"""
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


# ═══════════════════════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["root"])
async def root():
    """API 根路径"""
    return {
        "service": "iGEM-silk Orchestrator",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "tools": "/tools"
    }


@app.get("/health", response_model=HealthResponse, tags=["status"])
async def health():
    """健康检查"""
    return HealthResponse(status="healthy", service="orchestrator")


@app.get("/tools", response_model=ToolListResponse, tags=["info"])
async def list_tools():
    """列出所有可用工具"""
    from ..orchestrator.registry import TOOL_REGISTRY
    return ToolListResponse(
        tools=[
            ToolInfo(
                name=name,
                url=cfg.url,
                type=cfg.type,
                priority=cfg.priority,
                requires_gpu=cfg.requires_gpu
            )
            for name, cfg in TOOL_REGISTRY.items()
        ]
    )


@app.post("/predict", response_model=FusionResultResponse, tags=["prediction"])
async def predict(request: SinglePredictRequest):
    """
    单序列预测。

    对输入的氨基酸序列调用所有 P0 工具（或指定工具），
    返回融合后的综合评分。
    """
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = await _orchestrator.predict_single(
        PredictionRequest(
            sequence=request.sequence,
            peptide_id=request.peptide_id,
            tools=request.tools
        )
    )
    return _to_response(result)


@app.post("/predict/batch", response_model=BatchPredictResponse, tags=["prediction"])
async def predict_batch(request: BatchPredictRequest):
    """
    批量预测。

    一次处理多条序列（最多 1000 条），返回按融合分数排序的 top k 结果。
    """
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # 构建批量请求
    requests = [
        PredictionRequest(
            sequence=req.sequence,
            peptide_id=req.peptide_id
        )
        for req in request.sequences
    ]

    # 执行批量预测
    results = await _orchestrator.predict_batch(requests, tools=request.tools)

    # 排序并取 top_k
    ranked = rank_candidates(results, top_k=request.top_k)

    return BatchPredictResponse(
        success=True,
        total=len(results),
        returned=len(ranked),
        results=[_to_response(r) for r in ranked]
    )


# ═══════════════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)