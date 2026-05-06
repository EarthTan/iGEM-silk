"""预测功能的 API 路由"""

from fastapi import HTTPException
from ...orchestrator.core import PredictionRequest
from ...orchestrator.scoring import rank_candidates
from ..app import app, state
from .models import (
    SinglePredictRequest,
    BatchPredictRequest,
    FusionResultResponse,
    BatchPredictResponse
)
from .converters import to_response


@app.post("/predict", response_model=FusionResultResponse, tags=["prediction"])
async def predict(request: SinglePredictRequest):
    """单序列预测。"""
    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = await state.orchestrator.predict_single(
        PredictionRequest(
            sequence=request.sequence,
            peptide_id=request.peptide_id,
            tools=request.tools
        )
    )

    return to_response(result)


@app.post("/predict/batch", response_model=BatchPredictResponse, tags=["prediction"])
async def predict_batch(request: BatchPredictRequest):
    """批量预测多条序列。"""
    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    requests = [
        PredictionRequest(
            sequence=req.sequence,
            peptide_id=req.peptide_id
        )
        for req in request.sequences
    ]

    results = await state.orchestrator.predict_batch(requests, tools=request.tools)
    ranked = rank_candidates(results, top_k=request.top_k)

    return BatchPredictResponse(
        success=True,
        total=len(results),
        returned=len(ranked),
        results=[to_response(r) for r in ranked]
    )
