---
name: anoxpepred
description: 当用户需要预测肽序列的抗氧化活性时触发此技能。它基于机器学习模型预测肽的抗氧化潜力，支持多种抗氧化机制和批量处理。
created: 2026-04-18
version: 1.1.0
last_updated: 2026-04-25
---

# AnOxPePred

## What It Is
AnOxPePred (Antioxidant Peptide Predictor) 是一个基于深度学习的抗氧化肽预测工具。它使用预训练的卷积神经网络模型来评估肽序列的抗氧化潜力，支持多种抗氧化机制，包括：
- **FRS (Free Radical Scavenging)**：自由基清除能力
- **Chel (Metal Chelation)**：金属离子螯合能力

模型来源：[TobiasHeOl/AnOxPePred](https://github.com/TobiasHeOl/AnOxPePred)

## When to Use
- **抗氧化肽筛选**：从肽库中识别潜在的抗氧化候选物
- **功能食品开发**：评估食品源性肽的抗氧化活性
- **药物发现**：寻找具有治疗潜力的抗氧化肽
- **肽工程**：设计具有增强抗氧化活性的肽变体
- **生物信息学分析**：批量分析蛋白质水解产物的抗氧化潜力

## Methodology
AnOxPePred 使用深度卷积神经网络进行预测：
1. **序列编码**：使用 30x20 的 one-hot 编码矩阵表示肽序列
2. **卷积层**：128 个滤波器，核大小 3，激活函数 elu
3. **池化层**：平均池化，池大小 3
4. **全连接层**：256 个神经元，激活函数 elu，dropout 0.15
5. **输出层**：2 个神经元（对应 FRS 和 Chel），sigmoid 激活
6. **损失函数**：Focal Loss（处理类别不平衡）

## Operations

### 安装

**方式一：使用 uv（推荐）**
```bash
# 创建虚拟环境
cd /path/to/AnOxPePred
uv sync

# 可选：安装完整功能（深度学习模型）
uv sync --extra ml

# 可选：安装可视化依赖
uv sync --extra viz
```

**方式二：使用 pip（不推荐）**
```bash
pip install pandas numpy
pip install tensorflow biopython matplotlib seaborn  # 完整功能
```

### 模型文件说明

深度学习模型需要以下文件（已包含在 `anoxpepred_data/` 目录中）：
- `AnOxPePred_v1.data-00000-of-00001`：模型权重文件
- `AnOxPePred_v1.index`：模型索引文件
- `One-hot_encoding.txt`：氨基酸编码矩阵

如果模型文件缺失，会自动降级到基于氨基酸组成的规则预测模式。

### 快速开始

```python
import sys
sys.path.insert(0, '/path/to/AnOxPePred')  # 添加项目路径

from tools.anoxpepred_integration import AnOxPePredIntegration

# 初始化预测器
predictor = AnOxPePredIntegration()

# 预测单个肽的抗氧化活性
peptide = "YVPLPNVPQG"
result = predictor.predict_single(peptide, peptide_id="test_peptide")

print(f"抗氧化概率: {result.overall_score:.3f}")
print(f"预测类别: {result.overall_class}")
print(f"自由基清除分数(FRS): {result.frs_score:.3f}")
print(f"金属螯合分数(Chel): {result.chel_score:.3f}")
print(f"置信度: {result.confidence}")
```

### 批量预测

```python
# 批量预测多个肽
peptides = {
    "pep1": "YVPLPNVPQG",
    "pep2": "FFVAPFPEVFGK",
    "pep3": "KVEPLRAD"
}

batch_results = predictor.predict_batch(peptides)

# 打印结果
for peptide_id, result in batch_results.items():
    print(f"{peptide_id}: {result.sequence} -> {result.overall_class} (score: {result.overall_score:.4f})")

# 导出结果
predictor.export_results(batch_results, "anoxpepred_results.csv", format="csv")
```

### 从文件预测

```python
# 从 FASTA 文件预测
results = predictor.predict_from_fasta("peptides.fasta", threshold=0.5)

# 从 CSV 文件预测
results = predictor.predict_from_csv("peptides.csv", seq_col="sequence", id_col="id")
```

## Inputs and Outputs
- **输入**：
  - 肽序列（字符串格式，通常为 2-50 个氨基酸）
  - 肽ID（可选）
  - 文件路径（FASTA、CSV 格式）
- **输出**：
  - `overall_score`：综合抗氧化分数（0-1）
  - `overall_class`：预测类别（Antioxidant / Non-antioxidant）
  - `frs_score`：自由基清除分数（0-1）
  - `chel_score`：金属螯合分数（0-1）
  - `confidence`：置信度（high / medium / low / very_low）
  - `mechanism_scores`：各机制分数字典

## Examples

1. **单个肽评估**：
```python
result = predictor.predict_single("CCHHPLLLLLLA", peptide_id="cysteine_rich")
print(f"抗氧化: {result.is_antioxidant}, 分数: {result.overall_score:.3f}")
```

2. **高通量筛选**：
```python
# 读取测试数据
import pandas as pd
df = pd.read_csv("peptides.csv")
sequences = {str(i): seq for i, seq in enumerate(df['sequence'])}

# 批量预测
results = predictor.predict_batch(sequences)

# 筛选高活性肽
antioxidant_peptides = {
    pid: r for pid, r in results.items() if r.is_antioxidant
}
print(f"找到 {len(antioxidant_peptides)} 条抗氧化肽")
```

3. **机制分析**：
```python
result = predictor.predict_single("YVPLPNVPQG")
print(f"自由基清除: {result.mechanism_scores['radical']:.3f}")
print(f"金属螯合: {result.mechanism_scores['metal']:.3f}")
```

## References Index
| File | Contents |
|------|----------|
| `references/anoxpepred_guide.md` | 详细的技术文档、算法说明和特征工程 |
| `scripts/antioxidant_screening.py` | 抗氧化肽筛选管道脚本 |
| `tools/anoxpepred_integration.py` | 核心集成模块 |
| `anoxpepred_data/` | 模型权重和编码矩阵 |

## Limitations

1. **序列长度**：模型针对 2-50 个氨基酸的肽设计，超长序列可能不准确
2. **非标准氨基酸**：包含非标准氨基酸（B、J、Z、U、O、X）的序列可能无法正确编码
3. **模型可用性**：深度学习模型需要 TensorFlow，如果未安装会自动降级到规则预测
4. **预测模式**：
   - 深度学习模式：使用预训练模型，准确性更高
   - 规则预测模式：基于氨基酸组成，准确性较低但无需额外依赖