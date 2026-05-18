# API 规范手册

本系统微服务 API 设计沿————模板化、契约化。所有微服务遵循三种模板之一：
- **FASTA 服务**（序列→评分/分类）
- **PDB 服务**（PDB 结构→评分）
- **Structure 服务**（序列→3D 结构）

每个模板定义了一致的端点路径、请求/响应模型、错误处理和健康检查格式。

---

## 1. 通用约定

### 1.1 传输协议

| 项目 | 约定 |
|------|------|
| 协议 | HTTP/1.1 |
| Content-Type | `application/json` |
| 编码 | UTF-8 |
| 端口范围 | 评分 8001-8012, 安全过滤 8003-8008, 结构预测 8201-8205, PDB 评分 8101-8102 |
| 认证 | 无（内部网络，不对外暴露） |

### 1.2 状态码

| 状态码 | 含义 |
|--------|------|
| 200 | 成功（含业务错误如 `success: false`） |
| 202 | 异步任务已接受（仅 async 模式） |
| 422 | 请求体验证失败（字段缺失/类型错误） |
| 500 | 服务内部错误 |

### 1.3 公共端点

```http
GET /health   → HealthResponse
GET /info     → InfoResponse
```

#### HealthResponse

```json
{
  "status": "healthy",
  "tool_name": "anoxpepred",
  "version": "1.1.0",
  "model_loaded": true,
  "model": {
    "status": "ready",
    "model_mode": "cnn",
    "backend": "gpu"
  },
  "system": {
    "device": "gpu",
    "gpu_available": true,
    "gpu_name": "NVIDIA RTX 5880 Ada Generation",
    "gpu_memory": "47 GB"
  }
}
```

`status` 取值：`"healthy"`（可用）、`"loading"`（模型加载中，短暂状态）。

#### InfoResponse

```json
{
  "tool_name": "anoxpepred",
  "description": "Antioxidant peptide prediction",
  "version": "1.1.0",
  "capabilities": ["score", "classify"],
  "recommended_batch_size": 50,
  "model_type": "cnn",
  "backend": "gpu"
}
```

`recommended_batch_size` 是服务端的推荐上限，客户端不应超过此值。

---

## 2. FASTA 服务模板

适用于：AnOxPePred、BepiPred3、ToxinPred3、HemoPI2、MHCflurry、AlgPred2、pLM4CPPs、TIPred、GraphCPP、TemStaPro、SoDoPE。

### 2.1 端点

```http
POST /predict          # 单条预测
POST /predict/batch    # 批量预测
```

### 2.2 请求格式

#### 单条：`POST /predict`

```json
{
  "sequence": "YVPLPNVPQG",
  "peptide_id": "pep_001"
}
```

| 字段 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸单字母序列，1-5000 aa |
| `peptide_id` | string | 否 | 标识符，默认 `"unknown"` |

#### 批量：`POST /predict/batch`

```json
{
  "sequences": [
    {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"},
    {"sequence": "CYVPLPNVPQ", "peptide_id": "pep_002"}
  ]
}
```

| 字段 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `sequences` | array | 是 | 1-1000 条序列 |

**⚠️ 批量请求 payload 键名是 `sequences`（不是 `requests`）**。这是 FASTA 模板与 PDB 模板的关键区别。

### 2.3 单条响应

```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "peptide_id": "pep_001",
    "sequence": "YVPLPNVPQG",
    "score": 0.8732,
    "label": "antioxidant",
    "details": {
      "frs_score": 0.8732,
      "chel_score": 0.4418,
      "confidence": 0.9983,
      "is_antioxidant": true
    }
  },
  "error": null
}
```

| 顶层字段 | 类型 | 说明 |
|----------|------|------|
| `success` | bool | 是否成功。**注意**：即使 `success: true`，`result` 仍可能为 null（服务无错误但无法评分） |
| `peptide_id` | string | 请求传入的标识符 |
| `sequence` | string | 原始请求序列 |
| `result` | object|null | 评分结果。失败时为 null |
| `error` | string|null | 错误信息 |

#### result 对象

| 字段 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `peptide_id` | string | 否 | 默认 `"unknown"` |
| `sequence` | string | 否 | 回显原始序列 |
| `score` | float | **是** | 0-1 主评分 |
| `label` | string | **是** | 分类标签，取值因服务而异 |
| `details` | dict | 是（可为空） | 服务特定的附加信息 |

### 2.4 批量响应

```json
{
  "success": true,
  "results": [
    {
      "peptide_id": "pep_001",
      "sequence": "YVPLPNVPQG",
      "score": 0.8732,
      "label": "antioxidant",
      "details": {}
    },
    {
      "peptide_id": "pep_002",
      "sequence": "CYVPLPNVPQ",
      "score": 0.2341,
      "label": "non-antioxidant",
      "details": {}
    }
  ],
  "total": 2,
  "error": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否成功 |
| `results` | array | result 对象数组。**注意**：与单条不同，批量结果没有 `result` 嵌套层，`score`/`label` 直接在顶层 |
| `total` | int | 成功评分的数量。若 `< 输入长度`，则有部分失败 |
| `error` | string|null | 全局错误信息 |

**⚠️ 批量响应中没有 `result` 嵌套**。直接读 `results[0].score`，不是 `results[0].result.score`。

### 2.5 `label` 取值对照

| 服务 | label 可能值 |
|------|-------------|
| AnOxPePred | `"antioxidant"`, `"non-antioxidant"` |
| ToxinPred3 | `"Toxin"`, `"Non-Toxin"` |
| HemoPI2 | `"hemolytic"`, `"non-hemolytic"` |
| MHCflurry | `"binder"`, `"non-binder"` |
| AlgPred2 | `"Allergen"`, `"Non-Allergen"` |
| BepiPred3 | `"epitope"`, `"non-epitope"` |
| TemStaPro | `"stable"`, `"unstable"` |
| SoDoPE | `"soluble"`, `"insoluble"` |
| pLM4CPPs | `"CPP"`, `"non-CPP"` |
| GraphCPP | `"CPP"`, `"non-CPP"` |
| TIPred | `"inhibitor"`, `"non-inhibitor"` |

### 2.6 服务端默认配置

```python
recommended_batch_size = 50  # 服务端建议的批量大小上限
semaphore = asyncio.Semaphore(10)  # 服务端并发限制（可被子类覆盖）
```

---

## 3. PDB 服务模板

适用于：SASA、Aggrescan3D。

### 3.1 端点

```http
POST /predict          # 单条 PDB 评分
POST /predict/batch    # 批量 PDB 评分
```

### 3.2 请求格式

#### 单条：`POST /predict`

```json
{
  "pdb_content": "ATOM      1  N   ASP A   0     -23.404   9.271  13.678  1.00 18.04           N  \nATOM      2  CA ...",
  "sequence": "YVPLPNVPQG",
  "chain_id": "A",
  "peptide_id": "con_001"
}
```

| 字段 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `pdb_content` | string | **是** | PDB 格式全文 |
| `sequence` | string | 否（但 SASA 需要） | 功能肽序列，用于在 PDB 中定位 |
| `chain_id` | string | 否 | 目标链，默认 `"A"` |
| `peptide_id` | string | 否 | 标识符，默认 `"unknown"` |

**⚠️ SASA 不传 `sequence` 会返回 score=0**。见 quirks.md 第 2 条。

#### 批量：`POST /predict/batch`

```json
{
  "requests": [
    {
      "pdb_content": "ATOM      1  N   ...",
      "sequence": "YVPLPNVPQG",
      "peptide_id": "con_001"
    },
    {
      "pdb_content": "ATOM      1  N   ...",
      "sequence": "DNWWPKPPH",
      "peptide_id": "con_002"
    }
  ]
}
```

**⚠️ 批量请求 payload 键名是 `requests`（不是 `sequences`）**。这是 PDB 模板与 FASTA 模板的关键区别。

### 3.3 批量响应格式（与单条不同！）

#### 单条：`POST /predict`

```json
{
  "success": true,
  "peptide_id": "con_001",
  "result": {
    "peptide_id": "con_001",
    "score": 0.7638,
    "label": "exposed",
    "details": {
      "chain": "A",
      "peptide": {
        "mean_relative_sasa": 0.7638,
        "num_residues": 10,
        "num_exposed": 8
      }
    }
  },
  "error": null
}
```

#### 批量：`POST /predict/batch`

```json
{
  "success": true,
  "results": [
    {
      "peptide_id": "con_001",
      "score": 0.7638,
      "label": "exposed",
      "details": {...}
    }
  ],
  "total": 2,
  "error": null
}
```

| 对比点 | 单条 | 批量 |
|--------|------|------|
| score 位置 | `result.score` | `results[].score`（无 result 嵌套） |
| 字段结构 | success/peptide_id/result/error | success/results/total/error |

解析时统一用 `r.get("score")` 处理批量结果。

### 3.4 PDB 服务的 details 结构

#### SASA

```json
{
  "chain": "A",
  "probe_radius": 1.4,
  "exposure_threshold": 0.25,
  "peptide": {
    "sequence": "YVPLPNVPQG",
    "num_residues": 10,
    "num_exposed": 6,
    "total_sasa": 452.3,
    "mean_relative_sasa": 0.7638,
    "exposure_ratio": 0.6,
    "residue_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "residues": [
      {"residue_id": 1, "residue_name": "TYR", "residue_code": "Y", "sasa": 45.2, "relative_sasa": 0.82, "is_exposed": true},
      ...
    ]
  },
  "all_residues": [...]
}
```

#### Aggrescan3D

```json
{
  "risk_score": 0.31,
  "statistics": {
    "num_residues": 372,
    "min_score": -1.24,
    "max_score": 0.89,
    "avg_score": 0.31,
    "positive_fraction": 0.28,
    "positive_mean": 0.52
  },
  "top_hotspots": [
    {"chain": "A", "residue_id": 145, "residue_name": "VAL", "score": 0.89}
  ],
  "residues": [
    {"protein": "silk", "chain": "A", "residue_id": 1, "residue_name": "ASP", "a3d_score": -0.45, "is_aggregation_prone": false},
    ...
  ],
  "output_pdb_content": "ATOM ...",
  "aggrescan3d": {
    "conda_env": "aggrescan3d",
    "distance_cutoff": 5.0
  }
}
```

---

## 4. Structure 服务模板

适用于：ESMFold、OmegaFold、AlphaFold3、PEP-FOLD4、Waveflow。

### 4.1 端点

#### 同步模式（ESMFold、OmegaFold、PEP-FOLD4）

```http
POST /predict          # 单条结构预测
POST /predict/batch    # 批量结构预测
```

#### 异步 Job 模式（AlphaFold3，其他可选）

```http
POST /predict/async          # 提交任务 → 返回 job_id (202)
GET  /status/{job_id}        # 查询任务状态
GET  /result/{job_id}        # 获取任务结果
GET  /status                 # 所有运行中任务
GET  /jobs                   # 所有历史任务
DELETE /jobs/{job_id}        # 删除任务
```

#### Waveflow 独有

```http
POST /predict/{tool}         # tool = esmfold | omegafold | alphafold
POST /predict/batch/{tool}
POST /predict/async/{tool}
```

### 4.2 请求格式

#### 单条：`POST /predict`

```json
{
  "sequence": "YVPLPNVPQG",
  "peptide_id": "pep_001"
}
```

与 FASTA 模板相同的 PredictRequest。

#### 批量：`POST /predict/batch`

```json
{
  "sequences": [
    {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}
  ]
}
```

与 FASTA 模板相同的 BatchPredictRequest。

#### 异步提交：`POST /predict/async`

```json
{
  "sequence": "YVPLPNVPQG",
  "peptide_id": "pep_001"
}
```

响应 202：

```json
{
  "job_id": "abc123def456",
  "status_url": "/status/abc123def456",
  "status": "pending"
}
```

### 4.3 响应格式

#### 单条同步响应

```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "peptide_id": "pep_001",
    "sequence": "YVPLPNVPQG",
    "pdb_content": "ATOM      1  N   ...",
    "confidence": 0.8732,
    "details": {
      "mean_plddt": 0.8732,
      "sequence_length": 10,
      "model_version": "v1.0",
      "device": "cuda"
    }
  },
  "error": null
}
```

#### 批量同步响应

```json
{
  "success": true,
  "results": [
    {
      "peptide_id": "pep_001",
      "sequence": "YVPLPNVPQG",
      "pdb_content": "ATOM ...",
      "confidence": 0.8732,
      "details": {}
    }
  ],
  "total": 1,
  "error": null
}
```

#### 异步状态查询：`GET /status/{job_id}`

```json
{
  "job_id": "abc123def456",
  "status": "running",
  "progress": "3/5",
  "created_at": 1716012345.67,
  "finished_at": null
}
```

`status` 取值：`"pending"` → `"running"` → `"success"` | `"failed"`

#### 异步结果获取：`GET /result/{job_id}`

```json
{
  "job_id": "abc123def456",
  "sequence": "YVPLPNVPQG",
  "status": "success",
  "pdb_content": "ATOM ...",
  "confidence": 0.8732,
  "details": {},
  "error": null
}
```

### 4.4 PDB 文件保存建议

- 每条序列一个 PDB 文件，以 `{peptide_id}.pdb` 命名
- 每组预测存放在 `output4/pdb/{peptide_id}/` 目录
- 保留原始 B-factor 列（OmegaFold 用 confidence×100 填充）

### 4.5 各 Structure 服务的 `details` 字段

| 服务 | details 字段 | 说明 |
|------|-------------|------|
| OmegaFold | `mean_plddt`, `sequence_length`, `model_version`, `num_cycle`, `device` | pLDDT=confidence |
| ESMFold | `mean_plddt`, `ptm_score`, `sequence_length` | pTM 是全局折叠置信度 |
| AlphaFold3 | `mean_plddt`, `ptm_score`, `iptm_score`, `full_pae`(矩阵), `model_version` | PAE 矩阵可能非常大 |
| PEP-FOLD4 | `sequence_length` | 限 5-40 aa |
| Waveflow | `tool_type`, `job_name`, `elapsed_seconds`, `sequence_length` | 远程 API 耗时 |

---

## 5. 批量调用指导

### 5.1 每服务推荐配置速查

| 服务 | 类型 | 每批条数 | 并发数 | 超时(s) | GPU/CPU |
|------|------|----------|--------|---------|---------|
| AnOxPePred | fasta | 1000 | 10 | 120 | GPU |
| AlgPred2 | fasta | 1000 | 10 | 120 | CPU |
| ToxinPred3 | fasta | **1** | **2** | 180 | CPU |
| HemoPI2 | fasta | 100 | 10 | 180 | GPU |
| MHCflurry | fasta | 100 | 10 | 180 | GPU |
| BepiPred3 | fasta | 1000 | 5 | 300 | GPU |
| TemStaPro | fasta | 1000 | 5 | 300 | GPU |
| SoDoPE | fasta | 1000 | 10 | 300 | CPU |
| pLM4CPPs | fasta | 100 | 5 | 300 | GPU |
| GraphCPP | fasta | 100 | 5 | 300 | GPU |
| SASA | pdb | 50 | 10 | 300 | CPU |
| Aggrescan3D | pdb | 50 | **2** | 300 | CPU |
| OmegaFold | structure | **1** | **1** | 14400 | GPU |
| ESMFold | structure | 5 | 3 | 600 | GPU |
| AlphaFold3 | structure | 1 | 1 | 14400 | GPU |
| PEP-FOLD4 | structure | 1 | 3 | 1800 | CPU |
| Waveflow | structure | 5 | 3 | 3600 | CPU(远程) |

### 5.2 并发控制要点

```
toxinpred3: Semaphore(2), batch_size=1   ← sklearn 线程不安全
omegafold:  Semaphore(1), batch_size=1   ← 阻塞事件循环
aggrescan3d: Semaphore(2)                ← Docker 子进程开销大
temstapro:  Semaphore(5)                 ← GPU OOM 风险
```

其他 FASTA 服务可用 `Semaphore(10)` + `batch_size=1000`。

### 5.3 客户端代码模式

```python
from main.client import ServiceClient

client = ServiceClient(timeout=120.0)

# FASTA 评分
result = await client.predict_batch("anoxpepred", items)
# items = [{"peptide_id": "1", "sequence": "YVPL..."}, ...]
# result["results"][0]["score"]

# PDB 评分
result = await client.predict_pdb_batch("sasa", items)
# items = [{"peptide_id": "1", "pdb_content": "ATOM...", "sequence": "YVPL..."}]
# result["results"][0]["score"]  ← 注意：score 在顶层

# 结构预测（同步）
result = await client.predict_structure_sync("omegafold", items)
# items = [{"peptide_id": "1", "sequence": "YVPL..."}]
# result["results"][0]["pdb_content"]

# 结构预测（异步）
result = await client.predict_structure_async("alphafold3", sequence)
```

---

## 6. 错误处理契约

### 6.1 业务错误 vs HTTP 错误

- **HTTP 4xx/5xx**：网络层或框架层错误（请求体格式错误、服务内部错误）
- **HTTP 200 + `success: false`**：业务层错误（模型未加载、序列太长、PDB 解析失败）

所有业务逻辑错误都在 JSON body 内通过 `success` 和 `error` 字段表达。

### 6.2 部分失败

批量请求中个别序列可能失败。此时：
- `success: true`（整体请求成功）
- `total < 输入长度`（部分失败的数量）
- 失败项的 `details` 可能包含 `error` 字段
- 失败项的 `score` 为 `null`

```json
{
  "success": true,
  "results": [
    {"peptide_id": "1", "score": 0.87, "details": {}},
    {"peptide_id": "2", "score": null, "details": {"error": "Sequence too long: 6001 > 5000"}}
  ],
  "total": 1,
  "error": null
}
```

### 6.3 健康检查降级

`GET /health` 可能返回以下 `status`：

| status | 含义 | 处理方式 |
|--------|------|----------|
| `"healthy"` | 服务可用，模型已加载 | 正常调用 |
| `"loading"` | 模型正在加载（首次启动或重启后） | 等待后重试 |
| `"degraded"` | 服务部分可用（如模型文件缺失，使用规则回退） | AnOxPePred 特有，调用正常但精度降低 |

---

## 7. 各服务 `label` + `score` 含义矩阵

| 服务 | score 含义 | 范围 | label 语义 |
|------|-----------|------|-----------|
| AnOxPePred | 抗氧化概率 | 0-1 | antioxidant / non-antioxidant |
| ToxinPred3 | 毒性概率 | 0-1 | Toxin / Non-Toxin |
| HemoPI2 | 溶血概率 | 0-1 | hemolytic / non-hemolytic |
| MHCflurry | 结合概率 | 0-1 | binder / non-binder |
| AlgPred2 | 致敏概率 | 0-1 | Allergen / Non-Allergen |
| BepiPred3 | 表位概率 | 0-1 | epitope / non-epitope |
| TemStaPro | 稳定性分数 | 0-1 | stable / unstable |
| SoDoPE | 溶解度概率 | 0-1 | soluble / insoluble |
| pLM4CPPs | CPP 概率 | 0-1 | CPP / non-CPP |
| GraphCPP | CPP 概率 | 0-1 | CPP / non-CPP |
| TIPred | 抑制概率 | 0-1 | inhibitor / non-inhibitor |
| SASA | 平均相对 SASA | 0-1 | exposed / partial / buried / no_target |
| Aggrescan3D | 聚集风险 | 0-1 | high/moderate/low_aggregation_risk |
| OmegaFold | 无 | 无（`confidence` 是 pLDDT） | 无（结构质量用 pLDDT 表示） |
| ESMFold | 无 | 无（`confidence` 是 pLDDT） | 无 |

---

## 8. 快速检索

参见 `services.json` 获得机器可读格式的完整服务配置（端口、batch、并发、阈值、known details keys）。
