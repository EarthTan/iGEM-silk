# iGEM-silk 微服务架构设计文档

> **版本**: v1.0.0
> **状态**: 完整设计，可执行
> **目的**: 为下一个 AI 实现者提供详细的架构蓝图与可执行代码
> **最后更新**: 2026-05-06

---

## 一、项目现状与架构目标

### 1.1 现状盘点

| 维度 | 当前状态 |
|------|----------|
| **工具数量** | 10 个独立工具，已全部安装并验证 |
| **环境管理** | 各工具独立 `.venv`，无统一编排层 |
| **Python 版本** | 各工具不一致（3.10/3.11/3.12/3.13） |
| **项目阶段** | 探索期，未进入工程实现 |

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

### 2.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              客户端 / 前端                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     API Gateway (FastAPI, Port 8000)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   /predict  │  │  /predict/ │  │   /status  │  │   /tools    │         │
│  │             │  │    batch   │  │            │  │            │         │
│  └──────┬──────┘  └──────┬──────┘  └─────────────┘  └─────────────┘         │
└─────────┼────────────────┼──────────────────────────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Orchestrator (调度中心)                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  PredictionRequest                                                     │   │
│  │    - sequence: str           # 氨基酸序列                              │   │
│  │    - peptide_id: str         # 肽 ID                                  │   │
│  │    - tools: list[str] | None # 要调用的工具列表，None = 默认 P0       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                     │                                        │
│         ┌──────────────────────────┼──────────────────────────┐            │
│         ▼                          ▼                          ▼            │
│  ┌─────────────┐           ┌─────────────┐           ┌─────────────┐        │
│  │  Scoring    │           │  Registry   │           │   HTTP      │        │
│  │  Engine     │           │  (配置中心)  │           │   Client    │        │
│  └─────────────┘           └─────────────┘           └─────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
          │                                                            │
          │  并发调用 (asyncio.gather)                                 │
          ▼                                                            ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  anoxpepred      │  │  toxipred3       │  │  hemopi2         │  │  ...其他工具     │
│  (Port 8001)     │  │  (Port 8003)     │  │  (Port 8004)     │  │  (Port 8005-8010)│
│                  │  │                  │  │                  │  │                  │
│  P0 (必须调用)   │  │  P0 (必须调用)   │  │  P0 (必须调用)   │  │  P1 / P2         │
└──────────────────┘  └──────────────────┘  └──────────────────┘  └──────────────────┘
```

### 2.2 端口分配表

| 服务 | 端口 | 模型重量 | 建议实例数 | 优先级 |
|------|------|----------|------------|--------|
| **orchestrator (API)** | 8000 | - | 1 | - |
| AnOxPePred | 8001 | ⭐⭐ | 1 | P0 |
| BepiPred-3.0 | 8002 | ⭐⭐⭐ | 1 | P2 |
| ToxinPred3 | 8003 | ⭐ | 2 | P0 |
| HemoPI2 | 8004 | ⭐⭐ | 1 | P0 |
| MHCflurry | 8005 | ⭐⭐ | 1 | P1 |
| pLM4CPPs | 8006 | ⭐⭐⭐ | 1 | P1 |
| TIPred | 8007 | ⭐ | 2 | P1 |
| AlgPred2 | 8008 | ⭐ | 2 | P1 |
| GraphCPP | 8009 | ⭐⭐⭐ | 1 | P2 |
| MLCPP | 8010 | ⭐ | 2 | P2 |

### 2.3 目录结构

```
services/
├── __init__.py                    # 导出核心类和数据结构
│
├── orchestrator/                  # 调度中心（核心）
│   ├── __init__.py
│   ├── core.py                    # Orchestrator 主类、核心数据结构
│   ├── registry.py                # 工具注册表、ToolConfig 定义
│   └── scoring.py                 # 评分引擎、融合算法
│
├── api/                           # REST API 服务
│   ├── __init__.py
│   ├── main.py                    # 启动入口
│   ├── app.py                     # FastAPI 应用配置
│   ├── prediction/
│   │   ├── routes.py              # /predict, /predict/batch
│   │   ├── models.py
│   │   └── converters.py
│   ├── tools/
│   │   ├── routes.py              # /tools 路由
│   │   └── models.py
│   ├── status/
│   │   ├── routes.py              # /status 路由
│   │   └── models.py
│   └── root/
│       └── routes.py              # / 路由
│
├── template/                      # 工具服务模板
│   ├── __init__.py
│   └── tool_service.py            # BioToolService 基类、create_app 工厂
│
└── tools/                         # 具体工具实现
    └── anoxpepred/
        └── service.py             # AnOxPePred 服务示例
```

---

## 三、组件详细设计

### 3.1 Orchestrator（调度中心）

**文件位置**: `services/orchestrator/core.py`

#### 3.1.1 核心数据结构

```python
@dataclass
class PredictionRequest:
    sequence: str                    # 氨基酸序列
    peptide_id: str | None = None    # 肽 ID，默认 "unknown"
    tools: list[str] | None = None  # None = 默认 P0

@dataclass
class ToolResult:
    tool_name: str                   # 工具名称
    peptide_id: str                  # 肽 ID
    sequence: str                    # 原始序列
    score: float | None = None      # 预测分数 (0-1)
    label: str | None = None        # 预测标签
    details: dict = {}               # 附加信息
    latency_ms: float = 0.0          # 调用耗时
    error: str | None = None         # 错误信息

@dataclass
class FusionResult:
    peptide_id: str                  # 肽 ID
    sequence: str                    # 原始序列
    tool_results: list[ToolResult]   # 各工具原始结果
    fused_score: float | None = None # 融合分数
    fused_label: str | None = None   # 融合标签
    total_latency_ms: float = 0.0   # 总耗时
    scoring_details: dict | None = None  # 评分详情
```

#### 3.1.2 核心流程

```
用户请求 (PredictionRequest)
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│ Orchestrator.predict_single()                                   │
│                                                                 │
│  Step 1: 确定要调用的工具                                        │
│    - request.tools 有值 → 使用指定的工具                         │
│    - request.tools 为 None → 使用默认 P0 (anoxpepred, toxipred3, hemopi2)│
└────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│ Step 2: 并发调用所有工具 (asyncio.gather)                       │
│                                                                 │
│   asyncio.gather(                                              │
│       call_tool(anoxpepred, sequence),                         │
│       call_tool(toxipred3, sequence),                          │
│       call_tool(hemopi2, sequence),                            │
│   )                                                             │
│                                                                 │
│   工具服务返回 PredictResponse:                                  │
│   {                                                             │
│       "success": true,                                         │
│       "result": {"score": 0.82, "label": "antioxidant"},       │
│       "error": null                                            │
│   }                                                             │
└────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────┐
│ Step 3: 计算融合分数 (Scoring Engine)                            │
│   compute_fused_score(tool_results) → (fused_score, label)    │
└────────────────────────────────────────────────────────────────┘
         │
         ▼
      FusionResult
```

#### 3.1.3 并发调用机制

```python
async def call_tool(self, tool: ToolConfig, sequence: str, peptide_id: str) -> ToolResult:
    """
    1. 获取信号量（限制并发数，默认最多 5 个并发请求）
    2. 获取 HTTP 客户端
    3. 发送 POST 请求到 {tool.url}/predict
    4. 如果失败，自动重试（最多 max_retries 次，指数退避）
    5. 解析响应，返回 ToolResult
    """
    async with self._semaphore:  # 并发控制
        client = await self._get_client()
        response = await client.post(
            f"{tool.url}/predict",
            json={"sequence": sequence, "peptide_id": peptide_id},
            timeout=tool.timeout
        )
        # 解析响应，构建 ToolResult...
```

### 3.2 Registry（工具注册表）

**文件位置**: `services/orchestrator/registry.py`

#### 3.2.1 ToolConfig 定义

```python
@dataclass
class ToolConfig:
    name: str              # 唯一标识符，如 "anoxpepred"
    url: str               # HTTP 地址，如 "http://localhost:8001"
    type: Literal[         # 工具类型，用于评分引擎
        "toxicity", "antioxidant", "cpp", "mhc",
        "hemolytic", "bcell_epitope", "allergenicity",
        "tyrosinase_inhibitor", "general"
    ]
    timeout: float = 30.0           # 超时时间（秒）
    max_retries: int = 3            # 最大重试次数
    retry_delay: float = 1.0        # 重试间隔（秒）
    batch_size: int = 50            # 推荐批量大小
    requires_gpu: bool = False      # 是否需要 GPU
    priority: int = 1               # 优先级：0=P0, 1=P1, 2=P2
    description: str = ""           # 描述
```

#### 3.2.2 预配置工具

```python
TOOL_REGISTRY: dict[str, ToolConfig] = {
    "anoxpepred": ToolConfig(
        name="anoxpepred",
        url="http://localhost:8001",
        type="antioxidant",
        timeout=60.0,
        priority=0,  # P0
        description="抗氧化肽预测（AnOxPePred, TensorFlow CNN）",
    ),
    "toxipred3": ToolConfig(
        name="toxipred3",
        url="http://localhost:8003",
        type="toxicity",
        timeout=30.0,
        priority=0,  # P0
        description="肽毒性预测（ToxinPred3, Extra Trees + MERCI）",
    ),
    "hemopi2": ToolConfig(
        name="hemopi2",
        url="http://localhost:8004",
        type="hemolytic",
        timeout=60.0,
        priority=0,  # P0
        description="肽溶血性预测（HemoPI2, RF/ESM-2）",
    ),
    # ... P1, P2 工具
}
```

### 3.3 Scoring Engine（评分引擎）

**文件位置**: `services/orchestrator/scoring.py`

#### 3.3.1 工具权重配置

```python
TOOL_WEIGHTS: dict[str, float] = {
    # 核心功效工具（权重 = 1.0）
    "anoxpepred": 1.0,    # 抗氧化
    "tipred": 1.0,        # 酪氨酸酶抑制

    # 安全性工具（权重更高，安全第一）
    "toxipred3": 1.5,     # 毒性
    "hemopi2": 1.5,      # 溶血
    "algpred2": 1.3,     # 过敏原性

    # 辅助工具（权重较低）
    "mhcflurry": 0.8,     # MHC 结合
    "bepipred3": 0.5,     # B 细胞表位
    "plm4cpps": 0.9,      # 细胞穿膜肽
}
```

#### 3.3.2 融合算法

```python
def compute_fused_score(results: list[ToolResult]) -> tuple[float, str, dict]:
    """
    计算流程:

    Step 1: 过滤无效结果（error != None 或 score is None）

    Step 2: 计算加权分数
        weighted_score = raw_score × weight

    Step 3: 计算基础融合分数
        base_score = Σ(weighted_score) / Σ(weight)

    Step 4: 应用安全性惩罚
        如果 toxipred3 > 0.5（阈值）:
            penalty = toxicity_penalty × excess × 2
            multiplier *= max(0, 1 - penalty)
        同理 hemopi2, algpred2

    Step 5: 计算最终分数
        final_score = max(0, base_score × multiplier)
        如果 final_score < 0.2（安全下限），设为 0.0

    Step 6: 标签多数投票
        统计各标签出现次数，返回最多的

    返回: (fused_score, fused_label, scoring_details)
    """
```

#### 3.3.3 惩罚机制示例

```
假设 toxipred3 预测分数 = 0.7（超过 0.5 阈值）:
    excess = 0.7 - 0.5 = 0.2
    penalty = 2.0 × 0.2 × 2 = 0.8
    multiplier = max(0, 1 - 0.8) = 0.2

最终分数 = base_score × 0.2（打 2 折！）

如果 toxipred3 和 hemopi2 同时超标:
    整体乘数 = 0.2 × 0.2 = 0.04（只有 4%！）
```

### 3.4 API 服务

**文件位置**: `services/api/`

#### 3.4.1 启动入口

```python
# services/api/main.py
from .app import app
from .prediction import routes as _pred_routes
from .tools import routes as _tools_routes
from .status import routes as _status_routes
from .root import routes as _root_routes

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

#### 3.4.2 生命周期管理

```python
# services/api/app.py
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: 初始化 Orchestrator
    state.orchestrator = Orchestrator()
    yield
    # shutdown: 释放资源
    await state.orchestrator.close()
```

#### 3.4.3 API 路由

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/predict` | 单序列预测 |
| POST | `/predict/batch` | 批量预测 |
| GET | `/status` | 系统状态 |
| GET | `/tools` | 工具列表 |
| GET | `/tools/{name}` | 特定工具详情 |
| GET | `/health` | 健康检查 |
| GET | `/` | 根路径 |

### 3.5 工具服务模板

**文件位置**: `services/template/tool_service.py`

#### 3.5.1 创建新工具的步骤

```python
from services.template.tool_service import (
    create_app, BioToolService, ToolResult,
    PredictRequest, PredictResponse
)

class MyToolService(BioToolService):
    tool_name = "mytool"              # 工具名称
    version = "1.0.0"                # 版本号
    description = "我的自定义工具"    # 描述
    recommended_batch_size = 50      # 推荐批量大小

    async def load_model(self):
        # 加载模型权重
        self.model = load_my_model()

    async def predict_impl(self, sequence: str) -> ToolResult:
        # 执行预测逻辑
        score = self.model.predict(sequence)[0]
        return ToolResult(
            score=float(score),
            label="active" if score > 0.5 else "inactive"
        )

# 创建应用
app = create_app(MyToolService)

# 启动
# uvicorn services.mytool.service:app --port 8001 --host 0.0.0.0
```

#### 3.5.2 统一接口

| 方法 | 路径 | 请求格式 | 响应格式 |
|------|------|----------|----------|
| POST | `/predict` | `{"sequence": "...", "peptide_id": "..."}` | `{"success": true, "result": {...}, "error": null}` |
| POST | `/predict/batch` | `{"sequences": [...]}` | `{"success": true, "results": [...], "total": N}` |
| GET | `/health` | - | `{"status": "healthy", "model_loaded": true}` |
| GET | `/info` | - | `{"tool_name": "...", "capabilities": [...]}` |

---

## 四、API 接口详解

### 4.1 预测接口

#### POST /predict

**单序列预测**

```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}'
```

**响应示例:**
```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "fused_score": 0.73,
  "fused_label": "antioxidant",
  "tool_results": [
    {"tool_name": "anoxpepred", "score": 0.82, "label": "antioxidant", "latency_ms": 125.5},
    {"tool_name": "toxipred3", "score": 0.15, "label": "non-toxic", "latency_ms": 89.3},
    {"tool_name": "hemopi2", "score": 0.22, "label": "non-hemolytic", "latency_ms": 156.2}
  ],
  "total_latency_ms": 371.0,
  "scoring_details": {
    "base_score": 0.82,
    "penalty_multiplier": 1.0,
    "penalty_reasons": [],
    "score_components": {...}
  }
}
```

#### POST /predict/batch

**批量预测**

```bash
curl -X POST http://localhost:8000/predict/batch \
  -H "Content-Type: application/json" \
  -d '{
    "sequences": [
      {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"},
      {"sequence": "AVPQVFPG", "peptide_id": "pep_002"}
    ]
  }'
```

### 4.2 工具管理接口

#### GET /tools

**获取所有可用工具**

```bash
curl http://localhost:8000/tools
```

**响应示例:**
```json
{
  "tools": [
    {"name": "anoxpepred", "type": "antioxidant", "priority": 0, "url": "http://localhost:8001"},
    {"name": "toxipred3", "type": "toxicity", "priority": 0, "url": "http://localhost:8003"},
    ...
  ],
  "total": 10
}
```

### 4.3 状态接口

#### GET /status

**获取系统状态**

```bash
curl http://localhost:8000/status
```

**响应示例:**
```json
{
  "status": "operational",
  "orchestrator": {"status": "ready"},
  "tools": {
    "anoxpepred": {"status": "healthy", "latency_ms": 125.5},
    "toxipred3": {"status": "healthy", "latency_ms": 89.3},
    ...
  }
}
```

---

## 五、评分融合策略

### 5.1 设计原则

1. **安全性优先**: 毒性、溶血、过敏原超标时，分数大幅降低
2. **功效为基**: 抗氧化等核心功效作为基础分数
3. **权重分级**: 不同工具的重要性通过权重体现
4. **透明可解释**: 每一步计算都记录在 scoring_details 中

### 5.2 优先级策略

| 优先级 | 工具 | 调用策略 |
|--------|------|----------|
| **P0** | anoxpepred, toxipred3, hemopi2 | 必须调用，失败则预测不完整 |
| **P1** | mhcflurry, plm4cpps, tipred, algpred2 | 推荐调用，失败可降级 |
| **P2** | bepipred3, graphcpp, mlcpp | 可选，用于增强评估 |

### 5.3 安全阈值

| 指标 | 阈值 | 超过阈值处理 |
|------|------|-------------|
| 毒性 (toxipred3) | 0.5 | 分数打折 |
| 溶血 (hemopi2) | 0.5 | 分数打折 |
| 过敏原性 (algpred2) | 0.5 | 分数打折 |
| 最终分数下限 | 0.2 | 直接淘汰 (设为 0.0) |

---

## 六、部署指南

### 6.1 环境要求

- Python 3.10+
- uv 包管理器
- 各工具独立虚拟环境

### 6.2 启动顺序

```bash
# 1. 启动各工具服务（按优先级）
TOOL_CLASS=services.tools.anoxpepred.service:AnOxPePredService \
  uvicorn services.template.tool_service:app --port 8001 &

TOOL_CLASS=services.tools.toxipred3.service:ToxinPred3Service \
  uvicorn services.template.tool_service:app --port 8003 &

# ... 其他工具

# 2. 启动 Orchestrator API
cd services/api && uvicorn main:app --host 0.0.0.0 --port 8000
```

### 6.3 Docker 部署（待实现）

```dockerfile
# Dockerfile.orchestrator
FROM python:3.13-slim
WORKDIR /app
COPY services/ /app/services/
RUN pip install fastapi uvicorn httpx
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 七、扩展指南

### 7.1 添加新工具

1. 在 `services/tools/` 下创建新目录
2. 继承 `BioToolService` 实现 `load_model()` 和 `predict_impl()`
3. 在 `services/orchestrator/registry.py` 中添加 `ToolConfig`
4. 在 `services/orchestrator/scoring.py` 中配置权重
5. 分配新端口，更新文档

### 7.2 自定义评分策略

```python
from services.orchestrator.scoring import ScoringConfig

# 创建更严格的配置
strict_config = ScoringConfig(
    toxicity_penalty=3.0,    # 更重的毒性惩罚
    min_safety_score=0.3    # 更高的安全下限
)

# 使用自定义配置
result = await orchestrator.predict_single(request, scoring_config=strict_config)
```

---

## 八、故障排查

### 8.1 常见问题

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 连接被拒绝 | 工具服务未启动 | 检查端口是否监听 |
| 超时 | 模型加载慢/服务器负载高 | 增加 timeout 或重试 |
| 分数为 None | 工具返回错误 | 检查工具日志 |
| 分数异常低 | 安全性惩罚触发 | 检查 scoring_details |

### 8.2 健康检查

```bash
# 检查所有工具
curl http://localhost:8000/status | jq '.tools[] | select(.status != "healthy")'

# 检查特定工具
curl http://localhost:8001/health
```
