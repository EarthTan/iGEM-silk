# 微服务输入输出与调用方法

本文档列出所有微服务的输入输出格式、参数、返回值及调用方式。

---

## 目录

- [统一 API 契约](#统一-api-契约)
- [一、Fasta 序列评分服务](#一fasta-序列评分服务)
  - [1.1 AnOxPePred — 抗氧化肽预测](#11-anoxpepred-抗氧化肽预测)
  - [1.2 BepiPred-3.0 — B 细胞表位预测](#12-bepipred-30--b-细胞表位预测)
  - [1.3 ToxinPred3 — 毒性预测](#13-toxinpred3-毒性预测)
  - [1.4 HemoPI2 — 溶血性预测](#14-hemopi2-溶血性预测)
  - [1.5 MHCflurry — MHC-I 结合亲和力预测](#15-mhcflurry--mhc-i-结合亲和力预测)
  - [1.6 pLM4CPPs — 细胞穿膜肽预测 (ESM-2)](#16-plm4cpps-细胞穿膜肽预测-esm-2)
  - [1.7 TIPred — 酪氨酸酶抑制肽预测](#17-tipred-酪氨酸酶抑制肽预测)
  - [1.8 AlgPred2 — 过敏原性预测](#18-algpred2-过敏原性预测)
  - [1.9 GraphCPP — 细胞穿膜肽预测 (GNN)](#19-graphcpp-细胞穿膜肽预测-gnn)
  - [1.10 TemStaPro — 热稳定性预测](#110-temstapro-热稳定性预测)
  - [1.11 SoDoPE — 溶解度预测](#111-sodope-溶解度预测)
- [二、结构预测服务](#二结构预测服务)
  - [2.1 AlphaFold3 — 3D 生物分子结构预测](#21-alphafold3--3d-生物分子结构预测)
  - [2.2 PEP-FOLD4 — 肽从头结构预测](#22-pep-fold4-肽从头结构预测)
- [三、PDB 结构评分服务](#三pdb-结构评分服务)
  - [3.1 SASA — 溶剂可及表面积分析](#31-sasa-溶剂可及表面积分析)
  - [3.2 Aggrescan3D — 结构聚集倾向分析](#32-aggrescan3d-结构聚集倾向分析)
- [四、流水线调用流程](#四流水线调用流程)

---

## 统一 API 契约

所有微服务均通过 HTTP (FastAPI) 暴露，共享以下通用端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 服务基本信息 |
| `/health` | GET | 健康检查，返回模型加载状态 |
| `/info` | GET | 工具详细信息（输入输出格式、推荐批量大小） |
| `/predict` | POST | 单次预测 |
| `/predict/batch` | POST | 批量预测（内部并发控制） |

### 通用响应格式

所有 Fasta 评分服务返回统一的 `ToolResult`：

```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "score": 0.82,
    "label": "Antioxidant",
    "details": { ... }
  },
  "error": null
}
```

字段说明：
- `score` (float, 0–1)：统一评分。不同服务的分数含义不同，详见各服务说明。
- `label` (string)：分类标签。各服务的标签值不同。
- `details` (dict)：服务特定的详细信息。

---

## 一、Fasta 序列评分服务

Fasta 服务基类：`tools/template/fasta_service.py` → `FastaToolService`

**通用输入格式**：氨基酸序列字符串（单字母大写），无额外参数。

### 1.1 AnOxPePred — 抗氧化肽预测

| 属性 | 值 |
|------|-----|
| 端口 | 8001 |
| 分组 | score |
| 环境 | GPU/CPU (TensorFlow CNN) |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，>30 aa 自动截断至 30（中肽模式） |

无额外参数。CNN 输入形状 `(1, 30, 20)`，不足 30 残基居中以 `X` 补齐。

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | 综合抗氧化评分 = 0.6 × FRS + 0.4 × CHEL |
| `label` | string | `"Antioxidant"` (score ≥ 0.5) 或 `"Non-antioxidant"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `frs_score` | float | 自由基清除评分 (0–1) |
| `chel_score` | float | 金属螯合评分 (0–1) |
| `confidence` | string | `"high"` / `"medium"` / `"low"` / `"very_low"` |
| `is_antioxidant` | bool | 二分类结果 |
| `model_mode` | string | `"cnn"` (正常) 或 `"rule"` (回退规则) |

#### 调用示例

```python
# 单序列
POST http://127.0.0.1:8001/predict
{"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}

# 批量
POST http://127.0.0.1:8001/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}, {"sequence": "KELEEK"}]}
```

#### 注意事项

- 该模型训练于短肽 (2–30 aa)，长度超过 30 会截断。
- CNN 模型按原论文实现，输出 FRS 和 CHEL 两个独立评分，最终以加权平均作为综合评分。

---

### 1.2 BepiPred-3.0 — B 细胞表位预测

| 属性 | 值 |
|------|-----|
| 端口 | 8002 |
| 分组 | score |
| 环境 | GPU/CPU (ESM-2 t33, 2.5 GB) |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，≥5 aa，≤5000 aa |

无额外参数。内部使用 ESM-2 t33 (650M) + 滑动窗口 (size=7) 集成分数。

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | 所有残基、所有集成模型上的平均表位概率 |
| `label` | string | `"Epitope"` (score ≥ 0.1512) 或 `"Non-epitope"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `average_epitope_score` | float | 同 score |
| `max_epitope_score` | float | 单残基最高预测值 |
| `max_linear_epitope_score` | float | 窗口滑动平均最高值 |
| `threshold` | float | 0.1512（原论文阈值） |
| `num_residues_predicted` | int | 预测的残基总数 |
| `model` | string | `"ESM-2 + DenseNet Ensemble"` |

#### 调用示例

```python
POST http://127.0.0.1:8002/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}]}
```

#### 注意事项

- 阈值 0.1512 来自原论文，是精准度/召回率平衡的最优点。
- 在本项目中作为"表面暴露度代理指标"：B 细胞表位区域通常在折叠后暴露于蛋白表面。
- 模型较大 (~2.5 GB)，首次启动时自动下载。

---

### 1.3 ToxinPred3 — 毒性预测

| 属性 | 值 |
|------|-----|
| 端口 | 8003 |
| 分组 | filter（一票否决） |
| 环境 | CPU (ExtraTrees + 420维特征) |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，无长度限制 |

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | 毒性概率 |
| `label` | string | `"Toxin"` (score ≥ 0.38) 或 `"Non-Toxin"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `threshold` | float | 0.38 |
| `model` | string | `"ExtraTreesClassifier (Model 1: AAC+DPC)"` |

#### 调用示例

```python
POST http://127.0.0.1:8003/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 阈值 0.38：流水线中 ≥ 0.38 直接淘汰（硬过滤，一票否决）。
- 使用 AAC（氨基酸组成）+ DPC（二肽组成）共 420 维特征，Extra Trees 分类器。

---

### 1.4 HemoPI2 — 溶血性预测

| 属性 | 值 |
|------|-----|
| 端口 | 8004 |
| 分组 | filter（一票否决） |
| 环境 | GPU/CPU (ESM-2 t6 微调, 30 MB) |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，>40 aa 自动截断至 40 |

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | 溶血性概率 (softmax class 1) |
| `label` | string | `"Hemolytic"` (score ≥ 0.55) 或 `"Non-Hemolytic"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `threshold` | float | 0.55 |
| `model` | string | `"ESM-2 t6 (Model 3)"` |
| `device` | string | 运行设备 (`"cuda"` / `"cpu"` / `"mps"`) |

#### 调用示例

```python
POST http://127.0.0.1:8004/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 阈值 0.55：流水线中 ≥ 0.55 直接淘汰（硬过滤）。
- 基于 ESM-2 t6 (8M) 微调，ESM 输入限制 40 残基，超长序列截断。

---

### 1.5 MHCflurry — MHC-I 结合亲和力预测

| 属性 | 值 |
|------|-----|
| 端口 | 8005 |
| 分组 | score（反向指标） |
| 环境 | GPU/CPU |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，长度 8–15 aa (MHC-I 限制) |

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | 结合力评分（高 = 结合强 = 免疫原性风险高） |
| `label` | string | `"Strong Binder"` / `"Weak Binder"` / `"Non-Binder"` |

score 从 IC50 (nM) 换算：

| IC50 区间 | label | score |
|-----------|-------|-------|
| ≤ 50 nM | Strong Binder | 0.5 + (1 − affinity/50) × 0.5 |
| 50–500 nM | Weak Binder | 0.25 + (1 − (affinity−50)/450) × 0.25 |
| > 500 nM | Non-Binder | 0 + max(0, 0.25 − affinity/5000 × 0.25) |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `affinity_nM` | float | 原始 IC50 值 (nM) |
| `allele` | string | `"HLA-A*02:01"` (固定等位基因) |

#### 调用示例

```python
POST http://127.0.0.1:8005/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 固定使用 `HLA-A*02:01` 等位基因。如需其他等位基因需修改服务代码。
- MHC-I 肽长度限制 8–15 aa，超出范围结果不可靠。
- 在流水线中设为反向指标 (`SCORE_INVERT`)：评分时取 `1.0 − score`，即结合越弱越优。

---

### 1.6 pLM4CPPs — 细胞穿膜肽预测 (ESM-2)

| 属性 | 值 |
|------|-----|
| 端口 | 8006 |
| 分组 | score |
| 环境 | GPU/CPU (ESM-2 t6 + CNN) |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，≥5 aa |

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | CPP 概率 |
| `label` | string | `"CPP"` (score ≥ 0.15) 或 `"non-CPP"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `threshold` | float | 0.15（MCC 最优阈值） |
| `model_type` | string | `"ESM2-320_CNN"` |

#### 调用示例

```python
POST http://127.0.0.1:8006/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 阈值 0.15 是原论文在 KELM 外部数据集上调优的 MCC 最优阈值。
- < 5 aa 返回 `score=0.0, label="non-CPP"`。

---

### 1.7 TIPred — 酪氨酸酶抑制肽预测

| 属性 | 值 |
|------|-----|
| 端口 | 8007 |
| 分组 | score |
| 环境 | CPU（启动时合成训练，无需模型文件） |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，≥3 aa，无上限 |

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | TIP 概率 |
| `label` | string | `"TIP"` (score ≥ 0.5) 或 `"non-TIP"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `threshold` | float | 0.5 |
| `model_type` | string | `"Stacked-Ensemble-547d"` |

#### 调用示例

```python
POST http://127.0.0.1:8007/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 使用 7 种特征编码器 (AAC/DPC/APAAC/PAAC/CTDC/CTDT/CTDD, 547 维) + Stacked Ensemble (KNN + RF + SVM + GB → LR)。
- 首次启动时从 benchmark 数据集合成训练，无需预下载模型。
- 这是抗黑色素沉积的核心功能指标。

---

### 1.8 AlgPred2 — 过敏原性预测

| 属性 | 值 |
|------|-----|
| 端口 | 8008 |
| 分组 | filter（一票否决） |
| 环境 | CPU (Random Forest, ~1 MB) |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，无长度限制 |

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | 过敏原概率 |
| `label` | string | `"Allergen"` (score ≥ 0.3) 或 `"Non-Allergen"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `threshold` | float | 0.3 |
| `model` | string | `"Random Forest (AAC)"` |

#### 调用示例

```python
POST http://127.0.0.1:8008/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 阈值 0.3：流水线中 ≥ 0.3 直接淘汰（硬过滤）。
- 仅使用 20 种标准氨基酸的 AAC 特征（19 维，排除 B/J/O/U/X/Z）。
- 在原工具中对长序列（完整蛋白）优化，短肽预测不确定性较高。

---

### 1.9 GraphCPP — 细胞穿膜肽预测 (GNN)

| 属性 | 值 |
|------|-----|
| 端口 | 8009 |
| 分组 | score |
| 环境 | GPU/CPU (GraphSAGE GNN, 200 KB) |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列 |

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | CPP 概率 (sigmoid 输出) |
| `label` | string | `"CPP"` (score ≥ 0.5) 或 `"non-CPP"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `threshold` | float | 0.5 |
| `model_type` | string | `"GraphSAGE-GNN"` |

#### 调用示例

```python
POST http://127.0.0.1:8009/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 通过 RDKit 将氨基酸序列转为分子图（GraphSAGE + Topological Torsion 指纹, 2048 维）。
- 若 `Chem.MolFromFASTA()` 失败返回 `score=0.0`。
- 对 5–40 aa 短肽效果最佳，>100 aa 精度下降。
- 权重低于 pLM4CPPs（同为 CPP 预测，GNN 方法信号较稀疏）。

---

### 1.10 TemStaPro — 热稳定性预测

| 属性 | 值 |
|------|-----|
| 端口 | 8010 |
| 分组 | score |
| 环境 | GPU/CPU (ProtT5-XL, 2.3 GB + MLP×30, 80 MB) |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，无硬性长度限制 |

无额外参数。温度阈值（40/45/50/55/60/65°C）在模型中是固定的。

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | 30 个分类器输出的均值（越高越热稳定） |
| `label` | string | 温度区间，见下表 |

label 判定逻辑（6 个温度阈值，每个 ≥ 0.5 即视为稳定）：

| 稳定至 | label |
|--------|-------|
| < 40°C | `"<=40"` |
| 40–45°C | `"(40-45]"` |
| 45–50°C | `"(45-50]"` |
| 50–55°C | `"(50-55]"` |
| 55–60°C | `"(55-60]"` |
| 60–65°C | `"(60-65]"` |
| > 65°C | `"(65-70]"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `thresholds` | dict | 6 个温度阈值 (`"40"`–`"65"`)，每个包含 `raw`（均值）、`binary`（0/1）、`seeds`（5 个种子预测值） |
| `clash` | bool | 若二元预测非单调（如 1-0-1）则为 true，结果不可靠 |
| `thermophilicity` | string | `"mesophilic"` (≤45°C) / `"thermophilic"` (>45°C) / `"undetermined"` |

#### 调用示例

```python
POST http://127.0.0.1:8010/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 每个温度阈值使用 5 个不同随机种子的 MLP 集成（共 30 个分类器）。
- ProtT5-XL 编码器 ~2.3 GB，首次启动自动下载。
- 长序列 (>2000 aa) 编码速度显著下降。

---

### 1.11 SoDoPE — 溶解度预测

| 属性 | 值 |
|------|-----|
| 端口 | 8012 |
| 分组 | score |
| 环境 | CPU（纯数学运算，<1ms/条） |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，仅支持 20 种标准氨基酸 |

#### 输出

| 字段 | 类型 | 说明 |
|------|------|------|
| `score` | float (0–1) | 溶解度概率 = sigmoid(81.0581 × SWI − 62.7775) |
| `label` | string | `"Soluble"` (score ≥ 0.5) 或 `"Insoluble"` |

`details` 字段：

| 键 | 类型 | 说明 |
|----|------|------|
| `swi` | float | 溶解度加权指数 (Solubility-Weighted Index) |
| `probability` | float | 同 score |

#### 调用示例

```python
POST http://127.0.0.1:8012/predict/batch
{"sequences": [{"sequence": "YVPLPNVPQG"}]}
```

#### 注意事项

- 基于预计算的氨基酸溶解度权重表 + 逻辑回归。
- 仅支持 20 种标准氨基酸 (ACDEFGHIKLMNPQRSTVWY)，非标准残基报错。
- 计算速度极快，适合高通量初筛。

---

## 二、结构预测服务

结构服务基类：`tools/template/structure_service.py` → `StructureService`

**通用输入格式**：氨基酸序列字符串。**通用输出格式**：PDB/mmCIF 格式的三维结构文本。

### 2.1 AlphaFold3 — 3D 生物分子结构预测

| 属性 | 值 |
|------|-----|
| 端口 | 8201 |
| 分组 | structure |
| 环境 | **Linux + NVIDIA GPU 必需**（Docker） |
| 推荐批量 | 1 |
| 超时 | 3600s |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，1–5000 aa |

#### 输出

```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "pdb_content": "data_igem_silk_abc...\n#\nloop_\n...",
    "confidence": 0.85,
    "details": {
      "format": "mmcif",
      "job_name": "igem_silk_abc123",
      "confidence_metrics": {
        "ptm": 0.82,
        "iptm": 0.72,
        "fraction_disordered": 0.05,
        "has_clash": false,
        "ranking_score": 0.85
      }
    }
  }
}
```

| 输出字段 | 类型 | 说明 |
|----------|------|------|
| `pdb_content` | string | **mmCIF 格式**结构文件（非标准 PDB） |
| `confidence` | float | ranking_score，模型置信度 |
| `details.confidence_metrics.ptm` | float | 预测 TM-score |
| `details.confidence_metrics.iptm` | float | 界面 pTM |
| `details.confidence_metrics.ranking_score` | float | 综合排序分数 |

#### 调用示例

```python
POST http://127.0.0.1:8201/predict
{"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}
```

#### 注意事项

- **平台限制**：仅支持 Ubuntu + NVIDIA GPU。macOS / CPU 环境会直接报错。
- 需要配置 `AF3_MODEL_DIR` 和 `AF3_DATABASE_DIR` 环境变量（模型 ~TB 级）。
- 输出为 **mmCIF 格式**而非标准 PDB，后续工具如需 PDB 需转换。
- 每次预测约数分钟，批量模式串行执行。
- 内部使用 `modelSeeds: [1]` 单种子运行。

---

### 2.2 PEP-FOLD4 — 肽从头结构预测

| 属性 | 值 |
|------|-----|
| 端口 | 8202 |
| 分组 | structure |
| 环境 | Docker (CPU)，sOPEP 力场 |
| 推荐批量 | 5 |
| 超时 | 1800s |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `sequence` | string | 是 | 氨基酸序列，**5–40 aa**，仅 20 种标准氨基酸 |

内部参数（固定默认值，非请求参数）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| pH | 7.0 | 溶液 pH |
| ionic_strength | 150.0 mM | 离子强度 |
| num_models | 100 | 蒙特卡洛采样数（聚类为 5 个输出模型） |

#### 输出

```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "pdb_content": "ATOM      1  N   ...\nATOM      2  CA  ...\n...",
    "confidence": null,
    "details": {
      "format": "pdb",
      "num_models": 5,
      "model_files": ["model1.pdb", "model2.pdb", ...],
      "energy": { "energy_report": "sOPEP energy: -45.3 ..." }
    }
  }
}
```

| 输出字段 | 类型 | 说明 |
|----------|------|------|
| `pdb_content` | string | **标准 PDB 格式**，最低能量构象 (model1.pdb) |
| `confidence` | null | 当前版本不输出置信度 |
| `details.num_models` | int | 输出模型数量（预期 5 个） |
| `details.energy` | dict | (可选) sOPEP 能量报告 |

#### 调用示例

```python
POST http://127.0.0.1:8202/predict
{"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}
```

#### 注意事项

- **严格长度限制**：< 5 aa 或 > 40 aa 返回错误。
- **仅支持 20 种标准氨基酸** (ACDEFGHIKLMNPQRSTVWY)，非标准残基报错。
- 输出 model1.pdb 为最低能量的 cluster-center 结构。
- 每次预测约数分钟，批量模式串行执行。

---

## 三、PDB 结构评分服务

PDB 服务基类：`tools/template/pdb_service.py` → `PdbScoringService`

**通用输入格式**：PDB 文件内容（文本字符串）+ 可选序列和链信息。

### 3.1 SASA — 溶剂可及表面积分析

| 属性 | 值 |
|------|-----|
| 端口 | 8101 |
| 分组 | pdb_score |
| 环境 | CPU (FreeSASA, Lee-Richards 算法) |
| 推荐批量 | 50 |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pdb_content` | string | 是 | PDB 格式文件内容 |
| `sequence` | string | 否 | 目标肽序列。提供时仅统计该肽区域的 SASA；省略则返回 `label="no_target"` |
| `chain_id` | string | 否 | 目标链 ID，默认 `"A"`。若未找到使用第一条链 |

内部参数（固定默认值，非请求参数）：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| probe_radius | 1.4 Å | 探针半径（水分子模拟） |
| exposure_threshold | 0.25 | 相对 SASA 阈值，超过即判定 "exposed" |

#### 输出

```json
{
  "success": true,
  "peptide_id": "pep_001",
  "result": {
    "score": 0.7234,
    "label": "exposed",
    "details": {
      "chain": "A",
      "probe_radius": 1.4,
      "exposure_threshold": 0.25,
      "peptide": {
        "sequence": "YWDHINNPEVYF",
        "num_residues": 12,
        "num_exposed": 9,
        "total_sasa": 1845.32,
        "mean_relative_sasa": 0.7234,
        "exposure_ratio": 0.75,
        "residues": [
          {"residue_id": 1, "residue_name": "TYR", "residue_code": "Y",
           "sasa": 180.5, "relative_sasa": 0.708, "is_exposed": true}
        ]
      },
      "all_residues": [ ... ]
    }
  }
}
```

| 输出字段 | 类型 | 说明 |
|----------|------|------|
| `score` | float (0–1) | 肽区域平均相对 SASA（越高越暴露） |
| `label` | string | `"exposed"` (exposure_ratio > 0.6) / `"partial"` (> 0.3) / `"buried"` / `"no_target"` / `"error"` |
| `details.peptide.exposure_ratio` | float | 暴露残基占比 (>0.25 相对 SASA) |
| `details.peptide.residues` | list | 逐残基 SASA 明细 |

#### 调用示例

```python
POST http://127.0.0.1:8101/predict
{
  "pdb_content": "ATOM      1  N   ALA A   1 ...\n...",
  "sequence": "YVPLPNVPQG",
  "chain_id": "A",
  "peptide_id": "construct_001"
}
```

#### 注意事项

- 必须提供 `sequence` 才能定位肽区域，否则 `score=0, label="no_target"`。
- 使用 Tien et al. 2013 最大可及表面积参考值。
- 参考 SASA 值与氨基酸类型相关（如 TYR 参考值高于 GLY）。

---

### 3.2 Aggrescan3D — 结构聚集倾向分析

| 属性 | 值 |
|------|-----|
| 端口 | 8102 |
| 分组 | pdb_score |
| 环境 | Docker (CPU), `lcbio/a3d_server` 镜像 |
| 推荐批量 | 10 |
| 内部并发 | 2 (Docker 容器限制) |
| 超时 | 900s |

#### 输入

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pdb_content` | string | 是 | 必须包含 `ATOM` 或 `HETATM` 记录 |
| `chain_id` | string | 否 | 目标链 ID，用于后过滤结果。未找到则报错 |
| `sequence` | string | 否 | 接受但不参与评分（仅 `chain_id` 过滤） |

内部参数：

| 参数 | 默认值 | 环境变量 | 说明 |
|------|--------|----------|------|
| distance_cutoff | 10 Å | `A3D_DISTANCE` | 空间邻域距离阈值 |
| Docker 镜像 | `lcbio/a3d_server` | `A3D_IMAGE` | Aggrescan3D Docker 镜像 |

#### 输出

```json
{
  "success": true,
  "peptide_id": "construct_001",
  "result": {
    "score": 0.35,
    "label": "moderate_aggregation_risk",
    "details": {
      "risk_score": 0.35,
      "statistics": {
        "num_residues": 150, "min_score": -1.234, "max_score": 3.567,
        "avg_score": 0.123, "total_score": 18.45,
        "positive_fraction": 0.28, "positive_mean": 1.234
      },
      "top_hotspots": [
        {"chain": "A", "residue_id": "42", "residue_name": "LEU", "score": 3.567}
      ],
      "residues": [
        {"chain": "A", "residue_id": "1", "residue_name": "MET",
         "a3d_score": 0.456, "is_aggregation_prone": true}
      ],
      "output_pdb_content": "ATOM ..."  // (可选，b-factor 着色)
    }
  }
}
```

| 输出字段 | 类型 | 说明 |
|----------|------|------|
| `score` | float (0–1) | 归一化聚集风险评分（越高风险越大） |
| `label` | string | `"high_aggregation_risk"` (score ≥ 0.5) / `"moderate"` (≥ 0.25) / `"low"` |
| `details.residues` | list | 逐残基原始 A3D 评分 |
| `details.top_hotspots` | list | 前 20 个聚集热点残基 |
| `details.output_pdb_content` | string | (可选) 着色后的输出 PDB |

**风险评分归一化公式**：

```
risk_score = 0.50 × positive_fraction
           + 0.30 × clamp(positive_mean / 4.0, 0, 1)
           + 0.20 × clamp(max_score / 4.0, 0, 1)
```

#### 调用示例

```python
POST http://127.0.0.1:8102/predict
{
  "pdb_content": "ATOM      1  N   ALA A   1 ...\n...",
  "chain_id": "A",
  "peptide_id": "construct_001"
}
```

#### 注意事项

- PDB 内容必须包含 `ATOM` 或 `HETATM` 记录，否则拒绝。
- 每次调用启动 Docker 容器，耗时较长（数十秒至数分钟）。内部并发限制为 2。
- `score` 越高表示聚集风险越大，这是风险指标（非"越好越高"）。

---

## 四、流水线调用流程

### 4.1 肽级别评分（Step 3）

流水线通过 `ServiceClient.evaluate_peptides()` 并发调用所有可用 Fasta 评分/过滤服务：

```
peptides[] → POST /predict/batch (各服务并行) → peptide_scores{}
```

调用方式：

```python
from main.client import ServiceClient

client = ServiceClient(timeout=120.0)

# 1. 健康检查
health = await client.check_health()

# 2. 对全部肽并发调用所有可用服务
result = await client.evaluate_peptides(peptides, health=health)
# result["peptide_scores"] → {peptide_id: {service_name: {score, label, details}}}

# 3. 肽筛选后，map 到 construct
scored = ServiceClient.map_scores_to_constructs(constructs, result["peptide_scores"])
```

### 4.2 PDB 结构评分（construct 级别）

若启用结构评分（AlphaFold3 / PEP-FOLD4 → SASA / Aggrescan3D）：

```python
# 步骤 A：结构预测
POST http://127.0.0.1:8202/predict
{"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}
# → pdb_content

# 步骤 B：PDB 评分
POST http://127.0.0.1:8101/predict
{"pdb_content": "<上一步返回的 pdb_content>", "sequence": "YVPLPNVPQG", "chain_id": "A"}
# → {score, label: "exposed"/"partial"/"buried"}
```

### 4.3 客户端方法速查

| 方法 | 端点 | 用途 |
|------|------|------|
| `check_health()` | `GET /health` | 并发检测全部服务可用性 |
| `predict_single(name, seq, pid)` | `POST /predict` | 单条序列预测（调试） |
| `predict_batch(name, sequences[])` | `POST /predict/batch` | 批量序列预测 |
| `predict_pdb_single(name, pdb, ...)` | `POST /predict` | 单 PDB 评分 |
| `predict_pdb_batch(name, requests[])` | `POST /predict/batch` | 批量 PDB 评分 |
| `evaluate_peptides(peptides[])` | `POST /predict/batch` × N | 全服务并发评估（核心） |
| `map_scores_to_constructs()` | (本地) | 肽评分广播至 construct |

### 4.4 服务分组与流水线角色

| 分组 | 服务 | 流水线作用 |
|------|------|------------|
| **score** | AnOxPePred, BepiPred-3.0, MHCflurry, pLM4CPPs, TIPred, GraphCPP, TemStaPro, SoDoPE | 加权平均参与综合评分 |
| **filter** | ToxinPred3, HemoPI2, AlgPred2 | 一票否决硬过滤 |
| **structure** | AlphaFold3, PEP-FOLD4 | 序列→3D 结构，为 PDB 评分提供输入 |
| **pdb_score** | SASA, Aggrescan3D | 结构→评分，评估 construct 3D 性质 |

### 4.5 评分权重与反向指标

肽最终评分 = Σ(weight × adjusted_score) / Σ(weight)

| 服务 | 权重 | 是否反向 | 说明 |
|------|------|----------|------|
| AnOxPePred | 0.35 | 否 | 核心功能 |
| TIPred | 0.30 | 否 | 核心功能（抗黑色素） |
| BepiPred-3.0 | 0.15 | 否 | 暴露度代理 |
| pLM4CPPs | 0.10 | 否 | 辅助递送 |
| SoDoPE | 0.05 | 否 | 表达可行性 |
| MHCflurry | 0.05 | **是** (1.0 − score) | 免疫原性（越低越好） |
| GraphCPP | 0.05 | 否 | 辅助递送 (GNN) |
