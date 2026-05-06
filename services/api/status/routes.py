"""状态检查功能的 API 路由"""

from ..app import app
from .models import HealthResponse


@app.get("/health", response_model=HealthResponse, tags=["status"])
async def health():
    """健康检查接口。"""
    return HealthResponse(status="healthy", service="orchestrator")
