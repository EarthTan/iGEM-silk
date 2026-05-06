"""
应用核心配置模块

- FastAPI 应用实例
- CORS 中间件配置
- 全局 Orchestrator 实例
- 生命周期管理
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..orchestrator.core import Orchestrator


# 全局 Orchestrator 实例
class _State:
    orchestrator: Orchestrator | None = None

state = _State()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理。
    
    - startup（yield 前）：初始化 Orchestrator
    - shutdown（yield 后）：释放资源
    """
    # ─── startup ───
    state.orchestrator = Orchestrator()
    print("[Orchestrator API] Started on http://localhost:8000")
    
    yield  # 应用运行阶段
    
    # ─── shutdown ───
    if state.orchestrator:
        await state.orchestrator.close()
        print("[Orchestrator API] Shutdown")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="iGEM-silk Orchestrator",
    description="丝素蛋白融合功能肽设计平台的调度核心 API",
    version="1.0.0",
    lifespan=lifespan  # 绑定生命周期管理
)

# CORS 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
