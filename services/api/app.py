"""
应用核心配置模块

- FastAPI 应用实例
- CORS 中间件配置
- 全局 Orchestrator 实例
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..orchestrator.core import Orchestrator

# 创建 FastAPI 应用实例
app = FastAPI(
    title="iGEM-silk Orchestrator",
    description="丝素蛋白融合功能肽设计平台的调度核心 API",
    version="1.0.0"
)

# CORS 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局 Orchestrator 实例
# 存储在 app 对象的属性中，避免 import 后的 global 问题
class _State:
    orchestrator: Orchestrator | None = None

state = _State()
