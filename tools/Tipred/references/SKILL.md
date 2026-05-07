---
name: tipred
description: 当需要预测酪氨酸酶抑制肽(TIP)活性、进行抗黑色素生成肽筛选、或在融合引擎中进行TIP活性评分时触发此技能。
created: 2026-04-18
version: 2.0.0
last_updated: 2026-04-21
---

# TIPred - 酪氨酸酶抑制肽预测

## What It Is

预测**酪氨酸酶抑制肽（Tyrosinase Inhibitory Peptides, TIPs）**活性的计算工具，加速美白/抗黑色素生成肽的筛选。

### 融合引擎定位

| 层级 | 作用 |
|------|------|
| 特征化层 | 提供 547 维多视图特征表示 |
| 预测层 | TIP 活性概率评分（0-1） |
| 粗筛层 | 全排列前剔除无 TIP 活性组合 |

## When to Use

- 筛选抗黑色素生成肽候选序列
- 对融合肽进行 TIP 活性评分
- 作为六功效模型的特征输入之一
- 美白功效肽的预测与排名

## Methodology

```
肽序列 → 7种特征编码 → 547维特征向量 → Stacked Ensemble → TIP概率(0-1)
```

### 特征编码器（7种，547维）

| 编码器 | 全称 | 维度 |
|--------|------|------|
| AAC | Amino Acid Composition | 20 |
| DPC | Dipeptide Composition | 400 |
| APAAC | Amphiphilic Pseudo AAC | 40 |
| PAAC | Parallel Pseudo AAC | 40 |
| CTDC | Composition | 13 |
| CTDT | Transition | 13 |
| CTDD | Distribution | 21 |

### Stacked Ensemble

- **Base Models (Level 0)**: KNN, RF, SVM (RBF), GB
- **Meta Model (Level 1)**: Logistic Regression
- **训练策略**: 5 折交叉验证生成 base predictions，避免数据泄露

## Operations

### 环境

```bash
cd Tipred/
uv init --no-readme
uv add scikit-learn pandas numpy
```

### Python API

```python
from scripts.tipredictor_full import TIPredictorMVFF

predictor = TIPredictorMVFF(model_type='stacked')
results = predictor.train(sequences, labels)  # sequences: list, labels: list (1=TIP, 0=non-TIP)
probs = predictor.predict(['YGGFL', 'GHK'])
# → [0.905, 0.060]
```

### 命令行

```bash
# 训练
python scripts/tipredictor_full.py --train --input sequences.fasta --labels labels.csv --save-model mvff_model.pkl --type stacked

# 预测
python scripts/tipredictor_full.py --model mvff_model.pkl --input queries.fasta --output results.csv
```

## Inputs and Outputs

- **输入**: FASTA / CSV（含 sequence 列）/ Python List
- **输出**: TIP 概率（0-1）、预测分类（TIP/non-TIP，阈值 0.5）

```csv
ID,Sequence,TIP_Probability,Prediction
0,YGGFL,0.905,TIP
1,GHK,0.060,non-TIP
```

## Examples

### 快速训练与预测

```python
from scripts.tipredictor_full import TIPredictorMVFF

sequences = ['YGGFL', 'GHK'] * 50 + ['RRRRR', 'DDDDD'] * 50
labels = [1, 1] * 50 + [0, 0] * 50

predictor = TIPredictorMVFF(model_type='stacked')
predictor.train(sequences, labels)
probs = predictor.predict(['YGGFL', 'RRRRR'])
print(f'YGGFL: {probs[0]:.3f}, RRRRR: {probs[1]:.3f}')
```

### 批量筛选

```python
import pandas as pd
from scripts.tipredictor_full import TIPredictorMVFF

predictor = TIPredictorMVFF.load('mvff_model.pkl')
df = pd.read_csv('candidates.csv')
df['TIP_Prob'] = predictor.predict(df['Sequence'].tolist())
tip_candidates = df[df['TIP_Prob'] >= 0.5]
print(f'从 {len(df)} 条中筛选出 {len(tip_candidates)} 条 TIP 候选')
```

## References Index

| File | Contents |
|------|----------|
| `references/TIP-redesign.md` | 详细特征编码说明、模型对比、限制说明 |
| `references/tipredictor.py` | 旧版简单实现（10维特征） |
| `references/test_peptides.csv` | 测试数据 |
| `references/test_peptides.fasta` | 测试数据（FASTA 格式） |
| `scripts/train_example.py` | 训练示例脚本 |
