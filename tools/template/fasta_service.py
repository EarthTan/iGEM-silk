# Bio Tool Service 模板
# ==========================
#
# 【这个文件是什么？】
# ------------------
# 这是一个"模板文件"，用来帮助我们快速创建新的"工具微服务"。
# 想象一下：你要创建一个"抗氧化预测工具"的服务。
# 如果从零开始写，要处理很多复杂的事情：HTTP 接口、并发控制、错误处理...
# 但是用这个模板，只需要：
#   1. 继承 FastaToolService 类
#   2. 实现 load_model() 方法（告诉我怎么加载模型）
#   3. 实现 predict_impl() 方法（告诉我怎么预测）
# 然后这个模板会自动帮你处理所有其他的事情！
#
# 【类比】
# -------
# 把这个模板想象成一张"烘焙食谱模板"：
#   - 甜品师（FastaToolService）只需要决定：用什么原料？烤多久？
#   - 食谱模板（create_app）自动处理：用什么温度？烤箱怎么预热？
#
# 【如何启动这个服务】
# ------------------
# 方式一：直接启动模板（不推荐，需要设置环境变量）
#   TOOL_CLASS=tools.anoxpepred.service:AnOxPePredService
#   uvicorn tools.template.fasta_service:app --port 8001 --host 0.0.0.0
#
# 方式二：创建自己的服务（推荐）
#   假设你创建了一个 MyToolService 类
#   app = create_app(MyToolService)
#   uvicorn.run(app, port=8001)

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, ClassVar

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
# 第一部分：请求和响应模型
# ═══════════════════════════════════════════════════════════════════════════════
#
# 【什么是"请求"和"响应"？】
# -------------------------
# 简单来说：
#   - 请求（Request）= 用户发给服务的东西（比如：要预测的氨基酸序列）
#   - 响应（Response）= 服务返回给用户的东西（比如：预测分数 0.85）
#
# 在代码里，"请求"和"响应"都是 Python 的"类"，用来描述数据的结构。
# 这样每个字段是什么意思就一目了然了。
#
# 【为什么用 Pydantic？】
# ----------------------
# Pydantic 是一个数据验证库。我们用它来定义"请求"和"响应"的结构。
# 好处是：用户发来数据时，Pydantic 会自动检查数据格式对不对。
#   - 比如要求 score 必须是 0-1 之间的数字，如果用户传了 "hello"，会自动报错
#   - 比如要求 sequence 不能为空，如果用户传了 ""，会自动报错
# 这样可以避免很多奇怪的错误。


# ─────────────────────────────────────────────────────────────────────────────
# PredictRequest：单序列预测请求
# ─────────────────────────────────────────────────────────────────────────────
class PredictRequest(BaseModel):
    """
    单序列预测请求。

    【什么时候用？】
    当用户想预测一条肽序列时（比如"YVPLPNVPQG"），发送这个请求。

    【字段说明】
    - sequence: 要预测的氨基酸序列（字符串），长度 1-5000 个字符
    - peptide_id: 这条序列的名字/编号（可选）。如果不提供，默认叫 "unknown"

    【例子】
    {
        "sequence": "YVPLPNVPQG",
        "peptide_id": "pep_001"
    }
    """

    sequence: str = Field(..., min_length=1, max_length=5000, description="氨基酸序列")
    peptide_id: str | None = Field(None, description="肽 ID（可选）")


# ─────────────────────────────────────────────────────────────────────────────
# BatchPredictRequest：批量预测请求
# ─────────────────────────────────────────────────────────────────────────────
class BatchPredictRequest(BaseModel):
    """
    批量预测请求。

    【什么时候用？】
    当用户想一次预测多条序列时（比如一次预测 100 条），发送这个请求。
    比一条一条预测快很多，因为可以"并行处理"。

    【字段说明】
    - sequences: 一个"列表"，里面每个元素都是 PredictRequest（单条序列的请求）

    【例子】
    {
        "sequences": [
            {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"},
            {"sequence": "AVPQVFPG", "peptide_id": "pep_002"}
        ]
    }
    """

    sequences: list[PredictRequest] = Field(..., min_length=1, max_length=1000)


# ─────────────────────────────────────────────────────────────────────────────
# ToolResult：工具预测结果（统一格式）
# ─────────────────────────────────────────────────────────────────────────────
class ToolResult(BaseModel):
    """
    工具预测结果（统一格式）。

    【这个类是做什么的？】
    所有工具（抗氧化、毒性、溶血...）返回的结果，都用这个统一的格式。
    这样不管是什么工具，Orchestrator 都用一样的方式处理。

    【字段说明】
    - peptide_id: 这条序列的名字（默认 "unknown"）
    - sequence: 原始的氨基酸序列
    - score: 预测分数，范围 0.0 到 1.0
      - 0.0 = 完全没效果/非常危险
      - 1.0 = 效果最好/完全安全
    - label: 预测的标签，比如 "antioxidant"（抗氧化）、"toxic"（有毒）
    - details: 额外的详细信息（字典格式），比如预测的中间结果、置信度等

    【例子】
    {
        "peptide_id": "pep_001",
        "sequence": "YVPLPNVPQG",
        "score": 0.82,
        "label": "antioxidant",
        "details": {"confidence": 0.95, "method": "LSTM"}
    }
    """

    peptide_id: str = "unknown"
    sequence: str = ""
    score: float = Field(..., ge=0.0, le=1.0, description="预测分数 0-1")
    label: str = Field(..., description="预测标签（如 antioxidant, toxic, non-toxic）")
    details: dict[str, Any] = Field(default_factory=dict, description="附加详细信息")


# ─────────────────────────────────────────────────────────────────────────────
# PredictResponse：单序列预测响应
# ─────────────────────────────────────────────────────────────────────────────
class PredictResponse(BaseModel):
    """
    单序列预测响应。

    【什么时候用？】
    服务处理完单序列预测后，返回给用户的结果。

    【字段说明】
    - success: 是否成功（True/False）
    - peptide_id: 序列的名字
    - sequence: 原始序列
    - result: 预测结果（ToolResult 类型），如果失败则是 None
    - error: 错误信息，如果成功则是 None

    【例子】
    {
        "success": True,
        "peptide_id": "pep_001",
        "sequence": "YVPLPNVPQG",
        "result": {"score": 0.82, "label": "antioxidant", ...},
        "error": None
    }
    """

    success: bool
    peptide_id: str | None = None
    sequence: str | None = None
    result: ToolResult | None = None
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# BatchPredictResponse：批量预测响应
# ─────────────────────────────────────────────────────────────────────────────
class BatchPredictResponse(BaseModel):
    """
    批量预测响应。

    【什么时候用？】
    服务处理完批量预测后，返回给用户的结果。

    【字段说明】
    - success: 是否全部成功（如果有任何失败，返回 False）
    - results: 所有预测结果的列表
    - total: 成功预测的数量
    - error: 如果有失败的序列，显示错误信息

    【例子】
    {
        "success": True,
        "results": [..., ...],  # 100 个 ToolResult
        "total": 100,
        "error": None
    }
    """

    success: bool
    results: list[ToolResult]
    total: int
    error: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# HealthResponse：健康检查响应
# ─────────────────────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    """
    健康检查响应。

    【什么时候用？】
    当 Orchestrator 想检查某个工具服务是否正常运行时，发送这个请求。
    如果服务崩溃了，/health 会返回"不健康"的状态。

    【字段说明】
    - status: 健康状态（"healthy" = 正常，"loading" = 还在加载模型）
    - tool_name: 工具的名字
    - version: 工具的版本
    - model_loaded: 模型是否已加载（True/False）
    """

    status: str
    tool_name: str
    version: str
    model_loaded: bool
    model: dict | None = None
    system: dict | None = None


# ─────────────────────────────────────────────────────────────────────────────
# InfoResponse：工具信息响应
# ─────────────────────────────────────────────────────────────────────────────
class InfoResponse(BaseModel):
    """
    工具信息响应。

    【什么时候用？】
    当用户想了解某个工具的基本信息时（比如：支持什么功能？输入格式是什么？）

    【字段说明】
    - tool_name: 工具的名字
    - version: 工具的版本
    - description: 工具的描述
    - capabilities: 工具支持的功能列表，比如 ["predict", "predict/batch"]
    - input_format: 输入格式的说明
    - output_format: 输出格式的说明
    - recommended_batch_size: 推荐每次批量预测的最大数量
    """

    tool_name: str
    version: str
    description: str
    capabilities: list[str]
    input_format: dict[str, str]
    output_format: dict[str, str]
    recommended_batch_size: int


# ═══════════════════════════════════════════════════════════════════════════════
# 第二部分：FastaToolService 基类
# ═══════════════════════════════════════════════════════════════════════════════
#
# 【什么是"基类"？】
# ----------------
# 基类就像是一张"蓝图"，定义了所有工具服务"必须有什么"。
# 如果你想创建一个新的工具服务，只需要：
#   1. 继承 FastaToolService（相当于说"我要基于这个蓝图来创建"）
#   2. 填入你自己特有的内容（比如：怎么加载模型？怎么预测？）
#
# 【什么是"抽象方法"？】
# --------------------
# 方法名后面有 "raise NotImplementedError" 的，就是"抽象方法"。
# 抽象方法的意思是："子类必须实现这个方法，否则会报错"。
# 就像是一份合同："我允许你继承，但你必须实现这些方法"。
#
# 【什么是"异步"（async/await）？】
# -------------------------------
# async/await 是 Python 处理"并发"的方式。
# 简单理解：可以不排队，同时做很多事情。
# 比如：同时调用 10 个工具服务，而不是一个一个排队。


class FastaToolService:
    """
    所有工具服务的"基类"（蓝图）。

    【如果要用这个基类创建新工具，步骤是：】
    -------------------------------------------------
    1. 创建一个新类，继承 FastaToolService
    2. 设置类属性：tool_name（工具名字）、version（版本）、description（描述）
    3. 实现 load_model() 方法：告诉我怎么加载你的模型
    4. 实现 predict_impl() 方法：告诉我怎么对一条序列做预测

    【例子】
    --------
    class AnOxPePredService(FastaToolService):
        tool_name = "anoxpepred"           # 工具名字
        version = "1.1.0"                  # 版本号
        description = "抗氧化肽预测工具"   # 描述

        async def load_model(self):
            # 在这里加载你的模型
            self.model = load_my_model()

        async def predict_impl(self, sequence):
            # 在这里实现预测逻辑
            score = self.model.predict(sequence)
            return ToolResult(score=score, label="...")

    【关于"并发控制"】
    -----------------
    同一个工具服务可能同时收到很多请求（比如同时 100 个人要用）。
    为了防止模型被"挤爆"，我们用了一个"锁"（asyncio.Lock）。
    只有拿到锁的请求才能使用模型，其他请求要排队。
    这就像是一个厕所，同一时间只能一个人用。
    """

    # ── 类属性（子类必须覆盖）────────────────────────────
    # 类属性的意思是："这个类的所有对象都共享这个值"
    # 子类必须设置这些属性，否则会使用默认值（但不推荐）

    tool_name: ClassVar[str] = "template"  # 工具的唯一名字
    version: ClassVar[str] = "1.0.0"  # 版本号
    description: ClassVar[str] = "Template bio tool service"  # 描述
    recommended_batch_size: ClassVar[int] = 50  # 推荐批量大小

    # ── 实例属性 ──────────────────────────────────────────
    # 实例属性是每个对象自己独有的，不会共享

    model: Any = None  # 加载的模型对象（可以是任意类型）

    def __init__(self):
        """
        初始化服务实例。

        【为什么要加锁？】
        -----------------
        self._lock 是一个"异步锁"。
        当多个请求同时到来时，我们需要确保"模型加载"这件事不会重复执行。
        想象一下：如果 100 个请求同时到来，都发现模型没加载，都去加载...
        那模型就会被加载 100 次，可能会把内存撑爆。

        self._loaded 用来记录"模型是否已经加载过"。
        只有第一次需要加载，之后的请求直接用就行。

        self._model_status 是 /health 返回的模型状态详情，
        子类在 load_model() 过程中更新它。
        """
        self._lock = asyncio.Lock()  # 并发控制锁
        self._loaded = False  # 模型是否已加载的标记
        self._model_status: dict | None = None  # 模型状态详情
        self._system_info: dict | None = None  # 系统环境信息

    @staticmethod
    def shared_models_dir() -> Path:
        """tools/models/ — cross-service shared model cache."""
        return Path(__file__).parent.parent / "models"

    @staticmethod
    def shared_torch_home() -> Path:
        """tools/models/fair-esm/ — shared TORCH_HOME for fair-esm models."""
        return FastaToolService.shared_models_dir() / "fair-esm"

    async def load_model(self) -> None:
        """
        加载模型权重。

        【什么时候调用？】
        服务启动的时候调用一次，然后模型就常驻内存。
        之后每次预测都直接用这个模型，不会重新加载。

        【子类必须实现这个方法】
        ----------------------
        如果不实现，会抛出 NotImplementedError 错误。

        【例子】
        -------
        async def load_model(self):
            import tensorflow as tf
            self.model = tf.keras.models.load_model("path/to/model.h5")
        """
        raise NotImplementedError(f"{self.tool_name}: load_model() must be implemented")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        核心预测逻辑。

        【什么时候调用？】
        每当有一个预测请求到来时，这个方法就会被调用。

        【参数】
        - sequence: 氨基酸序列（字符串）

        【返回值】
        - ToolResult: 包含预测分数和标签的结果

        【子类必须实现这个方法】
        ----------------------
        如果不实现，会抛出 NotImplementedError 错误。

        【例子】
        -------
        async def predict_impl(self, sequence):
            # 把序列转成模型需要的格式
            features = self._extract_features(sequence)
            # 用模型预测
            score = self.model.predict(features)[0]
            # 返回结果
            return ToolResult(
                score=float(score),
                label="antioxidant" if score > 0.5 else "non-antioxidant"
            )
        """
        raise NotImplementedError(
            f"{self.tool_name}: predict_impl() must be implemented"
        )

    # ── 公开 API（一般不需要覆盖）──────────────────────────
    # 下面这些方法是"公开"的，可以被外部调用。
    # 它们已经实现了并发控制和错误处理，子类一般不需要修改。

    async def predict_single(self, request: PredictRequest) -> PredictResponse:
        """
        处理单序列预测请求。

        【这个方法是做什么的？】
        1. 确保模型已加载（如果没有，先加载）
        2. 调用 predict_impl() 做预测
        3. 包装成 PredictResponse 返回

        【关于"双重检查锁定"】
        --------------------
        为什么需要双重检查？
        假设同时来了两个请求，都发现模型没加载...
        没有锁的话，两个都会去加载模型，可能导致重复加载。
        有了锁，第一个请求会"锁定"，然后开始加载。
        第二个请求到了，发现锁被占用，就等着...
        等第一个加载完，第二个再进来，发现模型已经加载好了，就不用再加载了。
        """
        # 第一步：确保模型已加载
        if not self._loaded:
            async with self._lock:  # 获取锁
                if not self._loaded:  # 双重检查
                    await self.load_model()
                    self._loaded = True

        # 第二步：执行预测
        try:
            result = await self.predict_impl(request.sequence)
            result.peptide_id = request.peptide_id or "unknown"
            result.sequence = request.sequence
            return PredictResponse(
                success=True,
                peptide_id=result.peptide_id,
                sequence=request.sequence,
                result=result,
                error=None,
            )
        except Exception as e:
            # 预测出错了，返回错误信息
            return PredictResponse(
                success=False,
                peptide_id=request.peptide_id,
                sequence=request.sequence,
                result=None,
                error=str(e),
            )

    async def predict_batch(self, request: BatchPredictRequest) -> BatchPredictResponse:
        """
        处理批量预测请求。

        【什么是"信号量"（Semaphore）？】
        -------------------------------
        semaphore = asyncio.Semaphore(10) 的意思是：
        "最多同时处理 10 个请求"。

        想象一下：一个餐厅有 10 个厨师，如果来了 100 个客人...
        不能让 100 个客人同时占用厨师，否则会乱套。
        信号量就是用来限制"同时执行的数量"。

        【处理流程】
        -----------
        1. 确保模型已加载
        2. 创建一个信号量，限制同时最多 10 个预测
        3. 把所有请求包装成"任务"（task）
        4. asyncio.gather(*tasks) 表示"同时执行所有任务"
        5. 收集结果，返回
        """
        # 确保模型已加载
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        # 限制并发数：最多同时处理 10 个
        semaphore = asyncio.Semaphore(10)

        async def bounded_predict(item: PredictRequest) -> ToolResult | None:
            """
            在信号量限制下执行预测。
            如果超过 10 个请求同时到来，第 11 个要等前面的完成。
            """
            async with semaphore:
                try:
                    result = await self.predict_impl(item.sequence)
                    result.peptide_id = item.peptide_id or "unknown"
                    result.sequence = item.sequence
                    return result
                except Exception:
                    # 预测失败，返回 None
                    return None

        # 并发执行所有预测
        tasks = [bounded_predict(item) for item in request.sequences]
        results = await asyncio.gather(*tasks)

        # 过滤掉失败的（None）
        valid_results = [r for r in results if r is not None]

        # 返回结果
        return BatchPredictResponse(
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
#
# 【什么是"工厂函数"？】
# --------------------
# 工厂函数就像是一个"模板机"：
# 输入一个"工具类"，输出一个"完整的 FastAPI 应用"。
# 你不需要知道 FastAPI 怎么用，只需要：
#   1. 定义你的工具类（继承 FastaToolService）
#   2. 调用 create_app(你的工具类)
#   3. 得到一个完整的 Web 服务！
#
# 【什么是 FastAPI？】
# ------------------
# FastAPI 是一个 Python 的 Web 框架，用来构建 HTTP 服务。
# 你只需要定义"请求格式"和"响应格式"，FastAPI 会自动处理 HTTP 细节。
# 它还自动生成文档（/docs 页面），非常方便调试。


def create_app(ToolClass: type[FastaToolService]) -> FastAPI:
    """
    工厂函数：基于工具类创建完整的 FastAPI 应用。

    【参数】
    - ToolClass: 一个继承自 FastaToolService 的类

    【返回值】
    - 一个配置好的 FastAPI 应用

    【使用例子】
    -----------
    from tools.template.fasta_service import create_app, FastaToolService, ToolResult

    class MyToolService(FastaToolService):
        tool_name = "mytool"
        version = "1.0.0"
        description = "我的自定义工具"

        async def load_model(self):
            self.model = load_my_model()

        async def predict_impl(self, sequence: str) -> ToolResult:
            score = self.model.predict(sequence)
            return ToolResult(score=score, label="active" if score > 0.5 else "inactive")

    app = create_app(MyToolService)

    # 启动服务：
    # uvicorn tools.mytool.service:app --port 8001 --host 0.0.0.0
    """
    tool_instance = ToolClass()  # 创建工具类的实例

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        lifespan（生命周期）函数。

        这个函数在服务"启动时"和"关闭时"会被调用。

        【启动时】（yield 之前）
        - 加载模型
        - 如果加载失败，不退出服务，但标记为"未就绪"

        【关闭时】（yield 之后）
        - 清理资源（比如释放 GPU 内存）
        """
        # 启动时：加载模型
        try:
            await tool_instance.load_model()
            tool_instance._loaded = True
            print(f"[{ToolClass.tool_name}] Model loaded successfully")
        except Exception as e:
            print(f"[{ToolClass.tool_name}] Failed to load model: {e}")
            # 不退出，允许服务启动但标记为未就绪
        yield
        # 关闭时：清理资源
        if hasattr(tool_instance.model, "clear_session"):
            tool_instance.model.clear_session()
        print(f"[{ToolClass.tool_name}] Shutdown")

    # 创建 FastAPI 应用
    app = FastAPI(
        title=ToolClass.tool_name,
        description=ToolClass.description,
        version=ToolClass.version,
        lifespan=lifespan,
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # 定义路由（即：HTTP 接口）
    # ═══════════════════════════════════════════════════════════════════════════
    #
    # 路由的意思是："当用户访问这个 URL 时，执行什么代码"
    #
    # 常见 HTTP 方法：
    # - GET：获取数据（比如查看工具信息）
    # - POST：提交数据（比如提交序列进行预测）
    # - PUT：更新数据
    # - DELETE：删除数据

    @app.get("/")
    async def root():
        """
        根路径 /
        访问 http://localhost:8001/ 会返回服务信息
        """
        return {
            "service": ToolClass.tool_name,
            "version": ToolClass.version,
            "docs": "/docs",  # 文档地址
        }

    @app.post("/predict", response_model=PredictResponse)
    async def predict(request: PredictRequest):
        """
        预测接口：POST /predict

        【什么时候用？】
        用户想预测单条序列时，发送 POST 请求到这个接口。

        【请求格式】
        {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}

        【响应格式】
        {"success": true, "peptide_id": "pep_001", "sequence": "YVPLPNVPQG", "result": {...}, "error": null}
        """
        return await tool_instance.predict_single(request)

    @app.post("/predict/batch", response_model=BatchPredictResponse)
    async def predict_batch(request: BatchPredictRequest):
        """
        批量预测接口：POST /predict/batch

        【什么时候用？】
        用户想一次预测多条序列时，使用这个接口。
        比一条一条预测快很多（并行处理）。

        【请求格式】
        {"sequences": [{"sequence": "...", "peptide_id": "..."}, ...]}

        【响应格式】
        {"success": true, "results": [...], "total": 100, "error": null}
        """
        return await tool_instance.predict_batch(request)

    @app.get("/health", response_model=HealthResponse)
    async def health():
        """
        健康检查接口：GET /health

        【什么时候用？】
         会定期调用这个接口，检查服务是否正常。

        【响应格式】
        {"status": "healthy", "tool_name": "anoxpepred", "version": "1.1.0", "model_loaded": true}
        """
        return HealthResponse(
            status="healthy" if tool_instance._loaded else "loading",
            tool_name=ToolClass.tool_name,
            version=ToolClass.version,
            model_loaded=tool_instance._loaded,
            model=tool_instance._model_status,
            system=tool_instance._system_info,
        )

    @app.get("/info", response_model=InfoResponse)
    async def info():
        """
        工具信息接口：GET /info

        【什么时候用？】
        用户想了解这个工具的功能、输入输出格式时，调用这个接口。

        【响应格式】
        {
            "tool_name": "anoxpepred",
            "version": "1.1.0",
            "description": "抗氧化肽预测工具",
            "capabilities": ["predict", "predict/batch"],
            "input_format": {"sequence": "string(amino acid sequence)"},
            "output_format": {"score": "float 0-1", "label": "string"},
            "recommended_batch_size": 50
        }
        """
        return InfoResponse(
            tool_name=ToolClass.tool_name,
            version=ToolClass.version,
            description=ToolClass.description,
            capabilities=["predict", "predict/batch"],
            input_format={"sequence": "string (amino acid sequence)"},
            output_format={"score": "float 0-1", "label": "string"},
            recommended_batch_size=ToolClass.recommended_batch_size,
        )

    return app


# ═══════════════════════════════════════════════════════════════════════════════
# 第四部分：启动入口（用于直接运行模板）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 【这段代码什么时候用？】
# ----------------------
# 当你想"直接运行这个文件"来启动服务时，这段代码会生效。
# 一般不推荐这样做，而是通过命令行指定 TOOL_CLASS 环境变量。

if __name__ == "__main__":
    import uvicorn

    # 从环境变量读取配置（或者使用默认值）
    PORT = int(os.environ.get("TOOL_PORT", "8001"))  # 默认端口 8001
    HOST = os.environ.get("TOOL_HOST", "0.0.0.0")  # 默认监听所有网卡
    TOOL_CLASS = os.environ.get("TOOL_CLASS", "")  # 必须指定工具类

    if not TOOL_CLASS:
        print("ERROR: TOOL_CLASS environment variable must be set")
        print("Example: TOOL_CLASS=tools.anoxpepred.service:AnOxPePredService")
        sys.exit(1)

    # 动态导入指定的工具类
    # 比如 TOOL_CLASS = "tools.anoxpepred.service:AnOxPePredService"
    # 会变成：module = tools.anoxpepred.service, class_name = AnOxPePredService
    module_path, class_name = TOOL_CLASS.rsplit(":", 1)
    module = __import__(module_path, fromlist=[class_name])
    ToolClass = getattr(module, class_name)

    # 创建应用并启动
    app = create_app(ToolClass)
    uvicorn.run(app, host=HOST, port=PORT)

