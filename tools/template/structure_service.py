# 3D 结构生成服务 模板
# ==========================
#
# 【这个文件是什么？】
# ------------------
# 这是"3D 结构生成"类微服务的模板文件。
# 输入一条 FASTA 序列，输出三维结构模型（PDB 格式）。
#
# 和 fasta_service 的区别：
#   - fasta_service：序列 → 评分（数字）
#   - structure_service：序列 → 结构（PDB 文本）
#
# 【如何创建自己的 3D 结构服务？】
# ------------------------------
#   1. 继承 StructureService 类
#   2. 实现 load_model() 方法（加载你的结构预测模型）
#   3. 实现 predict_structure() 方法（序列 → PDB 结构）
#   4. app = create_app(YourService)
#   5. uvicorn.run(app, port=80XX)
#
# 【3D 结构预测的特殊性】
# -----------------------
# 结构预测通常是所有微服务中"最慢"的一类（如 AlphaFold 可能需数分钟）。
# 因此：
#   - 默认 recommended_batch_size 较小（5）
#   - batch 并发的 semaphore 也更保守（3）
#   - 建议启用 GPU 加速

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, ClassVar

from fastapi import FastAPI
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# 第一部分：请求和响应模型
# ═══════════════════════════════════════════════════════════════════════════════


# ─────────────────────────────────────────────────────────────────────────────
# PredictRequest：单序列预测请求
# ─────────────────────────────────────────────────────────────────────────────
class PredictRequest(BaseModel):
    """
    单序列结构预测请求。

    【字段说明】
    - sequence: 氨基酸序列，长度 1-5000
    - peptide_id: 序列编号（可选）

    【例子】
    {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}
    """

    sequence: str = Field(..., min_length=1, max_length=5000, description="氨基酸序列")
    peptide_id: str | None = Field(None, description="肽 ID（可选）")


# ─────────────────────────────────────────────────────────────────────────────
# BatchPredictRequest：批量结构预测请求
# ─────────────────────────────────────────────────────────────────────────────
class BatchPredictRequest(BaseModel):
    """
    批量结构预测请求。

    【字段说明】
    - sequences: 序列列表，每个元素是一条 PredictRequest

    【例子】
    {"sequences": [{"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}, ...]}
    """

    sequences: list[PredictRequest] = Field(..., min_length=1, max_length=1000)


# ─────────────────────────────────────────────────────────────────────────────
# StructureResult：单条结构预测结果
# ─────────────────────────────────────────────────────────────────────────────
class StructureResult(BaseModel):
    """
    单条序列的结构预测结果。

    【字段说明】
    - peptide_id: 序列编号
    - sequence: 原始氨基酸序列
    - pdb_content: PDB 格式的三维结构（纯文本）
    - confidence: 整体结构置信度 0-1（如 pLDDT 均值），可选
    - details: 附加信息（如 per-residue pLDDT、PAE 矩阵路径等）

    【例子】
    {
        "peptide_id": "pep_001",
        "sequence": "YVPLPNVPQG",
        "pdb_content": "ATOM      1  N   ...\\nATOM      2  CA  ...\\n...",
        "confidence": 0.87,
        "details": {"mean_plddt": 0.87, "num_residues": 10}
    }
    """

    peptide_id: str = "unknown"
    sequence: str = ""
    pdb_content: str = Field(..., description="PDB 格式三维结构文本")
    confidence: float | None = Field(None, ge=0.0, le=1.0, description="结构置信度 0-1")
    details: dict[str, Any] = Field(default_factory=dict, description="附加结构信息")


# ─────────────────────────────────────────────────────────────────────────────
# StructurePredictResponse：单序列结构预测响应
# ─────────────────────────────────────────────────────────────────────────────
class StructurePredictResponse(BaseModel):
    """
    单序列结构预测响应。

    【字段说明】
    - success: 是否成功
    - peptide_id: 序列编号
    - sequence: 原始序列
    - result: 结构预测结果（成功时）
    - error: 错误信息（失败时）

    【例子】
    {"success": true, "peptide_id": "pep_001", "sequence": "YVPLPNVPQG", "result": {...}, "error": null}
    """

    success: bool
    peptide_id: str | None = None
    sequence: str | None = None
    result: StructureResult | None = None
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# StructureBatchPredictResponse：批量结构预测响应
# ─────────────────────────────────────────────────────────────────────────────
class StructureBatchPredictResponse(BaseModel):
    """
    批量结构预测响应。

    【字段说明】
    - success: 是否全部成功
    - results: 所有结构预测结果列表
    - total: 成功预测的数量
    - error: 错误信息（如果有失败）
    """

    success: bool
    results: list[StructureResult]
    total: int
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# HealthResponse：健康检查响应
# ─────────────────────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    """
    健康检查响应。

    【字段说明】
    - status: "healthy" | "loading"
    - tool_name: 工具名
    - version: 版本号
    - model_loaded: 模型是否已加载
    """

    status: str
    tool_name: str
    version: str
    model_loaded: bool


# ─────────────────────────────────────────────────────────────────────────────
# InfoResponse：工具信息响应
# ─────────────────────────────────────────────────────────────────────────────
class InfoResponse(BaseModel):
    """
    工具信息响应。

    【字段说明】
    - tool_name: 工具名
    - version: 版本号
    - description: 描述
    - capabilities: 支持的功能列表
    - input_format: 输入格式说明
    - output_format: 输出格式说明
    - recommended_batch_size: 推荐批量大小
    """

    tool_name: str
    version: str
    description: str
    capabilities: list[str]
    input_format: dict[str, str]
    output_format: dict[str, str]
    recommended_batch_size: int


# ═══════════════════════════════════════════════════════════════════════════════
# 第二部分：StructureService 基类
# ═══════════════════════════════════════════════════════════════════════════════
#
# 【什么是"基类"？】
# 和 fasta_service 的 FastaToolService 一样，这是 3D 结构服务的蓝图。
# 你只需要继承它，实现 load_model() 和 predict_structure() 即可。


class StructureService:
    """
    3D 结构生成服务的基类。

    【使用步骤】
    ----------
    1. 继承 StructureService
    2. 设置类属性：tool_name, version, description
    3. 实现 load_model()：加载结构预测模型
    4. 实现 predict_structure()：序列 → StructureResult

    【例子】
    -------
    class MyFoldService(StructureService):
        tool_name = "myfold"
        version = "1.0.0"
        description = "基于深度学习的肽结构预测"

        async def load_model(self):
            self.model = load_folding_model()

        async def predict_structure(self, sequence: str) -> StructureResult:
            pdb_text = self.model.fold(sequence)
            return StructureResult(
                sequence=sequence,
                pdb_content=pdb_text,
                confidence=0.85,
            )
    """

    # ── 类属性（子类必须覆盖）────────────────────────────
    tool_name: ClassVar[str] = "structure_template"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = "Template 3D structure prediction service"
    recommended_batch_size: ClassVar[int] = 5  # 结构预测慢，默认 5

    # ── 实例属性 ──────────────────────────────────────────
    model: Any = None

    def __init__(self):
        self._lock = asyncio.Lock()
        self._loaded = False

    async def load_model(self) -> None:
        """
        加载结构预测模型。

        【子类必须实现】
        - 加载模型权重到 self.model
        - 可以加载多个模型（如 encoder + decoder）
        """
        raise NotImplementedError(f"{self.tool_name}: load_model() must be implemented")

    async def predict_structure(self, sequence: str) -> StructureResult:
        """
        对一条氨基酸序列进行结构预测。

        【参数】
        - sequence: 氨基酸序列（如 "YVPLPNVPQG"）

        【返回值】
        - StructureResult: 包含 pdb_content 和 confidence

        【子类必须实现】
        """
        raise NotImplementedError(
            f"{self.tool_name}: predict_structure() must be implemented"
        )

    # ── 公开 API（一般不需要覆盖）──────────────────────────

    async def predict_single(self, request: PredictRequest) -> StructurePredictResponse:
        """
        处理单序列结构预测请求。
        1. 确保模型已加载（双重检查锁定）
        2. 调用 predict_structure()
        3. 包装成 StructurePredictResponse
        """
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        try:
            result = await self.predict_structure(request.sequence)
            result.peptide_id = request.peptide_id or "unknown"
            result.sequence = request.sequence
            return StructurePredictResponse(
                success=True,
                peptide_id=result.peptide_id,
                sequence=request.sequence,
                result=result,
                error=None,
            )
        except Exception as e:
            return StructurePredictResponse(
                success=False,
                peptide_id=request.peptide_id,
                sequence=request.sequence,
                result=None,
                error=str(e),
            )

    async def predict_batch(
        self, request: BatchPredictRequest
    ) -> StructureBatchPredictResponse:
        """
        处理批量结构预测请求。

        【注意】
        结构预测计算量极大，默认并发限制为 3。
        """
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        # 结构预测更慢，限制并发为 3
        semaphore = asyncio.Semaphore(3)

        async def bounded_predict(item: PredictRequest) -> StructureResult | None:
            async with semaphore:
                try:
                    result = await self.predict_structure(item.sequence)
                    result.peptide_id = item.peptide_id or "unknown"
                    result.sequence = item.sequence
                    return result
                except Exception:
                    return None

        tasks = [bounded_predict(item) for item in request.sequences]
        results = await asyncio.gather(*tasks)

        valid_results = [r for r in results if r is not None]

        return StructureBatchPredictResponse(
            success=True,
            results=valid_results,
            total=len(valid_results),
            error=None
            if len(valid_results) == len(request.sequences)
            else f"{len(valid_results)}/{len(request.sequences)} succeeded",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 第三部分：FastAPI 应用工厂
# ═══════════════════════════════════════════════════════════════════════════════


def create_app(ToolClass: type[StructureService]) -> FastAPI:
    """
    工厂函数：基于工具类创建完整的 FastAPI 应用。

    【参数】
    - ToolClass: 一个继承自 StructureService 的类

    【返回值】
    - 一个配置好的 FastAPI 应用

    【使用例子】
    -----------
    class MyFoldService(StructureService):
        ...

    app = create_app(MyFoldService)
    uvicorn.run(app, host="0.0.0.0", port=8101)
    """
    tool_instance = ToolClass()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """服务生命周期：启动时加载模型，关闭时清理资源"""
        try:
            await tool_instance.load_model()
            tool_instance._loaded = True
            print(f"[{ToolClass.tool_name}] Model loaded successfully")
        except Exception as e:
            print(f"[{ToolClass.tool_name}] Failed to load model: {e}")
        yield
        # 清理 GPU 资源
        if hasattr(tool_instance.model, "clear_session"):
            tool_instance.model.clear_session()
        print(f"[{ToolClass.tool_name}] Shutdown")

    app = FastAPI(
        title=ToolClass.tool_name,
        description=ToolClass.description,
        version=ToolClass.version,
        lifespan=lifespan,
    )

    # ── 路由定义 ──────────────────────────────────────────

    @app.get("/")
    async def root():
        """根路径：返回服务基本信息"""
        return {
            "service": ToolClass.tool_name,
            "version": ToolClass.version,
            "docs": "/docs",
        }

    @app.post("/predict", response_model=StructurePredictResponse)
    async def predict(request: PredictRequest):
        """
        单序列结构预测：POST /predict

        【请求格式】
        {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}

        【响应格式】
        {"success": true, "result": {"pdb_content": "...", "confidence": 0.87}, ...}
        """
        return await tool_instance.predict_single(request)

    @app.post("/predict/batch", response_model=StructureBatchPredictResponse)
    async def predict_batch(request: BatchPredictRequest):
        """
        批量结构预测：POST /predict/batch

        【请求格式】
        {"sequences": [{"sequence": "...", "peptide_id": "..."}, ...]}

        【响应格式】
        {"success": true, "results": [...], "total": N, "error": null}
        """
        return await tool_instance.predict_batch(request)

    @app.get("/health", response_model=HealthResponse)
    async def health():
        """健康检查：GET /health"""
        return HealthResponse(
            status="healthy" if tool_instance._loaded else "loading",
            tool_name=ToolClass.tool_name,
            version=ToolClass.version,
            model_loaded=tool_instance._loaded,
        )

    @app.get("/info", response_model=InfoResponse)
    async def info():
        """工具信息：GET /info"""
        return InfoResponse(
            tool_name=ToolClass.tool_name,
            version=ToolClass.version,
            description=ToolClass.description,
            capabilities=["predict", "predict/batch"],
            input_format={"sequence": "string (amino acid sequence)"},
            output_format={"pdb_content": "string (PDB format)", "confidence": "float 0-1"},
            recommended_batch_size=ToolClass.recommended_batch_size,
        )

    return app


# ═══════════════════════════════════════════════════════════════════════════════
# 第四部分：启动入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("TOOL_PORT", "8101"))
    HOST = os.environ.get("TOOL_HOST", "0.0.0.0")
    TOOL_CLASS = os.environ.get("TOOL_CLASS", "")

    if not TOOL_CLASS:
        print("ERROR: TOOL_CLASS environment variable must be set")
        print("Example: TOOL_CLASS=tools.myfold.service:MyFoldService")
        sys.exit(1)

    module_path, class_name = TOOL_CLASS.rsplit(":", 1)
    module = __import__(module_path, fromlist=[class_name])
    ToolClass = getattr(module, class_name)

    app = create_app(ToolClass)
    uvicorn.run(app, host=HOST, port=PORT)
