"""
services/api/main.py
====================

【这个文件是什么？】
--------------------
main.py 是整个微服务系统的"前台接待处"（REST API）。

想象一下：一家餐厅的前台服务员（API）接收客人的点单（HTTP 请求），
然后把点单转交给厨房（Orchestrator），厨房做好菜后再由前台端给客人。

【什么是 FastAPI？】
------------------
FastAPI 是一个 Python 的 Web 框架，专门用来构建 HTTP API。

它能做的事情：
  1. 接收 HTTP 请求（GET、POST 等）
  2. 验证请求数据（比如：序列不能为空、长度不能超过 5000）
  3. 调用业务逻辑（Orchestrator）
  4. 返回响应（JSON 格式）

为什么选 FastAPI？
  - 快：性能接近 Node.js 和 Go
  - 简单：不用写很多样板代码
  - 安全：自动生成 API 文档（/docs 页面）
  - 类型安全：基于 Pydantic 的数据验证

【什么是"CORS"？】
-----------------
CORS = Cross-Origin Resource Sharing（跨域资源共享）。

浏览器的安全策略：网页只能访问"同源"的服务器。
"同源" = 协议 + 域名 + 端口都相同。

如果前端运行在 http://localhost:3000，而后端在 http://localhost:8000，
这就叫"跨域"，浏览器会阻止访问。

加上 CORS 中间件后，服务器告诉浏览器："允许来自任何源的请求"。

【API 提供了哪些接口？】
----------------------
  GET  /           → 欢迎信息
  GET  /health     → 健康检查（服务是否正常）
  GET  /tools      → 查看所有可用工具
  POST /predict    → 预测单条序列
  POST /predict/batch → 批量预测多条序列

【什么是"路由"（Route）？】
-------------------------
路由就是"URL 路径到处理函数"的映射。

比如：
  GET /health  → 调用 health() 函数
  POST /predict → 调用 predict() 函数

FastAPI 会根据请求的 HTTP 方法和路径，自动匹配到对应的函数。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ..orchestrator.core import Orchestrator, PredictionRequest, FusionResult
from ..orchestrator.scoring import rank_candidates


# ═══════════════════════════════════════════════════════════════════════════════
# 第一部分：请求 / 响应模型
# ═══════════════════════════════════════════════════════════════════════════════
#
#【什么是"请求模型"？】
#---------------------
# 请求模型定义了"客户端可以发给服务器什么数据"。
# 使用 Pydantic 的 BaseModel，可以自动验证数据的格式。
#
# 好处：
#   - 如果客户端发的数据不对，FastAPI 自动返回 422 错误
#   - 不用手动写 if sequence is None: 这种检查
#
#【什么是"响应模型"？】
#---------------------
# 响应模型定义了"服务器返回给客户端什么数据"。
# 这不是强制的（可以不写），但写了可以让文档更清晰。

# ─────────────────────────────────────────────────────────────────────────────
# SinglePredictRequest：单序列预测请求
# ─────────────────────────────────────────────────────────────────────────────
class SinglePredictRequest(BaseModel):
    """
    单序列预测请求。

    【什么时候用？】
    当用户想要预测一条肽序列时，发送这个请求。

    【字段说明】
    - sequence: 要预测的氨基酸序列（必填，1-5000 个字符）
    - peptide_id: 肽的 ID（可选，不提供则自动生成）
    - tools: 要调用的工具列表（可选，None = 使用默认 P0 工具）

    【请求格式例子】
    {
        "sequence": "YVPLPNVPQG",
        "peptide_id": "pep_001",
        "tools": ["anoxpepred", "toxipred3"]
    }
    """
    sequence: str = Field(..., min_length=1, max_length=5000, description="氨基酸序列")
    peptide_id: str | None = Field(None, description="肽 ID")
    tools: list[str] | None = Field(None, description="指定工具列表，None=所有 P0 工具")


# ─────────────────────────────────────────────────────────────────────────────
# BatchPredictRequest：批量预测请求
# ─────────────────────────────────────────────────────────────────────────────
class BatchPredictRequest(BaseModel):
    """
    批量预测请求。

    【什么时候用？】
    当用户想要一次预测多条肽序列时，发送这个请求。
    比如：已经生成了 100 条候选序列，想批量评估哪个最好。

    【字段说明】
    - sequences: 序列列表（必填，最多 1000 条）
    - tools: 要调用的工具列表（可选）
    - top_k: 返回分数最高的前几名（默认 50，最少 1，最多 1000）

    【请求格式例子】
    {
        "sequences": [
            {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"},
            {"sequence": "AVPQVFPG", "peptide_id": "pep_002"}
        ],
        "tools": null,
        "top_k": 10
    }
    """
    sequences: list[SinglePredictRequest] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="序列列表（最多 1000 条）"
    )
    tools: list[str] | None = Field(None, description="指定工具列表")
    top_k: int = Field(50, ge=1, le=1000, description="返回 top k 结果")


# ─────────────────────────────────────────────────────────────────────────────
# ToolResultResponse：单个工具结果（用于响应）
# ─────────────────────────────────────────────────────────────────────────────
class ToolResultResponse(BaseModel):
    """
    单个工具的预测结果（用于 API 响应）。

    【什么时候用？】
    在返回融合结果时，每个工具的预测结果用这个格式。

    【字段说明】
    - tool_name: 工具名称
    - score: 预测分数（0-1）
    - label: 预测标签
    - latency_ms: 工具调用耗时（毫秒）
    - error: 错误信息（如果失败）
    """
    tool_name: str
    score: float | None
    label: str | None
    latency_ms: float
    error: str | None


# ─────────────────────────────────────────────────────────────────────────────
# FusionResultResponse：融合结果（用于响应）
# ─────────────────────────────────────────────────────────────────────────────
class FusionResultResponse(BaseModel):
    """
    融合结果（用于 API 响应）。

    【什么时候用？】
    返回给客户端的最终预测结果。

    【字段说明】
    - peptide_id: 肽 ID
    - sequence: 原始序列
    - fused_score: 融合分数（0-1）
    - fused_label: 融合标签
    - total_latency_ms: 总耗时（毫秒）
    - scoring_details: 评分详细分解
    - tool_results: 各工具的原始结果
    """
    peptide_id: str
    sequence: str
    fused_score: float | None
    fused_label: str | None
    total_latency_ms: float
    scoring_details: dict[str, Any] | None
    tool_results: list[ToolResultResponse]


# ─────────────────────────────────────────────────────────────────────────────
# BatchPredictResponse：批量预测响应
# ─────────────────────────────────────────────────────────────────────────────
class BatchPredictResponse(BaseModel):
    """
    批量预测响应。

    【字段说明】
    - success: 是否全部成功
    - total: 总共处理了多少条序列
    - returned: 返回了多少条结果（top_k）
    - results: 结果列表（按融合分数排序）
    """
    success: bool
    total: int
    returned: int
    results: list[FusionResultResponse]


# ─────────────────────────────────────────────────────────────────────────────
# HealthResponse：健康检查响应
# ─────────────────────────────────────────────────────────────────────────────
class HealthResponse(BaseModel):
    """
    健康检查响应。

    【什么时候用？】
    当需要检查服务是否正常运行时，调用 GET /health。

    【字段说明】
    - status: 健康状态（"healthy" = 正常）
    - service: 服务名称
    """
    status: str
    service: str


# ─────────────────────────────────────────────────────────────────────────────
# ToolInfo：工具信息
# ─────────────────────────────────────────────────────────────────────────────
class ToolInfo(BaseModel):
    """
    工具信息。

    【什么时候用？】
    在返回工具列表时，每个工具的信息用这个格式。

    【字段说明】
    - name: 工具名称
    - url: 工具的 HTTP 地址
    - type: 工具类型
    - priority: 优先级（0=P0 必须，1=P1 推荐，2=P2 可选）
    - requires_gpu: 是否需要 GPU
    """
    name: str
    url: str
    type: str
    priority: int
    requires_gpu: bool


# ─────────────────────────────────────────────────────────────────────────────
# ToolListResponse：工具列表响应
# ─────────────────────────────────────────────────────────────────────────────
class ToolListResponse(BaseModel):
    """
    工具列表响应。

    【什么时候用？】
    调用 GET /tools 时返回。
    """
    tools: list[ToolInfo]


# ═══════════════════════════════════════════════════════════════════════════════
# 第二部分：FastAPI 应用初始化
# ═══════════════════════════════════════════════════════════════════════════════
#
#【什么是 FastAPI 实例？】
#------------------------
# app = FastAPI(...) 创建了一个 FastAPI 应用实例。
# 这个实例包含了所有的路由、中间件、配置。

app = FastAPI(
    title="iGEM-silk Orchestrator",
    description="丝素蛋白融合功能肽设计平台的调度核心 API",
    version="1.0.0"
)
"""
创建 FastAPI 应用，配置元数据：
  - title: API 文档中显示的标题
  - description: API 描述
  - version: 版本号
"""

# ─────────────────────────────────────────────────────────────────────────────
# CORS 中间件配置
# ─────────────────────────────────────────────────────────────────────────────
#
#【为什么需要 CORS 中间件？】
#--------------------------
# 假设前端运行在 http://localhost:3000（React/Vue）
# 后端 API 运行在 http://localhost:8000
# 浏览器的同源策略会阻止前端访问后端

# 配置 CORS 中间件，允许所有来源的跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # 允许所有来源（生产环境建议限制为具体的域名）
    allow_credentials=True,   # 允许携带凭证（cookies）
    allow_methods=["*"],      # 允许所有 HTTP 方法（GET、POST、PUT、DELETE...）
    allow_headers=["*"],      # 允许所有请求头
)
"""
添加 CORS 中间件到 FastAPI 应用。
这样前端就可以跨域访问这个 API 了。
"""

# ─────────────────────────────────────────────────────────────────────────────
# 全局 Orchestrator 实例
# ─────────────────────────────────────────────────────────────────────────────

_orchestrator: Orchestrator | None = None
"""
全局的 Orchestrator 实例。

为什么需要全局变量？
  - Orchestrator 在启动时创建（startup 事件）
  - 在关闭时销毁（shutdown 事件）
  - 在请求处理时使用（predict 函数）

为什么要初始化为 None？
  - 因为启动前 _orchestrator 还不存在
  - 可以通过检查 _orchestrator is None 来判断是否已启动
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 第三部分：生命周期管理（启动/关闭）
# ═══════════════════════════════════════════════════════════════════════════════
#
#【什么是"生命周期事件"？】
#------------------------
# 应用启动时会触发 startup 事件，关闭时会触发 shutdown 事件。
# 我们可以在这两个事件中初始化和清理资源。

@app.on_event("startup")
async def startup():
    """
    应用启动时执行。

    【什么时候触发？】
    当 uvicorn 启动服务时（比如运行 uvicorn main:app）。

    【做了什么？】
    1. 创建 Orchestrator 实例
    2. 打印启动信息

    【注意】
    这是一个 async 函数，FastAPI 会自动等待它完成后再开始处理请求。
    """
    global _orchestrator
    _orchestrator = Orchestrator()
    print("[Orchestrator API] Started on http://localhost:8000")


@app.on_event("shutdown")
async def shutdown():
    """
    应用关闭时执行。

    【什么时候触发？】
    当 uvicorn 收到终止信号（比如 Ctrl+C）时。

    【做了什么？】
    1. 关闭 Orchestrator（释放 HTTP 客户端资源）
    2. 打印关闭信息

    【为什么需要手动关闭？】
    如果不调用 await _orchestrator.close()，
    HTTP 客户端占用的连接和内存可能不会被及时释放。
    """
    global _orchestrator
    if _orchestrator:
        await _orchestrator.close()
        print("[Orchestrator API] Shutdown")


# ═══════════════════════════════════════════════════════════════════════════════
# 第四部分：工具函数
# ═══════════════════════════════════════════════════════════════════════════════
#
#【_to_response 是做什么的？】
#---------------------------
# Orchestrator 返回的是 FusionResult（内部使用的数据结构）
# API 响应需要用 FusionResultResponse（Pydantic 模型）
# _to_response 就是做这个"转换"的工作

def _to_response(result: FusionResult) -> FusionResultResponse:
    """
    将 FusionResult 转换为 API 响应模型。

    【参数】
    - result: Orchestrator 返回的 FusionResult

    【返回值】
    - FusionResultResponse: API 响应格式

    【为什么需要转换？】
    - FusionResult 是内部数据结构，字段可能是复杂的对象
    - FusionResultResponse 是公开 API 的格式，需要简单、可序列化

    【转换过程】
    FusionResult.tool_results（ToolResult 列表）
      → [ToolResultResponse(...), ...]
    """
    return FusionResultResponse(
        peptide_id=result.peptide_id,
        sequence=result.sequence,
        fused_score=result.fused_score,
        fused_label=result.fused_label,
        total_latency_ms=result.total_latency_ms,
        scoring_details=result.scoring_details,
        tool_results=[
            ToolResultResponse(
                tool_name=r.tool_name,
                score=r.score,
                label=r.label,
                latency_ms=r.latency_ms,
                error=r.error
            )
            for r in result.tool_results
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 第五部分：API 路由
# ═══════════════════════════════════════════════════════════════════════════════
#
#【什么是"装饰器"（@app.get）？】
#------------------------------
# @app.get("/path") 是一个装饰器，表示：
#   "下面的函数处理 GET 请求到 /path 这个路径"
#
# 装饰器的工作方式：
#   @decorator
#   def func():
#       ...
#   # 等价于
#   func = decorator(func)

# ─────────────────────────────────────────────────────────────────────────────
# 根路径：GET /
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["root"])
async def root():
    """
    API 根路径。

    【什么时候用？】
    访问 http://localhost:8000/ 时显示欢迎信息。

    【返回信息】
    - service: 服务名称
    - version: 版本号
    - docs: API 文档地址
    - health: 健康检查地址
    - tools: 工具列表地址
    """
    return {
        "service": "iGEM-silk Orchestrator",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "tools": "/tools"
    }


# ─────────────────────────────────────────────────────────────────────────────
# 健康检查：GET /health
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["status"])
async def health():
    """
    健康检查接口。

    【什么时候用？】
    - 运维监控：检查服务是否正常运行
    - 负载均衡器：检查哪些服务节点可用
    - 自动化脚本：检查服务是否启动

    【返回格式】
    {
        "status": "healthy",
        "service": "orchestrator"
    }

    【注意】
    这个接口不检查 Orchestrator 是否真的能工作，只是检查 API 服务本身是否活着。
    要检查 Orchestrator，需要调用 /predict 看是否能正常处理请求。
    """
    return HealthResponse(status="healthy", service="orchestrator")


# ─────────────────────────────────────────────────────────────────────────────
# 工具列表：GET /tools
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/tools", response_model=ToolListResponse, tags=["info"])
async def list_tools():
    """
    列出所有可用工具。

    【什么时候用？】
    前端想知道有哪些工具可用、各工具的 URL 和配置。

    【返回格式】
    {
        "tools": [
            {"name": "anoxpepred", "url": "http://localhost:8001", ...},
            {"name": "toxipred3", "url": "http://localhost:8003", ...},
            ...
        ]
    }
    """
    from ..orchestrator.registry import TOOL_REGISTRY
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


# ─────────────────────────────────────────────────────────────────────────────
# 单序列预测：POST /predict
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/predict", response_model=FusionResultResponse, tags=["prediction"])
async def predict(request: SinglePredictRequest):
    """
    单序列预测。

    【什么时候用？】
    当用户输入一条肽序列，想要知道它的：
      - 抗氧化能力（融合分数）
      - 各工具的详细预测结果

    【请求格式】
    POST /predict
    Content-Type: application/json

    {
        "sequence": "YVPLPNVPQG",
        "peptide_id": "pep_001",
        "tools": null
    }

    【响应格式】
    {
        "peptide_id": "pep_001",
        "sequence": "YVPLPNVPQG",
        "fused_score": 0.73,
        "fused_label": "antioxidant",
        "total_latency_ms": 523.5,
        "scoring_details": {...},
        "tool_results": [
            {"tool_name": "anoxpepred", "score": 0.82, ...},
            {"tool_name": "toxipred3", "score": 0.15, ...},
            {"tool_name": "hemopi2", "score": 0.22, ...}
        ]
    }

    【错误处理】
    - 503 Service Unavailable：如果 Orchestrator 还没初始化（启动失败）
    - 422 Unprocessable Entity：如果请求数据格式不对（比如 sequence 为空）
    """
    # 检查 Orchestrator 是否已初始化
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # 调用 Orchestrator 执行预测
    result = await _orchestrator.predict_single(
        PredictionRequest(
            sequence=request.sequence,
            peptide_id=request.peptide_id,
            tools=request.tools
        )
    )

    # 转换为响应格式并返回
    return _to_response(result)


# ─────────────────────────────────────────────────────────────────────────────
# 批量预测：POST /predict/batch
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/predict/batch", response_model=BatchPredictResponse, tags=["prediction"])
async def predict_batch(request: BatchPredictRequest):
    """
    批量预测多条序列。

    【什么时候用？】
    当用户有大量候选序列（比如 100 条），想要批量评估哪个最好。
    这个接口会自动：
      1. 并发处理所有序列
      2. 按融合分数排序
      3. 返回 top_k 个最好的结果

    【请求格式】
    POST /predict/batch
    Content-Type: application/json

    {
        "sequences": [
            {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"},
            {"sequence": "AVPQVFPG", "peptide_id": "pep_002"}
        ],
        "tools": null,
        "top_k": 10
    }

    【响应格式】
    {
        "success": true,
        "total": 100,
        "returned": 10,
        "results": [
            {"peptide_id": "pep_042", "fused_score": 0.85, ...},
            {"peptide_id": "pep_017", "fused_score": 0.82, ...},
            ...
        ]
    }

    【限制】
    - 最多一次处理 1000 条序列（max_length=1000）
    - 返回 top_k 条结果（默认 50，最多 1000）
    """
    # 检查 Orchestrator 是否已初始化
    if not _orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    # 把 API 请求格式转换为 Orchestrator 的格式
    requests = [
        PredictionRequest(
            sequence=req.sequence,
            peptide_id=req.peptide_id
        )
        for req in request.sequences
    ]

    # 执行批量预测
    results = await _orchestrator.predict_batch(requests, tools=request.tools)

    # 排序并取 top_k
    ranked = rank_candidates(results, top_k=request.top_k)

    # 返回响应
    return BatchPredictResponse(
        success=True,
        total=len(results),
        returned=len(ranked),
        results=[_to_response(r) for r in ranked]
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 第六部分：启动入口
# ═══════════════════════════════════════════════════════════════════════════════
#
#【这段代码什么时候用？】
#----------------------
# 当直接运行这个文件时（比如 python services/api/main.py），
# 会启动 FastAPI 服务。

if __name__ == "__main__":
    import uvicorn
    # 启动 uvicorn 服务器
    # host="0.0.0.0" 表示监听所有网卡（可以让其他机器访问）
    # port=8000 表示监听 8000 端口
    uvicorn.run(app, host="0.0.0.0", port=8000)

    """
    启动后可以访问：
      - API 文档：http://localhost:8000/docs
      - 健康检查：http://localhost:8000/health
      - 工具列表：http://localhost:8000/tools
      - 预测接口：http://localhost:8000/predict

    【推荐启动方式】
    直接运行这个文件只是用于开发调试。
    生产环境应该用 uvicorn 命令：
      uvicorn services.api.main:app --host 0.0.0.0 --port 8000
    这样可以获得更好的日志、性能和配置选项。
    """