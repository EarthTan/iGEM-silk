# Bio Tool Service Template
# ==========================
# 每个工具服务都继承此模板，只需实现 load_model() 和 predict_impl() 方法。
# 启动方式: uvicorn services.template.tool_service:app --port XXXX --host 0.0.0.0

"""
services/template/tool_service.py
==================================
Bio Tool Service 的 FastAPI 模板。

每个工具服务只需：
1. 继承 BioToolService
2. 实现 load_model() — 启动时加载模型（只调用一次）
3. 实现 predict_impl() — 核心预测逻辑

使用示例：
-----------
# 方式一：直接启动模板（需通过环境变量配置工具）
uvicorn services.template.tool_service:app --port 8001 --host 0.0.0.0

# 方式二：创建具体工具服务（推荐）
from services.template.tool_service import BioToolService, create_app, PredictRequest, ToolResult

class AnOxPePredService(BioToolService):
    tool_name = "anoxpepred"
    version = "1.1.0"
    description = "抗氧化肽预测工具"

    async def load_model(self):
        # 加载 TensorFlow 模型
        import tensorflow as tf
        self.model = tf.keras.models.load_model("path/to/model.h5")

    async def predict_impl(self, sequence: str) -> ToolResult:
        # 实现预测逻辑
        score = self.model.predict(...)  # 0-1
        return ToolResult(score=score, label="antioxidant" if score > 0.5 else "non-antioxidant")

app = create_app(AnOxPePredService)
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, ClassVar

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════
# 请求 / 响应模型
# ═══════════════════════════════════════════════════════════════════════════

class PredictRequest(BaseModel):
    """单序列预测请求"""
    sequence: str = Field(..., min_length=1, max_length=5000, description="氨基酸序列")
    peptide_id: str | None = Field(None, description="肽 ID（可选）")


class BatchPredictRequest(BaseModel):
    """批量预测请求"""
    sequences: list[PredictRequest] = Field(..., min_length=1, max_length=1000)


class ToolResult(BaseModel):
    """工具预测结果（统一格式）"""
    peptide_id: str = "unknown"
    sequence: str = ""
    score: float = Field(..., ge=0.0, le=1.0, description="预测分数 0-1")
    label: str = Field(..., description="预测标签（如 antioxidant, toxic, non-toxic）")
    details: dict[str, Any] = Field(default_factory=dict, description="附加详细信息")


class PredictResponse(BaseModel):
    """单序列预测响应"""
    success: bool
    peptide_id: str | None = None
    sequence: str | None = None
    result: ToolResult | None = None
    error: str | None = None


class BatchPredictResponse(BaseModel):
    """批量预测响应"""
    success: bool
    results: list[ToolResult]
    total: int
    error: str | None = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    tool_name: str
    version: str
    model_loaded: bool


class InfoResponse(BaseModel):
    """工具信息响应"""
    tool_name: str
    version: str
    description: str
    capabilities: list[str]
    input_format: dict[str, str]
    output_format: dict[str, str]
    recommended_batch_size: int


# ═══════════════════════════════════════════════════════════════════════════
# Bio Tool Service 基类
# ═══════════════════════════════════════════════════════════════════════════

class BioToolService:
    """
    所有工具服务的基类。

    子类必须实现：
    - tool_name: str       工具唯一名称
    - version: str        版本号
    - description: str    工具描述
    - load_model()        加载模型（异步，启动时调用一次）
    - predict_impl()      核心预测逻辑（异步，每次请求调用）

    可选覆盖：
    - recommended_batch_size: int  推荐的批量大小（默认 50）
    """

    # ── 类属性（子类必须覆盖）────────────────────────────
    tool_name: ClassVar[str] = "template"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = "Template bio tool service"
    recommended_batch_size: ClassVar[int] = 50

    # ── 实例属性 ──────────────────────────────────────────
    model: Any = None  # 加载的模型对象

    def __init__(self):
        self._lock = asyncio.Lock()  # 并发控制锁
        self._loaded = False          # 模型是否已加载

    async def load_model(self) -> None:
        """
        加载模型权重。启动时调用一次，子类必须实现。
        如果模型较重，可以用 asyncio.to_thread() 在后台加载。
        """
        raise NotImplementedError(f"{self.tool_name}: load_model() must be implemented")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        核心预测逻辑。处理单条序列，返回标准化结果。
        子类必须实现。
        """
        raise NotImplementedError(f"{self.tool_name}: predict_impl() must be implemented")

    # ── 公开 API（一般不需要覆盖）──────────────────────────

    async def predict_single(self, request: PredictRequest) -> PredictResponse:
        """单序列预测入口（带并发控制）"""
        # 确保模型已加载
        if not self._loaded:
            async with self._lock:
                if not self._loaded:  # 双重检查
                    await self.load_model()
                    self._loaded = True

        try:
            result = await self.predict_impl(request.sequence)
            result.peptide_id = request.peptide_id or "unknown"
            result.sequence = request.sequence
            return PredictResponse(
                success=True,
                peptide_id=result.peptide_id,
                sequence=request.sequence,
                result=result,
                error=None
            )
        except Exception as e:
            return PredictResponse(
                success=False,
                peptide_id=request.peptide_id,
                sequence=request.sequence,
                result=None,
                error=str(e)
            )

    async def predict_batch(self, request: BatchPredictRequest) -> BatchPredictResponse:
        """批量预测入口（带并发限制）"""
        # 确保模型已加载
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        semaphore = asyncio.Semaphore(10)  # 单服务最大并发 10

        async def bounded_predict(item: PredictRequest) -> ToolResult | None:
            async with semaphore:
                try:
                    result = await self.predict_impl(item.sequence)
                    result.peptide_id = item.peptide_id or "unknown"
                    result.sequence = item.sequence
                    return result
                except Exception:
                    return None

        # 并发执行
        tasks = [bounded_predict(item) for item in request.sequences]
        results = await asyncio.gather(*tasks)

        valid_results = [r for r in results if r is not None]
        return BatchPredictResponse(
            success=True,
            results=valid_results,
            total=len(valid_results),
            error=None if len(valid_results) == len(request.sequences) else f"{len(valid_results)}/{len(request.sequences)} succeeded"
        )


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI 应用工厂
# ═══════════════════════════════════════════════════════════════════════════

def create_app(ToolClass: type[BioToolService]) -> FastAPI:
    """
    工厂函数：基于工具类创建完整的 FastAPI 应用。

    使用方式：
    ---------
    from services.template.tool_service import create_app, BioToolService, ToolResult

    class MyToolService(BioToolService):
        tool_name = "mytool"
        version = "1.0.0"
        description = "My custom tool"

        async def load_model(self):
            # 加载模型
            self.model = load_my_model()

        async def predict_impl(self, sequence: str) -> ToolResult:
            score = self.model.predict(sequence)
            return ToolResult(score=score, label="active" if score > 0.5 else "inactive")

    app = create_app(MyToolService)

    # 启动：
    # uvicorn services.mytool.service:app --port 8001 --host 0.0.0.0
    """
    tool_instance = ToolClass()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动时：加载模型
        try:
            await tool_instance.load_model()
            tool_instance._loaded = True
            print(f"[{ToolClass.tool_name}] Model loaded successfully")
        except Exception as e:
            print(f"[{ToolClass.tool_name}] Failed to load model: {e}")
            # 不在这里退出，允许服务启动但标记为未就绪
        yield
        # 关闭时：清理资源（如 GPU 内存）
        if hasattr(tool_instance.model, 'clear_session'):
            tool_instance.model.clear_session()
        print(f"[{ToolClass.tool_name}] Shutdown")

    app = FastAPI(
        title=ToolClass.tool_name,
        description=ToolClass.description,
        version=ToolClass.version,
        lifespan=lifespan
    )

    # ── 路由 ─────────────────────────────────────────────

    @app.get("/")
    async def root():
        return {
            "service": ToolClass.tool_name,
            "version": ToolClass.version,
            "docs": "/docs"
        }

    @app.post("/predict", response_model=PredictResponse)
    async def predict(request: PredictRequest):
        """单序列预测"""
        return await tool_instance.predict_single(request)

    @app.post("/predict/batch", response_model=BatchPredictResponse)
    async def predict_batch(request: BatchPredictRequest):
        """批量预测（推荐使用，减少网络开销）"""
        return await tool_instance.predict_batch(request)

    @app.get("/health", response_model=HealthResponse)
    async def health():
        """健康检查"""
        return HealthResponse(
            status="healthy" if tool_instance._loaded else "loading",
            tool_name=ToolClass.tool_name,
            version=ToolClass.version,
            model_loaded=tool_instance._loaded
        )

    @app.get("/info", response_model=InfoResponse)
    async def info():
        """工具信息"""
        return InfoResponse(
            tool_name=ToolClass.tool_name,
            version=ToolClass.version,
            description=ToolClass.description,
            capabilities=["predict", "predict/batch"],
            input_format={"sequence": "string (amino acid sequence)"},
            output_format={"score": "float 0-1", "label": "string"},
            recommended_batch_size=ToolClass.recommended_batch_size
        )

    return app


# ═══════════════════════════════════════════════════════════════════════════
# 启动入口（用于直接运行模板）
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    # 读取环境变量配置
    PORT = int(os.environ.get("TOOL_PORT", "8001"))
    HOST = os.environ.get("TOOL_HOST", "0.0.0.0")
    TOOL_CLASS = os.environ.get("TOOL_CLASS", "")

    if not TOOL_CLASS:
        print("ERROR: TOOL_CLASS environment variable must be set")
        print("Example: TOOL_CLASS=services.tools.anoxpepred.service:AnOxPePredService")
        sys.exit(1)

    # 动态导入指定的工具类
    module_path, class_name = TOOL_CLASS.rsplit(":", 1)
    module = __import__(module_path, fromlist=[class_name])
    ToolClass = getattr(module, class_name)

    app = create_app(ToolClass)
    uvicorn.run(app, host=HOST, port=PORT)