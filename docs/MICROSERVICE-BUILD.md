# 微服务开发指南

> **版本**: v1.0.0
> **状态**: 可执行
> **目的**: 指导开发者快速创建符合标准的工具微服务
> **最后更新**: 2026-05-06

---

## 一、概述

本文档定义了在 `services/tools/` 目录下开发新工具微服务的**接口标准**和**数据标准**。所有工具服务必须遵循这些规范，以确保与 Orchestrator 的无缝对接。

### 1.1 快速开始

```bash
# 1. 创建工具目录
mkdir -p services/tools/mytool/

# 2. 继承 BioToolService 实现核心逻辑
# 3. 注册路由并创建 FastAPI 应用
# 4. 在 registry.py 中添加配置
```

---

## 二、接口标准

### 2.1 必须实现的接口

每个工具微服务**必须**实现以下 HTTP 接口：

| 方法 | 路径 | 描述 | Content-Type |
|------|------|------|-------------|
| GET | `/` | 服务根路径，返回基本信息 | - |
| POST | `/predict` | 单序列预测 | `application/json` |
| POST | `/predict/batch` | 批量预测 | `application/json` |
| GET | `/health` | 健康检查 | - |
| GET | `/info` | 工具信息 | - |

### 2.2 接口详细规范

#### GET /

返回服务基本信息。

**响应格式:**
```json
{
  "service": "anoxpepred",
  "version": "1.1.0",
  "docs": "/docs"
}
```

#### POST /predict

单序列预测接口。

**请求格式:**
```json
{
  "sequence": "YVPLPNVPQG",
  "peptide_id": "pep_001"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sequence` | string | ✅ | 氨基酸序列，长度 1-5000 |
| `peptide_id` | string | ❌ | 肽 ID，不提供则为 `"unknown"` |

**响应格式:**
```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "peptide_id": "pep_001",
    "sequence": "YVPLPNVPQG",
    "score": 0.82,
    "label": "antioxidant",
    "details": {
      "confidence": 0.95,
      "method": "CNN"
    }
  },
  "error": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | boolean | 是否成功 |
| `peptide_id` | string | 肽 ID |
| `sequence` | string | 原始序列 |
| `result` | object | 预测结果，失败时为 `null` |
| `error` | string | 错误信息，成功时为 `null` |

**result 字段详情:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `peptide_id` | string | ✅ | 肽 ID |
| `sequence` | string | ✅ | 原始序列 |
| `score` | float | ✅ | 预测分数，范围 0.0-1.0 |
| `label` | string | ✅ | 预测标签 |
| `details` | object | ❌ | 附加信息，如置信度、预测方法等 |

#### POST /predict/batch

批量预测接口。

**请求格式:**
```json
{
  "sequences": [
    {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"},
    {"sequence": "AVPQVFPG", "peptide_id": "pep_002"}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sequences` | array | ✅ | 序列列表，最多 1000 条 |

**响应格式:**
```json
{
  "success": true,
  "results": [
    {
      "peptide_id": "pep_001",
      "sequence": "YVPLPNVPQG",
      "score": 0.82,
      "label": "antioxidant",
      "details": {}
    },
    {
      "peptide_id": "pep_002",
      "sequence": "AVPQVFPG",
      "score": 0.45,
      "label": "non-antioxidant",
      "details": {}
    }
  ],
  "total": 2,
  "error": null
}
```

#### GET /health

健康检查接口。Orchestrator 会定期调用此接口检查服务状态。

**响应格式:**
```json
{
  "status": "healthy",
  "tool_name": "anoxpepred",
  "version": "1.1.0",
  "model_loaded": true
}
```

| 字段 | 类型 | 说明 |
|------|------|------|------|
| `status` | string | 状态：`healthy`（正常）或 `loading`（模型加载中） |
| `tool_name` | string | 工具名称 |
| `version` | string | 版本号 |
| `model_loaded` | boolean | 模型是否已加载 |

#### GET /info

工具信息接口。

**响应格式:**
```json
{
  "tool_name": "anoxpepred",
  "version": "1.1.0",
  "description": "抗氧化肽预测工具（AnOxPePred, TensorFlow CNN）",
  "capabilities": ["predict", "predict/batch"],
  "input_format": {
    "sequence": "string (amino acid sequence, length 1-5000)"
  },
  "output_format": {
    "score": "float (0.0-1.0, higher is better for antioxidant)",
    "label": "string (antioxidant or non-antioxidant)"
  },
  "recommended_batch_size": 50
}
```

---

## 三、数据标准

### 3.1 输入数据标准

#### 3.1.1 氨基酸序列

- **格式**: 字符串，仅包含标准氨基酸字母
- **允许字符**: `ACDEFGHIKLMNPQRSTVWY`（20 种标准氨基酸）
- **长度限制**: 1-5000 个氨基酸
- **大小写**: 不敏感（建议统一大写处理）

```python
# 示例
sequence = "YVPLPNVPQG"  # 正确
sequence = "YVPLPNVPQGX"  # 包含未知字符 X，可能被拒绝
```

#### 3.1.2 肽 ID

- **格式**: 字符串
- **限制**: 最多 255 个字符
- **默认值**: `"unknown"`

### 3.2 输出数据标准

#### 3.2.1 分数 (score)

| 类型 | 范围 | 说明 |
|------|------|------|
| 回归 | 0.0-1.0 | 预测值直接作为分数 |
| 二分类 | 0.0-1.0 | 属于正类的概率 |
| 多分类 | 0.0-1.0 | 各类概率之和为 1.0 |

**分数语义约定:**

| 工具类型 | 分数含义 | 说明 |
|----------|----------|------|
| 抗氧化 (antioxidant) | 越高越好 | 1.0 = 最强抗氧化 |
| 毒性 (toxicity) | 越低越好 | 0.0 = 无毒 |
| 溶血 (hemolytic) | 越低越好 | 0.0 = 不溶血 |
| 过敏原性 (allergenicity) | 越低越好 | 0.0 = 不过敏 |
| 细胞穿膜 (cpp) | 越高越好 | 1.0 = 最容易穿膜 |
| 酪氨酸酶抑制 (tyrosinase_inhibitor) | 越高越好 | 1.0 = 最强抑制 |
| MHC 结合 | 越高越好 | 1.0 = 最强结合 |

#### 3.2.2 标签 (label)

标签应准确反映预测结果，推荐格式：

| 工具类型 | 推荐标签 |
|----------|----------|
| 抗氧化 | `antioxidant`, `non-antioxidant` |
| 毒性 | `toxic`, `non-toxic` |
| 溶血 | `hemolytic`, `non-hemolytic` |
| 过敏原性 | `allergen`, `non-allergen` |
| 细胞穿膜 | `cpp`, `non-cpp` |
| 酪氨酸酶抑制 | `tyrosinase_inhibitor`, `non-inhibitor` |
| B 细胞表位 | `epitope`, `non-epitope` |

#### 3.2.3 details（附加信息）

可选字段，用于返回额外信息。推荐包含：

```json
{
  "confidence": 0.95,
  "method": "CNN",
  "features": {
    "hydrophobicity": 0.72,
    "charge": 0.15
  }
}
```

### 3.3 错误处理标准

#### 3.3.1 成功响应

```json
{
  "success": true,
  "result": {...},
  "error": null
}
```

#### 3.3.2 失败响应

```json
{
  "success": false,
  "result": null,
  "error": "Invalid sequence: contains unknown amino acid 'X'"
}
```

#### 3.3.3 HTTP 状态码

| 状态码 | 场景 |
|--------|------|
| 200 | 请求成功（无论 success 是 true 还是 false） |
| 400 | 请求格式错误（如 JSON 解析失败） |
| 422 | 请求数据验证失败（如 sequence 为空） |
| 500 | 服务器内部错误（如模型加载失败） |

---

## 四、开发模板

### 4.1 最小实现示例

```python
# services/tools/mytool/service.py

from services.template.tool_service import (
    create_app,
    BioToolService,
    ToolResult,
)


class MyToolService(BioToolService):
    """我的自定义工具"""

    tool_name = "mytool"
    version = "1.0.0"
    description = "我的自定义工具服务"
    recommended_batch_size = 50

    async def load_model(self):
        """加载模型权重"""
        # TODO: 在这里加载你的模型
        # self.model = load_my_model("path/to/model")
        pass

    async def predict_impl(self, sequence: str) -> ToolResult:
        """执行预测逻辑"""
        # TODO: 在这里实现预测
        # score = self.model.predict(sequence)[0]

        score = 0.5  # 示例
        return ToolResult(
            score=float(score),
            label="active" if score > 0.5 else "inactive",
            details={"confidence": 0.95}
        )


app = create_app(MyToolService)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8011)
```

### 4.2 完整实现示例（带模型加载）

```python
# services/tools/anoxpepred/service.py

import os
from services.template.tool_service import (
    create_app,
    BioToolService,
    ToolResult,
)


class AnOxPePredService(BioToolService):
    """AnOxPePred 抗氧化肽预测服务"""

    tool_name = "anoxpepred"
    version = "1.1.0"
    description = "抗氧化肽预测工具（AnOxPePred, TensorFlow CNN）"
    recommended_batch_size = 50

    def __init__(self):
        super().__init__()
        self._model = None

    async def load_model(self):
        """加载 TensorFlow 模型"""
        import tensorflow as tf

        model_path = os.environ.get(
            "ANOXPE_MODEL_PATH",
            "/models/anoxpepred/model.h5"
        )
        self._model = tf.keras.models.load_model(model_path)

    async def predict_impl(self, sequence: str) -> ToolResult:
        """执行预测"""
        import numpy as np

        # 预处理序列
        features = self._preprocess(sequence.upper())

        # 预测
        prediction = self._model.predict(features, verbose=0)[0][0]

        # 构建结果
        return ToolResult(
            score=float(prediction),
            label="antioxidant" if prediction > 0.5 else "non-antioxidant",
            details={
                "confidence": abs(prediction - 0.5) * 2,
                "raw_output": float(prediction)
            }
        )

    def _preprocess(self, sequence: str) -> np.ndarray:
        """序列预处理"""
        import numpy as np

        # 氨基酸编码
        AA_MAP = "ACDEFGHIKLMNPQRSTVWY"
        seq_array = np.array([AA_MAP.index(aa) for aa in sequence if aa in AA_MAP])

        # 填充或截断到固定长度
        max_len = 50
        if len(seq_array) < max_len:
            seq_array = np.pad(seq_array, (0, max_len - len(seq_array)))
        else:
            seq_array = seq_array[:max_len]

        # One-hot 编码
        one_hot = np.zeros((max_len, 20))
        one_hot[np.arange(max_len), seq_array] = 1

        return one_hot.reshape(1, max_len, 20)


app = create_app(AnOxPePredService)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
```

---

## 五、配置注册

### 5.1 在 Registry 中注册

编辑 `services/orchestrator/registry.py`，添加 `ToolConfig`:

```python
TOOL_REGISTRY: dict[str, ToolConfig] = {
    # ... 现有工具 ...

    # 新工具
    "mytool": ToolConfig(
        name="mytool",
        url="http://localhost:8011",  # 新分配的端口
        type="general",  # 或具体类型：toxicity, antioxidant, cpp 等
        timeout=30.0,
        priority=1,  # 0=P0, 1=P1, 2=P2
        description="我的自定义工具",
    ),
}
```

### 5.2 分配端口

参考 `docs/MICROSERVICE-ARCHITECTURE.md` 中的端口分配表，确保新工具使用未占用的端口。

### 5.3 配置权重（如需）

如果工具需要参与融合评分，在 `services/orchestrator/scoring.py` 中添加权重:

```python
TOOL_WEIGHTS: dict[str, float] = {
    # ... 现有权重 ...
    "mytool": 1.0,  # 根据工具重要性设置
}
```

---

## 六、测试验证

### 6.1 本地测试

```bash
# 启动服务
python -m services.tools.mytool.service

# 测试健康检查
curl http://localhost:8011/health

# 测试单序列预测
curl -X POST http://localhost:8011/predict \
  -H "Content-Type: application/json" \
  -d '{"sequence": "YVPLPNVPQG"}'

# 测试批量预测
curl -X POST http://localhost:8011/predict/batch \
  -H "Content-Type: application/json" \
  -d '{"sequences": [{"sequence": "YVPLPNVPQG"}, {"sequence": "AVPQVFPG"}]}'
```

### 6.2 集成测试

```bash
# 测试与 Orchestrator 的集成
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"sequence": "YVPLPNVPQG", "tools": ["mytool"]}'
```

### 6.3 验证清单

- [ ] `/` 返回正确的基本信息
- [ ] `/health` 返回 `model_loaded: true`
- [ ] `/predict` 对有效序列返回 `success: true`
- [ ] `/predict` 对无效序列返回 `success: false` 并有清晰错误信息
- [ ] `/predict/batch` 正确处理多条序列
- [ ] `/info` 返回完整的工具信息
- [ ] score 在 0.0-1.0 范围内
- [ ] label 是推荐的标签格式
- [ ] 响应时间在 timeout 限制内

---

## 七、最佳实践

### 7.1 模型加载

```python
async def load_model(self):
    """使用懒加载 + 锁，防止并发重复加载"""
    import asyncio

    if self._model is None:
        async with self._lock:
            if self._model is None:  # 双重检查
                self._model = await self._load_model_async()
```

### 7.2 并发控制

```python
async def predict_impl(self, sequence: str) -> ToolResult:
    """使用信号量限制并发"""
    async with self._semaphore:
        return await self._do_predict(sequence)
```

### 7.3 错误处理

```python
async def predict_impl(self, sequence: str) -> ToolResult:
    try:
        score = self._model.predict(sequence)
        return ToolResult(score=score, label=...)
    except ValueError as e:
        raise ValueError(f"Invalid sequence: {e}")
    except Exception as e:
        raise RuntimeError(f"Prediction failed: {e}")
```

### 7.4 日志记录

```python
import logging

logger = logging.getLogger(__name__)

async def load_model(self):
    logger.info("Loading model from %s", model_path)
    self._model = load_model(model_path)
    logger.info("Model loaded successfully")
```

---

## 八、部署

### 8.1 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `TOOL_PORT` | 服务端口 | `8011` |
| `TOOL_HOST` | 监听地址 | `0.0.0.0` |
| `MODEL_PATH` | 模型文件路径 | `/models/mytool/model.h5` |

### 8.2 启动命令

```bash
# 使用模板直接启动
TOOL_CLASS=services.tools.mytool.service:MyToolService \
MODEL_PATH=/models/mytool/model.h5 \
uvicorn services.template.tool_service:app --port 8011 --host 0.0.0.0

# 或直接运行服务文件
python -m services.tools.mytool.service
```

### 8.3 Docker 化（待实现）

```dockerfile
# services/tools/mytool/Dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY services/tools/mytool/ /app/
RUN pip install fastapi uvicorn tensorflow
CMD ["python", "-m", "services.tools.mytool.service"]
```

---

## 九、 Checklist

新建工具微服务时，确保完成以下步骤：

- [ ] 在 `services/tools/` 下创建目录
- [ ] 实现 `load_model()` 方法
- [ ] 实现 `predict_impl()` 方法
- [ ] 配置 `tool_name`, `version`, `description`
- [ ] 在 `registry.py` 中添加 `ToolConfig`
- [ ] 分配并使用未占用的端口
- [ ] 在端口分配表中记录
- [ ] 通过所有测试验证
- [ ] 更新 `docs/MICROSERVICE-ARCHITECTURE.md`
