---
name: toxinpred3
description: 当需要预测肽序列毒性、提取 AAC/DPC 特征用于机器学习模型、或在融合引擎中过滤有毒肽候选时触发此技能。
created: 2026-04-11
version: 1.1
last_updated: 2026-04-25
---

# ToxinPred 3.0 技能包

> 原仓库: https://github.com/raghavagps/toxinpred3
> 论文: Rathore AS, et al. (2024) "ToxinPred3.0: An improved method for the prediction of toxicity of peptides." *Computers in Biology and Medicine*.

## 工具定位

**ToxinPred 3.0** 是由印度 IIITD Prof. G. P. S. Raghava 团队开发的肽毒性预测工具，在融合引擎中承担**粗筛过滤**角色，用于在全排列组合之前剔除明显有毒的肽段。

### 在融合引擎中的定位

| 应用场景 | 具体作用 |
|---------|---------|
| 粗筛过滤 | 剔除有毒肽候选 |
| 特征输入 | AAC/DPC 特征作为六功效模型输入 |
| 安全性评估 | 评估融合肽各组分潜在毒性风险 |
| 参考对照 | 与其他毒性预测工具交叉验证 |

### 技术原理

```
毒性预测 = ML 分数 (Extra Trees + AAC/DPC)
- ML 模型：基于 Extra Trees 分类器
- 特征：AAC(20维) + DPC(400维) = 420维
- 服务使用 Model 1 (纯 ML)，不依赖 MERCI/Perl 杂交路径
```

> **Model 1 vs Model 2**: 官方提供两种模式 — Model 1 (AAC+DPC) 和 Model 2 (Hybrid+MERCI motif)。
> 实际测试发现 Model 2 在已知毒素上产生假阴性（MERCI 负向 motif 过度惩罚），服务选择 Model 1。

---

## 安装与配置

### 环境要求

- Python 3.11 - 3.11 (需要 scikit-learn 1.2.2 兼容)
- 依赖：numpy<2, pandas, scikit-learn==1.2.2, joblib

### 标准化安装流程

```bash
cd ToxinPred3
uv venv --python 3.11 .venv
source .venv/bin/activate

uv pip install "numpy<2" pandas scikit-learn==1.2.2 joblib
uv pip install toxinpred3
```

### 快速验证

```python
from toxinpred_features import predict_toxicity

sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG"]
results = predict_toxicity(sequences)
print(results)
```

---

## 核心功能

### 1. AAC 氨基酸组成 (20维)

```python
from toxinpred_features import aac_composition

sequences = ["KWKLFKKIGAVLKVL"]
aac = aac_composition(sequences)
# 输出: DataFrame, 20列, AAC_A, AAC_C, ... AAC_Y
```

**生物学意义：**
- 阳离子氨基酸(K,R)高 → 可能抗菌
- 疏水氨基酸(A,V,I,L)高 → 影响膜穿透
- 芳香族氨基酸(W,Y,F) → 可能影响受体结合

### 2. DPC 二肽组成 (400维)

```python
from toxinpred_features import dpc_composition

sequences = ["KWKLFKKIGAVLKVL"]
dpc = dpc_composition(sequences)
# 输出: DataFrame, 400列, DPC_AA, DPC_AC, ... DPC_WY
```

**生物学意义：**
- 反映局部结构偏好
- 某些二肽 motif 是毒素特征标记
- 捕捉氨基酸间相互作用

### 3. 完整特征提取 (420维)

```python
from toxinpred_features import extract_features

sequences = ["KWKLFKKIGAVLKVL"]
features = extract_features(sequences)
# 输出: DataFrame, 420列 (AAC + DPC)
```

### 4. 毒性预测

```python
from toxinpred_features import predict_toxicity

sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG"]
results = predict_toxicity(sequences, threshold=0.38, model=2)
# 输出: Name, Sequence, Length, Score, Prediction
```

**参数说明：**
| 参数 | 说明 | 默认值 |
|------|------|--------|
| threshold | 毒性阈值 (0-1) | 0.38 |
| model | 1=AAC+DPC, 2=Hybrid | 2 |

**阈值建议：**
| 场景 | 阈值 | 说明 |
|------|------|------|
| 高风险（直接给药） | 0.3 | 提高敏感性 |
| 初筛阶段 | 0.38 | 默认值 |
| 低风险（外用） | 0.5 | 提高特异性 |

---

## 批量处理

### 从 FASTA 文件批量预测

```python
from toxinpred_features import batch_predict_from_file

results = batch_predict_from_file(
    input_file="peptides.fa",
    output_file="predictions.csv",
    threshold=0.38,
    model=2
)
```

### 融合引擎集成示例

```python
from toxinpred_features import predict_toxicity, extract_features
import pandas as pd

def filter_toxic_peptides(peptides: list, threshold: float = 0.38) -> tuple:
    """
    过滤掉可能有毒的肽段

    Returns:
        (安全肽列表, 有毒肽列表)
    """
    predictions = predict_toxicity(peptides, threshold=threshold)

    safe = predictions[predictions['Prediction'] == 'Non-Toxin']['Sequence'].tolist()
    toxic = predictions[predictions['Prediction'] == 'Toxin']['Sequence'].tolist()

    return safe, toxic


def get_peptide_features(peptides: list) -> pd.DataFrame:
    """
    获取肽的完整特征向量，用于机器学习模型输入
    """
    return extract_features(peptides)


# 使用示例
test_peptides = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG", "GIGAVLKVLTTGLPALISWIKRKRQQ"]
safe, toxic = filter_toxic_peptides(test_peptides)
features = get_peptide_features(test_peptides)
```

---

## 快速参考

| 功能 | 函数 | 输出 |
|------|------|------|
| 特征提取 | `extract_features(sequences)` | DataFrame (420列) |
| AAC | `aac_composition(sequences)` | DataFrame (20列) |
| DPC | `dpc_composition(sequences)` | DataFrame (400列) |
| 毒性预测 | `predict_toxicity(sequences)` | DataFrame |
| 批量预测 | `batch_predict_from_file(input, output)` | CSV文件 |

---

## Examples

### 示例1：单序列毒性预测

```python
from toxinpred_features import predict_toxicity

result = predict_toxicity(["KWKLFLFKKIGAVLKVL"], threshold=0.38)
print(result)
```

### 示例2：批量处理+特征提取

```python
from toxinpred_features import batch_predict_from_file, extract_features

# 批量预测
results = batch_predict_from_file("peptides.fa", "out.csv")

# 提取特征用于ML
features = extract_features("peptides.fa")
print(f"特征维度: {features.shape}")  # (n, 420)
```

### 示例3：运行演示脚本

```bash
cd ToxinPred3
source .venv/bin/activate
python scripts/demo.py
```

---

## 已知问题

### 官方 CLI 的 delimiter bug

**问题：** toxinpred3 CLI 在写入输出文件时报错 `ValueError: bad delimiter value`

**原因：** pandas 1.4+ 对 `to_csv` 的 delimiter 参数检查更严格

**解决方案：** 使用 `toxinpred_features.py` 中的 Python API（已修复此问题）

---

## References Index

| File | Contents |
|------|----------|
| `references/installation.md` | 详细安装步骤与故障排除 |
| `references/biological_background.md` | 肽毒性生物学背景 |
| `references/api_reference.md` | API 详细参数说明 |
| `scripts/demo.py` | 演示脚本 |
| `toxinpred_features.py` | Python API 封装模块 |

---

## 交付物清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `toxinpred_features.py` | ✅ 已创建 | Python API 封装 (v1.1) |
| `test_demo.fa` | ✅ 已创建 | 测试数据 |
| `scripts/demo.py` | ✅ 已修复 | 演示脚本 |
| `SKILL.md` | ✅ 已更新 | 本技能文档 |
| `references/` | ✅ 可用 | 详细参考文档 |

---

## 更新日志

### v1.1 (2026-04-25)
- 创建 `toxinpred_features.py` Python API 封装
- 修复 demo.py 导入路径
- 修复官方 CLI 的 pandas delimiter bug
- 更新 SKILL.md 准确描述功能

### v1.0 (2026-04-11)
- 初始版本（文档描述不准确）

---

**作者**：Sisyphus (Agent)
**日期**：2026-04-25
**验证状态**：✅ **全部通过** (Python 3.11 + sklearn 1.2.2)
