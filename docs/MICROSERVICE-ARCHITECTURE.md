# iGEM-silk 微服务架构设计文档

> **版本**: v1.0.0
> **状态**: 完整设计，可执行
> **目的**: 为下一个 AI 实现者提供详细的架构蓝图与可执行代码
> **最后更新**: 2026-05-03

---

## 一、项目现状与架构目标

### 1.1 现状盘点

| 维度 | 当前状态 |
|------|----------|
| **工具数量** | 10 个独立工具，已全部安装并验证 |
| **主入口** | `main.py` 空壳（6 行占位代码） |
| **环境管理** | 各工具独立 `.venv`，无统一编排层 |
| **Python 版本** | 各工具不一致（3.10/3.11/3.12/3.13） |
| **项目阶段** | 探索期 v0.2，未进入工程实现 |

### 1.2 工具清单与分类

| 工具 | 功能 | 预测类型 | 模型重量 | Python 版本 | 优先级 |
|------|------|----------|----------|-------------|--------|
| **AnOxPePred** | 抗氧化活性 | 回归/二分类 | ⭐⭐（TensorFlow） | 3.10 | P0 |
| **BepiPred-3.0** | B 细胞表位 | 回归（每残基） | ⭐⭐⭐（ESM-2） | 3.11 | P0 |
| **ToxinPred3** | 毒性预测 | 二分类 | ⭐（sklearn） | 3.11 | P0 |
| **HemoPI2** | 溶血性 | 分类/回归 | ⭐⭐（ESM-2） | 3.12 | P0 |
| **MHCflurry** | MHC 结合亲和力 | 回归 | ⭐⭐（sklearn） | 3.10 | P1 |
| **pLM4CPPs** | 细胞穿膜肽 | 二分类 | ⭐⭐⭐（ESM-2+TF） | 3.13 | P1 |
| **GraphCPP** | CPP（图神经网络） | 二分类 | ⭐⭐⭐（PyG） | 3.11 | P2 |
| **MLCPP** | CPP（ML 方法） | 二分类 | ⭐（sklearn） | 3.11 | P2 |
| **TIPred** | 酪氨酸酶抑制肽 | 二分类 | ⭐（sklearn） | 3.11 | P1 |
| **AlgPred2** | 过敏原性 | 二分类 | ⭐（sklearn） | 3.11 | P1 |

### 1.3 架构设计目标

1. **环境隔离**: 每个工具运行在独立 Python 环境，互不干扰
2. **统一接口**: 所有工具暴露相同的 REST API，Orchestrator 无需感知差异
3. **弹性扩展**: 重的模型工具（ESM-2、PyG）长期驻留，避免重复初始化
4. **融合评分**: 多工具结果统一汇聚为综合评分
5. **最小运维**: 不引入 Kubernetes 等重基础设施，单机可运行

---

## 二、总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client                                   │
│                  (CLI / Streamlit UI)                           │
└─────────────────────────────┬───────────────────────────────────┘
                              │ HTTP/JSON
┌─────────────────────────────▼───────────────────────────────────┐
│                    Orchestrator (端口 8000)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │ Tool Registry│  │ Task Queue   │  │   Scoring Engine         │  │
│  │ (配置中心)    │  │ (asyncio)    │  │   (融合评分)             │  │
│  └──────────────┘  └──────────────┘  └──────────────────────────┘  │
└─────────────────────────────┬───────────────────────────────────┘
         │                    │                    │
   ┌─────┴─────┐       ┌─────┴─────┐       ┌─────┴─────┐
   │ Tool Svc  │       │ Tool Svc  │       │ Tool Svc  │
   │ AnOxPePred│       │BepiPred-3 │       │ToxinPred3 │
   │ :8001     │       │   .0      │       │  :8003    │
   │ (驻留)    │       │ :8002     │       │ (驻留)    │
   └───────────┘       └───────────┘       └───────────┘
   ┌───────────┐       ┌───────────┐       ┌───────────┐
   │ Tool Svc  │       │ Tool Svc  │       │ Tool Svc  │
   │ HemoPI2   │       │ MHCflurry │       │ pLM4CPPs  │
   │ :8004     │       │ :8005     │       │ :8006     │
   │ (驻留)    │       │ (驻留)    │       │ (驻留)    │
   └───────────┘       └───────────┘       └───────────┘
   ┌───────────┐       ┌───────────┐       ┌───────────┐
   │ Tool Svc  │       │ Tool Svc  │       │ Tool Svc  │
   │ TIPred    │       │ AlgPred2  │       │ GraphCPP  │
   │ :8007     │       │ :8008     │       │ :8009     │
   │ (驻留)    │       │ (驻留)    │       │ (驻留)    │
   └───────────┘       └───────────┘       └───────────┘
   ┌───────────┐
   │ Tool Svc  │
   │ MLCPP     │
   │ :8010     │
   │ (驻留)    │
   └───────────┘
```

### 2.1 端口分配表

| 服务 | 端口 | 模型重量 | 建议实例数 |
|------|------|----------|------------|
| orchestrator | 8000 | - | 1 |
| AnOxPePred | 8001 | ⭐⭐ | 1 |
| BepiPred-3.0 | 8002 | ⭐⭐⭐ | 1 |
| ToxinPred3 | 8003 | ⭐ | 2 |
| HemoPI2 | 8004 | ⭐⭐ | 1 |
| MHCflurry | 8005 | ⭐⭐ | 1 |
| pLM4CPPs | 8006 | ⭐⭐⭐ | 1 |
| TIPred | 8007 | ⭐ | 2 |
| AlgPred2 | 8008 | ⭐ | 2 |
| GraphCPP | 8009 | ⭐⭐⭐ | 1 |
| MLCPP | 8010 | ⭐ | 2 |

---

## 三、组件详细设计

### 3.1 Tool Service（统一 FastAPI 服务模板）

#### 3.1.1 标准接口规范

**每个 Tool Service 必须实现以下端点：**

```
POST /predict          单序列预测
POST /predict/batch   批量预测（重要！减少网络开销）
GET  /health          健康检查
GET  /info            工具信息（版本、输入输出格式）
```

**POST /predict 请求体：**
```json
{
  "sequence": "YVPLPNVPQG",
  "peptide_id": "pep_001"
}
```

**POST /predict 响应体：**
```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "score": 0.823,
    "label": "antioxidant",
    "details": {}
  },
  "error": null
}
```

**POST /predict/batch 请求体：**
```json
{
  "sequences": [
    {"peptide_id": "pep_001", "sequence": "YVPLPNVPQG"},
    {"peptide_id": "pep_002", "sequence": "FFVAPFPEVFGK"}
  ]
}
```

**POST /predict/batch 响应体：**
```json
{
  "success": true,
  "results": [
    {"peptide_id": "pep_001", "sequence": "YVPLPNVPQG", "score": 0.823, "label": "antioxidant"},
    {"peptide_id": "pep_002", "sequence": "FFVAPFPEVFGK", "score": 0.156, "label": "non-antioxidant"}
  ],
  "total": 2,
  "error": null
}
```

#### 3.1.2 FastAPI 服务模板

文件路径: `services/template/tool_service.py`

```python
#!/usr/bin/env python3
"""
Bio Tool Service Template
========================
每个工具服务都继承此模板，只需实现 predict_single() 和 predict_batch() 方法。
启动方式: uvicorn tool_service:app --port XXXX --host 0.0.0.0
"""

import sys
import asyncio
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


# ─── 请求/响应模型 ──────────────────────────────────────────────────────

class PredictRequest(BaseModel):
    sequence: str = Field(..., min_length=1, max_length=5000)
    peptide_id: str | None = None


class BatchPredictRequest(BaseModel):
    sequences: list[PredictRequest] = Field(..., min_length=1, max_length=1000)


class ToolResult(BaseModel):
    peptide_id: str
    sequence: str
    score: float = Field(..., ge=0.0, le=1.0)
    label: str
    details: dict[str, Any] = {}


class PredictResponse(BaseModel):
    success: bool
    peptide_id: str | None = None
    sequence: str | None = None
    result: ToolResult | None = None
    error: str | None = None


class BatchPredictResponse(BaseModel):
    success: bool
    results: list[ToolResult]
    total: int
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    tool_name: str
    version: str


class InfoResponse(BaseModel):
    tool_name: str
    version: str
    description: str
    capabilities: list[str]
    input_format: dict[str, str]
    output_format: dict[str, str]


# ─── Tool Service 基类 ────────────────────────────────────────────────

class BioToolService:
    """每个工具服务继承此类，实现 load_model() 和 predict_impl()"""

    tool_name: str = "template"
    version: str = "1.0.0"
    description: str = "Template bio tool service"

    def __init__(self):
        self.model = None
        self._lock = asyncio.Lock()

    async def load_model(self):
        """子类实现：加载模型权重（启动时调用一次）"""
        raise NotImplementedError

    async def predict_impl(self, sequence: str) -> ToolResult:
        """子类实现：核心预测逻辑"""
        raise NotImplementedError

    async def predict_single(self, request: PredictRequest) -> PredictResponse:
        """单序列预测入口（带并发控制）"""
        async with self._lock:
            try:
                result = await self.predict_impl(request.sequence)
                result.peptide_id = request.peptide_id or "unknown"
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
        """批量预测入口"""
        semaphore = asyncio.Semaphore(10)  # 限制并发量

        async def bounded_predict(item: PredictRequest) -> ToolResult | None:
            async with semaphore:
                try:
                    result = await self.predict_impl(item.sequence)
                    result.peptide_id = item.peptide_id or "unknown"
                    return result
                except Exception:
                    return None

        tasks = [bounded_predict(item) for item in request.sequences]
        results = await asyncio.gather(*tasks)

        valid_results = [r for r in results if r is not None]
        return BatchPredictResponse(
            success=True,
            results=valid_results,
            total=len(valid_results),
            error=None
        )


# ─── FastAPI 应用工厂 ─────────────────────────────────────────────────

def create_app(ToolClass: type[BioToolService]) -> FastAPI:
    """工厂函数：创建指定工具的 FastAPI 应用"""

    tool_instance = ToolClass()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动时加载模型
        await tool_instance.load_model()
        yield
        # 关闭时清理资源

    app = FastAPI(
        title=ToolClass.tool_name,
        description=ToolClass.description,
        version=ToolClass.version,
        lifespan=lifespan
    )

    @app.post("/predict", response_model=PredictResponse)
    async def predict(request: PredictRequest):
        return await tool_instance.predict_single(request)

    @app.post("/predict/batch", response_model=BatchPredictResponse)
    async def predict_batch(request: BatchPredictRequest):
        return await tool_instance.predict_batch(request)

    @app.get("/health", response_model=HealthResponse)
    async def health():
        return HealthResponse(
            status="healthy",
            tool_name=ToolClass.tool_name,
            version=ToolClass.version
        )

    @app.get("/info", response_model=InfoResponse)
    async def info():
        return InfoResponse(
            tool_name=ToolClass.tool_name,
            version=ToolClass.version,
            description=ToolClass.description,
            capabilities=["predict", "predict/batch"],
            input_format={"sequence": "string (amino acid sequence)"},
            output_format={"score": "float 0-1", "label": "string"}
        )

    return app


# ─── 启动脚本示例 ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # 示例：启动 AnOxPePred 服务
    # from services.anoxpepred.service import AnOxPePredService
    # app = create_app(AnOxPePredService)
    # uvicorn.run(app, host="0.0.0.0", port=8001)

    uvicorn.run(
        "services.template.tool_service:app",
        host="0.0.0.0",
        port=8001,
        reload=False
    )
```

### 3.2 Tool Registry（配置中心）

文件路径: `services/orchestrator/registry.py`

```python
"""
Tool Registry
============
系统的"配置中心"。Orchestrator 完全依赖它，不硬编码任何工具 URL。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ToolConfig:
    name: str                          # 工具唯一名称
    url: str                           # HTTP URL，例如 http://localhost:8001
    type: Literal[
        "toxicity", "antioxidant", "cpp", "mhc",
        "hemolytic", "bcell_epitope", "allergenicity",
        "tyrosinase_inhibitor", "general"
    ]                                  # 功能分类
    timeout: float = 30.0              # 超时秒数
    max_retries: int = 3               # 最大重试次数
    retry_delay: float = 1.0            # 重试间隔秒数
    batch_size: int = 50                # 推荐批量大小
    requires_gpu: bool = False          # 是否需要 GPU
    priority: int = 1                  # 优先级（1=最高）


# ─── 工具注册表 ────────────────────────────────────────────────────────

TOOL_REGISTRY: dict[str, ToolConfig] = {
    # ── P0 工具（抗氧化/毒性/溶血，融合引擎核心）───────────
    "anoxpepred": ToolConfig(
        name="anoxpepred",
        url="http://localhost:8001",
        type="antioxidant",
        timeout=60.0,
        priority=0
    ),
    "toxipred3": ToolConfig(
        name="toxipred3",
        url="http://localhost:8003",
        type="toxicity",
        timeout=30.0,
        priority=0
    ),
    "hemopi2": ToolConfig(
        name="hemopi2",
        url="http://localhost:8004",
        type="hemolytic",
        timeout=60.0,
        priority=0
    ),

    # ── P1 工具（MHC/递送/酪氨酸酶抑制/过敏原性）──────────
    "mhcflurry": ToolConfig(
        name="mhcflurry",
        url="http://localhost:8005",
        type="mhc",
        timeout=30.0,
        priority=1
    ),
    "plm4cpps": ToolConfig(
        name="plm4cpps",
        url="http://localhost:8006",
        type="cpp",
        timeout=120.0,
        requires_gpu=False,  # 使用 8M 模型，可 CPU 运行
        priority=1
    ),
    "tipred": ToolConfig(
        name="tipred",
        url="http://localhost:8007",
        type="tyrosinase_inhibitor",
        timeout=30.0,
        priority=1
    ),
    "algpred2": ToolConfig(
        name="algpred2",
        url="http://localhost:8008",
        type="allergenicity",
        timeout=30.0,
        priority=1
    ),

    # ── P2 工具（补充/备选）───────────────────────────────
    "bepipred3": ToolConfig(
        name="bepipred3",
        url="http://localhost:8002",
        type="bcell_epitope",
        timeout=180.0,
        requires_gpu=True,
        priority=2
    ),
    "graphcpp": ToolConfig(
        name="graphcpp",
        url="http://localhost:8009",
        type="cpp",
        timeout=60.0,
        requires_gpu=False,
        priority=2
    ),
    "mlcpp": ToolConfig(
        name="mlcpp",
        url="http://localhost:8010",
        type="cpp",
        timeout=30.0,
        priority=2
    ),
}


# ─── 工具查询辅助 ────────────────────────────────────────────────────

def get_tool(name: str) -> ToolConfig | None:
    return TOOL_REGISTRY.get(name)


def get_tools_by_type(tool_type: str) -> list[ToolConfig]:
    return [t for t in TOOL_REGISTRY.values() if t.type == tool_type]


def get_all_tools() -> dict[str, ToolConfig]:
    return TOOL_REGISTRY.copy()


def get_p0_tools() -> list[ToolConfig]:
    """获取 P0 优先级工具（融合引擎必须调用）"""
    return [t for t in TOOL_REGISTRY.values() if t.priority == 0]


def get_primary_cpp_tool() -> ToolConfig | None:
    """获取主 CPP 工具（优先级最高）"""
    cpp_tools = [t for t in TOOL_REGISTRY.values() if t.type == "cpp"]
    return min(cpp_tools, key=lambda t: t.priority) if cpp_tools else None
```

### 3.3 Orchestrator（调度核心）

文件路径: `services/orchestrator/core.py`

```python
"""
Orchestrator
============
调度核心：负责工具调用编排、并发执行、结果聚合。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .registry import TOOL_REGISTRY, ToolConfig


# ─── 数据模型 ──────────────────────────────────────────────────────────

@dataclass
class PredictionRequest:
    sequence: str
    peptide_id: str | None = None
    tools: list[str] | None = None  # None = 调用所有 P0 工具


@dataclass
class ToolResult:
    tool_name: str
    peptide_id: str
    sequence: str
    score: float | None = None
    label: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class FusionResult:
    peptide_id: str
    sequence: str
    tool_results: list[ToolResult]
    fused_score: float | None = None
    fused_label: str | None = None
    total_latency_ms: float = 0.0


# ─── Orchestrator 主类 ────────────────────────────────────────────────

class Orchestrator:
    """调度核心，支持 asyncio 并发执行和自动重试"""

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        concurrency: int = 5
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.semaphore = asyncio.Semaphore(concurrency)
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def call_tool(
        self,
        tool: ToolConfig,
        sequence: str,
        peptide_id: str | None = None
    ) -> ToolResult:
        """调用单个工具，支持超时和重试"""
        async with self.semaphore:
            client = await self._get_client()
            url = f"{tool.url}/predict"
            payload = {"sequence": sequence, "peptide_id": peptide_id}
            last_error = None

            for attempt in range(tool.max_retries if hasattr(tool, 'max_retries') else self.max_retries):
                try:
                    start = time.perf_counter()
                    response = await client.post(url, json=payload, timeout=tool.timeout)
                    latency_ms = (time.perf_counter() - start) * 1000

                    if response.status_code == 200:
                        data = response.json()
                        if data.get("success"):
                            result = data["result"]
                            return ToolResult(
                                tool_name=tool.name,
                                peptide_id=peptide_id or "unknown",
                                sequence=sequence,
                                score=result.get("score"),
                                label=result.get("label"),
                                details=result.get("details", {}),
                                latency_ms=latency_ms
                            )
                        else:
                            last_error = data.get("error", "Unknown error")
                    else:
                        last_error = f"HTTP {response.status_code}"

                except httpx.TimeoutException:
                    last_error = f"Timeout after {tool.timeout}s"
                except httpx.RequestError as e:
                    last_error = str(e)

                if attempt < self.max_retries - 1:
                    await asyncio.sleep(tool.retry_delay if hasattr(tool, 'retry_delay') else 1.0)

            return ToolResult(
                tool_name=tool.name,
                peptide_id=peptide_id or "unknown",
                sequence=sequence,
                error=last_error
            )

    async def predict_single(
        self,
        request: PredictionRequest,
        tools: list[str] | None = None
    ) -> FusionResult:
        """对单条序列执行多工具预测"""
        # 确定要调用的工具列表
        if request.tools:
            tool_configs = [TOOL_REGISTRY[t] for t in request.tools if t in TOOL_REGISTRY]
        else:
            # 默认调用所有 P0 工具
            tool_configs = [t for t in TOOL_REGISTRY.values() if t.priority == 0]

        # 并发调用所有工具
        start = time.perf_counter()
        tasks = [
            self.call_tool(tool, request.sequence, request.peptide_id)
            for tool in tool_configs
        ]
        tool_results = await asyncio.gather(*tasks)
        total_latency_ms = (time.perf_counter() - start) * 1000

        # 融合结果
        fused_score, fused_label = self._fuse_results(tool_results)

        return FusionResult(
            peptide_id=request.peptide_id or "unknown",
            sequence=request.sequence,
            tool_results=tool_results,
            fused_score=fused_score,
            fused_label=fused_label,
            total_latency_ms=total_latency_ms
        )

    async def predict_batch(
        self,
        requests: list[PredictionRequest],
        tools: list[str] | None = None
    ) -> list[FusionResult]:
        """批量预测（自动分批，避免并发爆炸）"""
        semaphore = asyncio.Semaphore(3)  # 限制同时处理的序列数

        async def bounded_predict(req: PredictionRequest) -> FusionResult:
            async with semaphore:
                return await self.predict_single(req, tools)

        tasks = [bounded_predict(req) for req in requests]
        return await asyncio.gather(*tasks)

    def _fuse_results(self, results: list[ToolResult]) -> tuple[float | None, str | None]:
        """
        融合评分策略
        ───────────
        默认策略：加权平均，权重与 priority 成反比

        后期可升级为：
        - ML 模型融合（训练数据积累后）
        - Pareto 最优筛选
        - 用户定义权重
        """
        valid_results = [r for r in results if r.error is None and r.score is not None]

        if not valid_results:
            return None, "no_valid_results"

        # 加权平均：priority 越小权重越高
        total_weight = sum(1.0 / (r.tool_name and TOOL_REGISTRY.get(r.tool_name, ToolConfig(name="", url="", type="general")).priority + 1) for r in valid_results)
        weighted_sum = sum(
            r.score * (1.0 / (TOOL_REGISTRY.get(r.tool_name, ToolConfig(name="", url="", type="general")).priority + 1))
            for r in valid_results
        )
        fused_score = weighted_sum / total_weight

        # 标签：少数服从多数
        labels = [r.label for r in valid_results if r.label]
        fused_label = max(set(labels), key=labels.count) if labels else "unknown"

        return fused_score, fused_label


# ─── CLI 入口 ─────────────────────────────────────────────────────────

async def main():
    orchestrator = Orchestrator()

    # 测试单条序列
    result = await orchestrator.predict_single(
        PredictionRequest(
            sequence="YVPLPNVPQG",
            peptide_id="test_pep_001"
        )
    )

    print(f"肽: {result.sequence}")
    print(f"融合分数: {result.fused_score:.3f}" if result.fused_score else "无分数")
    print(f"融合标签: {result.fused_label}")
    print(f"总延迟: {result.total_latency_ms:.0f}ms")
    print("\n各工具结果:")
    for tr in result.tool_results:
        status = "✅" if tr.error is None else "❌"
        print(f"  {status} {tr.tool_name}: score={tr.score}, label={tr.label}, latency={tr.latency_ms:.0f}ms")

    await orchestrator.close()


if __name__ == "__main__":
    asyncio.run(main())
```

### 3.4 Scoring Engine（融合评分）

文件路径: `services/orchestrator/scoring.py`

```python
"""
Scoring Engine
=============
多工具结果融合评分策略。

当前实现：加权平均 + 标签投票
后期升级路径：ML 模型融合、Pareto 最优
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .core import ToolResult, FusionResult


# ─── 评分权重配置 ────────────────────────────────────────────────────

# 每个工具的功能类型权重（数值越高 = 越重要）
TOOL_WEIGHTS = {
    # ── 核心功效工具 ──────────────────────────────
    "anoxpepred":   1.0,   # 抗氧化（核心功效）
    "toxipred3":    1.5,   # 毒性（安全门槛，必须低毒）
    "hemopi2":      1.5,   # 溶血（安全门槛，必须低溶血）
    "tipred":       1.0,   # 酪氨酸酶抑制（核心功效）

    # ── 安全性评估工具 ──────────────────────────
    "mhcflurry":    0.8,   # MHC 结合（免疫原性风险）
    "algpred2":     1.2,   # 过敏原性（安全门槛）
    "bepipred3":    0.5,   # B 细胞表位（免疫原性参考）

    # ── 递送相关工具 ──────────────────────────────
    "plm4cpps":     0.9,   # CPP 预测（递送潜力）
    "graphcpp":     0.7,   # CPP 预测（备选）
    "mlcpp":        0.5,   # CPP 预测（备选）
}


@dataclass
class ScoringConfig:
    """评分策略配置"""
    toxicity_penalty: float = 2.0       # 毒性分数 > 0.5 时的惩罚系数
    hemolytic_penalty: float = 2.0      # 溶血分数 > 0.5 时的惩罚系数
    allergenicity_penalty: float = 2.0  # 过敏原性分数 > 0.5 时的惩罚系数
    min_safety_score: float = 0.3      # 安全分数下限（低于此值直接淘汰）
    use_pareto: bool = False            # 是否使用 Pareto 最优筛选


def compute_fused_score(
    results: list[ToolResult],
    config: ScoringConfig | None = None
) -> tuple[float, str, dict[str, Any]]:
    """
    计算融合分数

    Returns:
        (fused_score, fused_label, details)
    """
    if config is None:
        config = ScoringConfig()

    valid_results = [r for r in results if r.error is None and r.score is not None]

    if not valid_results:
        return 0.0, "no_valid_results", {"error": "No valid tool results"}

    details = {}
    score_components = {}

    # 1. 计算各工具的加权分数
    for r in valid_results:
        tool_weight = TOOL_WEIGHTS.get(r.tool_name, 1.0)
        tool_config_key = r.tool_name  # 用于查找 penalty 配置
        score_components[r.tool_name] = {
            "raw_score": r.score,
            "weight": tool_weight,
            "weighted_score": r.score * tool_weight
        }

    # 2. 应用惩罚（毒性/溶血/过敏原性超标时）
    penalty_multiplier = 1.0
    penalty_reasons = []

    for r in valid_results:
        tool_name = r.tool_name
        score = r.score

        # 毒性惩罚
        if tool_name == "toxipred3" and score > 0.5:
            penalty = config.toxicity_penalty * (score - 0.5) * 2
            penalty_multiplier *= (1.0 - penalty)
            penalty_reasons.append(f"toxicity_penalty:{penalty:.2f}")

        # 溶血惩罚
        if tool_name == "hemopi2" and score > 0.5:
            penalty = config.hemolytic_penalty * (score - 0.5) * 2
            penalty_multiplier *= (1.0 - penalty)
            penalty_reasons.append(f"hemolytic_penalty:{penalty:.2f}")

        # 过敏原性惩罚
        if tool_name == "algpred2" and score > 0.5:
            penalty = config.allergenicity_penalty * (score - 0.5) * 2
            penalty_multiplier *= (1.0 - penalty)
            penalty_reasons.append(f"allergenicity_penalty:{penalty:.2f}")

    # 3. 加权平均
    total_weight = sum(score_components[r.tool_name]["weight"] for r in valid_results)
    weighted_sum = sum(score_components[r.tool_name]["weighted_score"] for r in valid_results)
    base_score = weighted_sum / total_weight

    # 4. 应用惩罚
    final_score = max(0.0, base_score * penalty_multiplier)

    # 5. 安全下限检查
    if final_score < config.min_safety_score:
        final_score = 0.0

    # 6. 标签投票
    labels = [r.label for r in valid_results if r.label]
    fused_label = max(set(labels), key=labels.count) if labels else "unknown"

    # 7. 详细信息
    details = {
        "base_score": round(base_score, 4),
        "penalty_multiplier": round(penalty_multiplier, 4),
        "penalty_reasons": penalty_reasons,
        "score_components": {k: {kk: round(vv, 4) for kk, vv in v.items()} for k, v in score_components.items()},
        "tool_count": len(valid_results)
    }

    return round(final_score, 4), fused_label, details


def rank_candidates(results: list[FusionResult], top_k: int = 50) -> list[FusionResult]:
    """对候选肽排序，取 top_k"""
    valid = [r for r in results if r.fused_score is not None]
    valid.sort(key=lambda x: x.fused_score, reverse=True)
    return valid[:top_k]
```

### 3.5 API 路由（FastAPI）

文件路径: `services/api/main.py`

```python
"""
Orchestrator API
================
对外暴露的统一 REST API。
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from orchestrator.core import Orchestrator, PredictionRequest, FusionResult
from orchestrator.scoring import compute_fused_score, rank_candidates


# ─── 请求/响应模型 ────────────────────────────────────────────────────

class SinglePredictRequest(BaseModel):
    sequence: str = Field(..., min_length=1, max_length=5000)
    peptide_id: str | None = None
    tools: list[str] | None = None  # None = 所有 P0 工具


class BatchPredictRequest(BaseModel):
    sequences: list[SinglePredictRequest] = Field(..., min_length=1, max_length=1000)
    tools: list[str] | None = None


class ToolResultResponse(BaseModel):
    tool_name: str
    score: float | None
    label: str | None
    latency_ms: float
    error: str | None


class FusionResultResponse(BaseModel):
    peptide_id: str
    sequence: str
    fused_score: float | None
    fused_label: str | None
    total_latency_ms: float
    tool_results: list[ToolResultResponse]


class BatchPredictResponse(BaseModel):
    success: bool
    total: int
    results: list[FusionResultResponse]


# ─── FastAPI 应用 ─────────────────────────────────────────────────────

app = FastAPI(title="iGEM-silk Orchestrator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator: Orchestrator | None = None


@app.on_event("startup")
async def startup():
    global orchestrator
    orchestrator = Orchestrator()


@app.on_event("shutdown")
async def shutdown():
    if orchestrator:
        await orchestrator.close()


@app.post("/predict", response_model=FusionResultResponse)
async def predict(request: SinglePredictRequest):
    """单条序列预测"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = await orchestrator.predict_single(
        PredictionRequest(
            sequence=request.sequence,
            peptide_id=request.peptide_id,
            tools=request.tools
        )
    )
    return _to_response(result)


@app.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch(request: BatchPredictRequest):
    """批量预测"""
    if not orchestrator:
        raise HTTPException(status_code=503, detail="Service not initialized")

    requests = [
        PredictionRequest(
            sequence=req.sequence,
            peptide_id=req.peptide_id
        )
        for req in request.sequences
    ]

    results = await orchestrator.predict_batch(requests, tools=request.tools)
    ranked = rank_candidates(results)

    return BatchPredictResponse(
        success=True,
        total=len(results),
        results=[_to_response(r) for r in ranked]
    )


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "orchestrator"}


@app.get("/tools")
async def list_tools():
    """列出所有可用工具"""
    from orchestrator.registry import TOOL_REGISTRY
    return {
        "tools": [
            {
                "name": name,
                "url": cfg.url,
                "type": cfg.type,
                "priority": cfg.priority,
                "requires_gpu": cfg.requires_gpu
            }
            for name, cfg in TOOL_REGISTRY.items()
        ]
    }


def _to_response(result: FusionResult) -> FusionResultResponse:
    return FusionResultResponse(
        peptide_id=result.peptide_id,
        sequence=result.sequence,
        fused_score=result.fused_score,
        fused_label=result.fused_label,
        total_latency_ms=result.total_latency_ms,
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
```

---

## 四、目录结构

```
iGEM-silk/
├── main.py                          # 主入口（CLI）
├── pyproject.toml                    # 项目依赖
├── services/
│   ├── api/
│   │   └── main.py                 # Orchestrator REST API
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── core.py                 # 调度核心（asyncio）
│   │   ├── registry.py              # 工具注册表
│   │   └── scoring.py              # 融合评分引擎
│   ├── template/
│   │   └── tool_service.py         # FastAPI 服务模板
│   └── tools/                      # 各工具服务实现
│       ├── anoxpepred/
│       │   └── service.py          # AnOxPePred 微服务
│       ├── toxipred3/
│       │   └── service.py          # ToxinPred3 微服务
│       ├── hemopi2/
│       │   └── service.py          # HemoPI2 微服务
│       ├── mhcflurry/
│       │   └── service.py          # MHCflurry 微服务
│       ├── plm4cpps/
│       │   └── service.py          # pLM4CPPs 微服务
│       ├── tipred/
│       │   └── service.py          # TIPred 微服务
│       ├── algpred2/
│       │   └── service.py          # AlgPred2 微服务
│       ├── bepipred3/
│       │   └── service.py          # BepiPred-3.0 微服务
│       ├── graphcpp/
│       │   └── service.py          # GraphCPP 微服务
│       └── mlcpp/
│           └── service.py          # MLCPP 微服务
├── scripts/
│   ├── start_orchestrator.sh      # 启动 Orchestrator
│   ├── start_all_tools.sh          # 启动所有工具服务
│   └── stop_all.sh                 # 停止所有服务
├── tests/
│   ├── test_orchestrator.py        # Orchestrator 单元测试
│   ├── test_scoring.py            # 融合评分测试
│   └── test_integration.py         # 集成测试
└── docker-compose.yml              # Docker 部署（如选择容器化）
```

---

## 五、部署指南

### 5.1 阶段一：本机多端口（立即可做）

**启动顺序：**
1. 启动工具服务（后台运行）
2. 启动 Orchestrator API
3. 使用 CLI 或 HTTP 客户端调用

**启动脚本：**

`scripts/start_all_tools.sh`:
```bash
#!/usr/bin/env bash
set -e

# 每个工具服务在独立终端或后台进程启动
# 这里用 & 后台运行，wait 阻塞等待所有子进程

echo "Starting Tool Services..."

# AnOxPePred :8001
echo "Starting AnOxPePred..."
cd tools/AnOxPePred
uv run uvicorn services.template.tool_service:app --port 8001 --host 0.0.0.0 &
ANOX_PID=$!

# ToxinPred3 :8003
echo "Starting ToxinPred3..."
cd tools/ToxinPred3
uv run uvicorn services.template.tool_service:app --port 8003 --host 0.0.0.0 &
TOXIN_PID=$!

# ... 其他工具类似

echo "All tool services started."
echo "PIDs: AnOxPePred=$ANOX_PID, ToxinPred3=$TOXIN_PID"
wait
```

`scripts/start_orchestrator.sh`:
```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
uv run uvicorn services.api.main:app --port 8000 --host 0.0.0.0 --reload
```

### 5.2 阶段二：Docker 容器化（推荐中期采用）

`docker-compose.yml`:
```yaml
version: '3.8'

services:
  orchestrator:
    build: ./services/api
    ports:
      - "8000:8000"
    depends_on:
      - anoxpepred
      - toxipred3
      - hemopi2
    restart: unless-stopped

  anoxpepred:
    build: ./services/tools/anoxpepred
    ports:
      - "8001:8001"
    deploy:
      resources:
        limits:
          memory: 2G

  toxipred3:
    build: ./services/tools/toxipred3
    ports:
      - "8003:8003"

  hemopi2:
    build: ./services/tools/hemopi2
    ports:
      - "8004:8004"
    deploy:
      resources:
        limits:
          memory: 4G
```

---

## 六、关键工程细节

### 6.1 超时控制

```python
# 每个工具配置独立超时
ANOX_PRED_CONFIG.timeout = 60.0   # ESM-2 模型较慢
TOXIN_PRED_CONFIG.timeout = 30.0  # sklearn 模型较快
```

### 6.2 错误隔离

```python
# 单个工具失败不影响其他工具
try:
    result = await call_tool(...)
except Exception:
    result = ToolResult(error=str(e))
# Orchestrator 继续处理其他工具
```

### 6.3 批处理优化

```python
# 单个请求不要发 1 条序列
# 要攒批后一起发，减少 HTTP 开销

# 推荐：50 条/批
TOOL_REGISTRY["anoxpepred"].batch_size = 50

# Orchestrator 自动分批
async def predict_batch(requests, batch_size=50):
    for i in range(0, len(requests), batch_size):
        batch = requests[i:i+batch_size]
        # 发送到工具服务的 /predict/batch 端点
```

### 6.4 并发限制

```python
# Orchestrator 限制总并发
self.semaphore = asyncio.Semaphore(5)

# 每个工具服务限制内部并发
semaphore = asyncio.Semaphore(10)
```

---

## 七、分阶段实施路线图

### 第 1 周：核心骨架

| 任务 | 产出 | 状态 |
|------|------|------|
| 实现 `tool_service.py` 模板 | 可复用的 FastAPI 基类 | ⬜ |
| 实现 `registry.py` | 配置中心代码 | ⬜ |
| 实现 3 个 P0 工具服务（AnOxPePred/ToxinPred3/HemoPI2） | 独立可运行的工具微服务 | ⬜ |
| 实现 `orchestrator/core.py` | 调度核心骨架 | ⬜ |
| 实现 `orchestrator/scoring.py` | 融合评分骨架 | ⬜ |
| 手动测试单个工具调用 | 验证链路通通 | ⬜ |

### 第 2 周：API 与集成

| 任务 | 产出 | 状态 |
|------|------|------|
| 实现 `api/main.py` | REST API | ⬜ |
| 实现剩余 7 个工具服务 | 完整工具矩阵 | ⬜ |
| CLI 入口 `main.py` | 统一的命令行接口 | ⬜ |
| 单元测试 | 覆盖核心逻辑 | ⬜ |
| 编写 `start_all_tools.sh` | 一键启动脚本 | ⬜ |

### 第 3 周：优化与文档

| 任务 | 产出 | 状态 |
|------|------|------|
| 批量处理优化 | 支持 100+ 序列/批 | ⬜ |
| 重试与错误处理 | 健壮性提升 | ⬜ |
| `docker-compose.yml` | 容器化部署 | ⬜ |
| 更新 `CONTEXT.md` | 反映新架构 | ⬜ |
| 集成测试 | 端到端验证 | ⬜ |

### 第 4 周及以后：生产化

| 任务 | 产出 | 状态 |
|------|------|------|
| GPU 调度（bepipred3/pLM4CPPs） | 加速重模型 | ⬜ |
| ML 融合评分（训练数据积累后） | 更精准的评分 | ⬜ |
| Pareto 最优筛选 | 多目标优化 | ⬜ |
| 前端 UI（Streamlit） | 可视化界面 | ⬜ |
| 性能压测 | 确认瓶颈与扩展性 | ⬜ |

---

## 八、实现检查清单（给下一个 AI）

在完成每个组件后，请在以下检查点验证：

### 工具服务实现检查

- [ ] 继承 `BioToolService` 基类
- [ ] 实现 `load_model()` 方法（启动时调用一次）
- [ ] 实现 `predict_impl()` 方法（核心预测逻辑）
- [ ] 实现了 `/predict`、`/predict/batch`、`/health`、`/info` 四个端点
- [ ] 服务可独立启动并响应健康检查
- [ ] 批量预测（50 条/批）延迟 < 单条 × 50

### Orchestrator 实现检查

- [ ] `TOOL_REGISTRY` 包含所有 10 个工具配置
- [ ] 单序列调用时，所有 P0 工具并发执行
- [ ] 单个工具失败不影响其他工具和最终结果
- [ ] 批量预测（100 条序列）全部返回结果

### Scoring Engine 实现检查

- [ ] 毒性/溶血/过敏原性超标时有惩罚机制
- [ ] 融合分数归一化到 0-1
- [ ] 标签采用多数投票

### API 实现检查

- [ ] `/predict` 单序列端点可调用
- [ ] `/predict/batch` 批量端点可调用
- [ ] `/tools` 端点返回所有工具列表
- [ ] 错误时返回有意义的错误信息

### 集成测试检查

- [ ] 启动所有工具服务后，Orchestrator 可正常调用
- [ ] 端到端：输入序列 → 调用 3+ 工具 → 返回融合结果
- [ ] 批量测试：100 条序列全部返回（允许部分失败但有记录）
