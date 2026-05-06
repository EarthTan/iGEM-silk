"""
应用生命周期管理

- startup 事件：初始化 Orchestrator
- shutdown 事件：清理 Orchestrator 资源
"""

from .app import app, state
from ..orchestrator.core import Orchestrator


@app.on_event("startup")
async def startup():
    """应用启动时执行，初始化 Orchestrator 实例。"""
    state.orchestrator = Orchestrator()
    print("[Orchestrator API] Started on http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    """应用关闭时执行，释放 Orchestrator 占用的资源。"""
    if state.orchestrator:
        await state.orchestrator.close()
        print("[Orchestrator API] Shutdown")
