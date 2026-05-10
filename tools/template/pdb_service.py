# PDB 评分服务 模板
# ==========================
#
# 【这个文件是什么？】
# ------------------
# 这是"PDB 评分"类微服务的模板文件。
# 输入一个 PDB 结构文件（+ 可选的序列和链信息），输出针对该结构的评分结果。
#
# 和 fasta_service / structure_service 的区别：
#   - fasta_service：序列 → 评分
#   - structure_service：序列 → 结构
#   - pdb_service：结构 → 评分（输入是 PDB 文件，不是纯序列）
#
# 【典型应用场景】
# ----------------
# - 对 AlphaFold 生成的结构做质量评估（如 pLDDT、pTM 之外的其他指标）
# - 预测蛋白质稳定性（折叠自由能变化 ΔΔG）
# - 评估蛋白-蛋白/蛋白-肽的对接分数
# - 结构层面的毒性/功能预测
#
# 【如何创建自己的 PDB 评分服务？】
# ------------------------------
#   1. 继承 PdbScoringService 类
#   2. 实现 load_model() 方法（加载评分模型）
#   3. 实现 score_pdb() 方法（PDB 结构 → 评分结果）
#   4. app = create_app(YourService)
#   5. uvicorn.run(app, port=80XX)
#
# 【关于 PDB 数据的传输方式】
# --------------------------
# pdb_content 以 JSON 字符串传输（嵌入在请求 body 中），
# 而非 multipart 文件上传。这样做的原因：
#   - 保持与现有 POST /predict 接口风格一致（都是 JSON）
#   - 肽的 PDB 通常只有几十 KB，JSON 传输足够
#   - 如果以后需要处理超大 PDB（如完整蛋白复合体），可额外加 /predict/upload

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
# PdbScoreRequest：单次 PDB 评分请求
# ─────────────────────────────────────────────────────────────────────────────
class PdbScoreRequest(BaseModel):
    """
    单次 PDB 评分请求。

    【字段说明】
    - pdb_content: PDB 文件内容（纯文本）
    - sequence: 关联的氨基酸序列（可选，某些评分工具可能需要）
    - chain_id: 目标链 ID（可选，如 "A", "B"）
    - peptide_id: 序列编号（可选）

    【例子】
    {
        "pdb_content": "ATOM      1  N   ...\\nATOM      2  CA  ...\\n...",
        "sequence": "YVPLPNVPQG",
        "chain_id": "A",
        "peptide_id": "pep_001"
    }
    """

    pdb_content: str = Field(..., min_length=1, description="PDB 文件内容")
    sequence: str | None = Field(None, description="关联的氨基酸序列（可选）")
    chain_id: str | None = Field(None, description="目标链 ID（可选）")
    peptide_id: str | None = Field(None, description="肽 ID（可选）")


# ─────────────────────────────────────────────────────────────────────────────
# PdbBatchScoreRequest：批量 PDB 评分请求
# ─────────────────────────────────────────────────────────────────────────────
class PdbBatchScoreRequest(BaseModel):
    """
    批量 PDB 评分请求。

    【字段说明】
    - requests: PDB 评分请求列表，每个元素是一条 PdbScoreRequest

    【例子】
    {
        "requests": [
            {"pdb_content": "...", "peptide_id": "pep_001"},
            {"pdb_content": "...", "peptide_id": "pep_002"}
        ]
    }
    """

    requests: list[PdbScoreRequest] = Field(..., min_length=1, max_length=100)


# ─────────────────────────────────────────────────────────────────────────────
# PdbScoreResult：单条 PDB 评分结果
# ─────────────────────────────────────────────────────────────────────────────
class PdbScoreResult(BaseModel):
    """
    单条 PDB 评分结果。

    【字段说明】
    - peptide_id: 序列编号
    - score: 综合评分 0-1（0 = 最差, 1 = 最优）
    - label: 预测标签（如 "stable", "unstable", "binding", "non-binding"）
    - details: 各项评分细节（如 ΔΔG、RMSD、各能量项等）

    【例子】
    {
        "peptide_id": "pep_001",
        "score": 0.82,
        "label": "stable",
        "details": {"ddG": -2.5, "confidence": 0.91, "energy_terms": {...}}
    }
    """

    peptide_id: str = "unknown"
    score: float = Field(..., ge=0.0, le=1.0, description="综合评分 0-1")
    label: str = Field(default="", description="预测标签")
    details: dict[str, Any] = Field(default_factory=dict, description="各项评分细节")


# ─────────────────────────────────────────────────────────────────────────────
# PdbScoreResponse：单次 PDB 评分响应
# ─────────────────────────────────────────────────────────────────────────────
class PdbScoreResponse(BaseModel):
    """
    单次 PDB 评分响应。

    【字段说明】
    - success: 是否成功
    - peptide_id: 序列编号
    - result: 评分结果（成功时）
    - error: 错误信息（失败时）
    """

    success: bool
    peptide_id: str | None = None
    result: PdbScoreResult | None = None
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# PdbBatchScoreResponse：批量 PDB 评分响应
# ─────────────────────────────────────────────────────────────────────────────
class PdbBatchScoreResponse(BaseModel):
    """
    批量 PDB 评分响应。

    【字段说明】
    - success: 是否全部成功
    - results: 所有评分结果列表
    - total: 成功评分的数量
    - error: 错误信息（如果有失败）
    """

    success: bool
    results: list[PdbScoreResult]
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
# 第二部分：PdbScoringService 基类
# ═══════════════════════════════════════════════════════════════════════════════
#
# 【什么是"基类"？】
# 这是 PDB 评分服务的蓝图。你只需要继承它，
# 实现 load_model() 和 score_pdb() 即可。


class PdbScoringService:
    """
    PDB 评分服务的基类。

    【使用步骤】
    ----------
    1. 继承 PdbScoringService
    2. 设置类属性：tool_name, version, description
    3. 实现 load_model()：加载评分模型
    4. 实现 score_pdb()：PDB 结构 → PdbScoreResult

    【例子】
    -------
    class MyStabilityService(PdbScoringService):
        tool_name = "mystability"
        version = "1.0.0"
        description = "蛋白质稳定性评估工具"

        async def load_model(self):
            self.model = load_stability_model()

        async def score_pdb(self, pdb_content, sequence=None, chain_id=None):
            delta_g = self.model.compute_ddG(pdb_content, chain_id)
            score = 1.0 / (1.0 + max(0, delta_g))  # ΔΔG → 0-1
            return PdbScoreResult(
                score=score,
                label="stable" if delta_g < 0 else "destabilizing",
                details={"ddG_kcal_mol": delta_g},
            )
    """

    # ── 类属性（子类必须覆盖）────────────────────────────
    tool_name: ClassVar[str] = "pdb_template"
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = "Template PDB scoring service"
    recommended_batch_size: ClassVar[int] = 20

    # ── 实例属性 ──────────────────────────────────────────
    model: Any = None

    def __init__(self):
        self._lock = asyncio.Lock()
        self._loaded = False

    async def load_model(self) -> None:
        """
        加载评分模型。

        【子类必须实现】
        - 加载模型权重到 self.model
        """
        raise NotImplementedError(f"{self.tool_name}: load_model() must be implemented")

    async def score_pdb(
        self,
        pdb_content: str,
        sequence: str | None = None,
        chain_id: str | None = None,
    ) -> PdbScoreResult:
        """
        对一个 PDB 结构进行评分。

        【参数】
        - pdb_content: PDB 文件内容（ATOM 记录等）
        - sequence: 关联的氨基酸序列（可选，某些工具需要）
        - chain_id: 目标链 ID（可选，如 "A"）

        【返回值】
        - PdbScoreResult: 评分结果

        【子类必须实现】
        """
        raise NotImplementedError(f"{self.tool_name}: score_pdb() must be implemented")

    # ── 公开 API（一般不需要覆盖）──────────────────────────

    async def predict_single(self, request: PdbScoreRequest) -> PdbScoreResponse:
        """
        处理单次 PDB 评分请求。
        1. 确保模型已加载（双重检查锁定）
        2. 调用 score_pdb()
        3. 包装成 PdbScoreResponse
        """
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        try:
            result = await self.score_pdb(
                pdb_content=request.pdb_content,
                sequence=request.sequence,
                chain_id=request.chain_id,
            )
            result.peptide_id = request.peptide_id or "unknown"
            return PdbScoreResponse(
                success=True,
                peptide_id=result.peptide_id,
                result=result,
                error=None,
            )
        except Exception as e:
            return PdbScoreResponse(
                success=False,
                peptide_id=request.peptide_id,
                result=None,
                error=str(e),
            )

    async def predict_batch(
        self, request: PdbBatchScoreRequest
    ) -> PdbBatchScoreResponse:
        """
        处理批量 PDB 评分请求。

        PDB 评分通常比纯序列评分慢（需要解析结构），
        默认并发限制为 10。
        """
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        semaphore = asyncio.Semaphore(10)

        async def bounded_predict(item: PdbScoreRequest) -> PdbScoreResult | None:
            async with semaphore:
                try:
                    result = await self.score_pdb(
                        pdb_content=item.pdb_content,
                        sequence=item.sequence,
                        chain_id=item.chain_id,
                    )
                    result.peptide_id = item.peptide_id or "unknown"
                    return result
                except Exception:
                    return None

        tasks = [bounded_predict(item) for item in request.requests]
        results = await asyncio.gather(*tasks)

        valid_results = [r for r in results if r is not None]

        return PdbBatchScoreResponse(
            success=True,
            results=valid_results,
            total=len(valid_results),
            error=None
            if len(valid_results) == len(request.requests)
            else f"{len(valid_results)}/{len(request.requests)} succeeded",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 第三部分：FastAPI 应用工厂
# ═══════════════════════════════════════════════════════════════════════════════


def create_app(ToolClass: type[PdbScoringService]) -> FastAPI:
    """
    工厂函数：基于工具类创建完整的 FastAPI 应用。

    【参数】
    - ToolClass: 一个继承自 PdbScoringService 的类

    【返回值】
    - 一个配置好的 FastAPI 应用

    【使用例子】
    -----------
    class MyStabilityService(PdbScoringService):
        ...

    app = create_app(MyStabilityService)
    uvicorn.run(app, host="0.0.0.0", port=8201)
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

    @app.post("/predict", response_model=PdbScoreResponse)
    async def predict(request: PdbScoreRequest):
        """
        单次 PDB 评分：POST /predict

        【请求格式】
        {"pdb_content": "ATOM ...", "sequence": "...", "chain_id": "A", "peptide_id": "..."}

        【响应格式】
        {"success": true, "peptide_id": "...", "result": {"score": 0.82, "label": "stable"}, "error": null}
        """
        return await tool_instance.predict_single(request)

    @app.post("/predict/batch", response_model=PdbBatchScoreResponse)
    async def predict_batch(request: PdbBatchScoreRequest):
        """
        批量 PDB 评分：POST /predict/batch

        【请求格式】
        {"requests": [{"pdb_content": "...", "peptide_id": "..."}, ...]}

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
            input_format={
                "pdb_content": "string (PDB format)",
                "sequence": "string (optional)",
                "chain_id": "string (optional)",
            },
            output_format={"score": "float 0-1", "label": "string", "details": "object"},
            recommended_batch_size=ToolClass.recommended_batch_size,
        )

    return app


# ═══════════════════════════════════════════════════════════════════════════════
# 第四部分：启动入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("TOOL_PORT", "8201"))
    HOST = os.environ.get("TOOL_HOST", "0.0.0.0")
    TOOL_CLASS = os.environ.get("TOOL_CLASS", "")

    if not TOOL_CLASS:
        print("ERROR: TOOL_CLASS environment variable must be set")
        print("Example: TOOL_CLASS=tools.mystability.service:MyStabilityService")
        sys.exit(1)

    module_path, class_name = TOOL_CLASS.rsplit(":", 1)
    module = __import__(module_path, fromlist=[class_name])
    ToolClass = getattr(module, class_name)

    app = create_app(ToolClass)
    uvicorn.run(app, host=HOST, port=PORT)
