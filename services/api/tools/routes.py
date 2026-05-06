"""工具查询功能的 API 路由"""

from ..app import app
from .models import ToolInfo, ToolListResponse


@app.get("/tools", response_model=ToolListResponse, tags=["info"])
async def list_tools():
    """列出所有可用工具。"""
    from ...orchestrator.registry import TOOL_REGISTRY
    
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
