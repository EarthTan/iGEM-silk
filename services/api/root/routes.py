"""根路由"""

from ..app import app


@app.get("/", tags=["root"])
async def root():
    """API 根路径，显示欢迎信息和相关链接。"""
    return {
        "service": "iGEM-silk Orchestrator",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "tools": "/tools"
    }
