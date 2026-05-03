# Template Module
# =================
# Bio Tool Service 模板

from .tool_service import (
    BioToolService,
    create_app,
    PredictRequest,
    BatchPredictRequest,
    ToolResult,
    PredictResponse,
    BatchPredictResponse,
    HealthResponse,
    InfoResponse,
)

__all__ = [
    "BioToolService",
    "create_app",
    "PredictRequest",
    "BatchPredictRequest",
    "ToolResult",
    "PredictResponse",
    "BatchPredictResponse",
    "HealthResponse",
    "InfoResponse",
]