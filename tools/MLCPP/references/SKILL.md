---
name: mlcpp
description: 当用户需要预测细胞穿透肽（CPP）时触发此技能。它基于机器学习模型预测肽的细胞穿透能力，支持在线和离线双模式运行。
created: 2026-04-18
version: 1.0.0
last_updated: 2026-04-18
---

# MLCPP

## What It Is
MLCPP 2.0 (Machine Learning-based Cell Penetrating Peptide Predictor) 是一个基于机器学习的细胞穿透肽预测工具。它使用预训练的机器学习模型来评估肽的细胞穿透潜力，为药物递送系统和治疗性肽设计提供关键信息。

## When to Use
- **药物递送系统设计**：识别潜在的细胞穿透肽载体
- **治疗性肽开发**：评估肽的细胞穿透能力
- **高通量筛选**：从肽库中筛选有效的CPP候选物
- **肽工程优化**：设计具有增强穿透能力的肽变体
- **生物信息学分析**：批量分析蛋白质组中的潜在CPP

## Methodology
MLCPP 使用以下方法进行预测：
1. **机器学习模型**：基于随机森林、支持向量机等算法的预测模型
2. **特征提取**：从肽序列中提取物理化学和结构特征
3. **双模式运行**：支持在线API调用和离线模拟模式
4. **概率评分**：提供细胞穿透概率（0-1之间的分数）
5. **阈值分类**：基于阈值将肽分类为CPP或非CPP

## Operations

### 安装
```bash
# 安装核心依赖
pip install requests pandas numpy

# 可选：安装可视化依赖
pip install matplotlib seaborn

# 可选：安装FASTA处理依赖
pip install biopython
```

### 快速开始
```python
from tools.mlcpp_integration import MLCPPIntegration

# 初始化MLCPP（默认使用在线模式）
mlcpp = MLCPPIntegration(mode="online", verbose=True)

# 预测单个肽的细胞穿透能力
peptide = "RKKRRQRRR"
result = mlcpp.predict_single(peptide, peptide_id="test_peptide")

print(f"细胞穿透概率: {result.cell_penetrating_probability:.3f}")
print(f"预测类别: {result.predicted_class}")
print(f"置信度: {result.confidence:.3f}")
```

### 离线模式
```python
# 使用离线模式（当网络不可用时）
mlcpp_offline = MLCPPIntegration(mode="offline")

# 离线预测
result = mlcpp_offline.predict_single("RKKRRQRRR")
print(f"离线预测结果: {result.predicted_class}")
```

### 批量预测
```python
# 批量预测多个肽
peptides = {
    "TAT": "RKKRRQRRR",
    "Penetratin": "RQIKIWFQNRRMKWKK",
    "Polyarginine": "RRRRRRRRR"
}

batch_results = mlcpp.predict_batch(peptides)

# 导出结果
mlcpp.export_results(batch_results, "mlcpp_results.csv")
```

## Inputs and Outputs
- **输入**：
  - 肽序列（字符串格式）
  - 肽ID（可选）
  - 运行模式（online/offline）
  - 文件路径（FASTA、CSV格式）
- **输出**：
  - 细胞穿透概率（0-1之间的分数）
  - 预测类别（CPP/非CPP）
  - 置信度分数
  - 详细特征分析结果
  - CSV/JSON格式的结果文件

## Examples
1. **单个肽评估**：快速评估特定肽的细胞穿透潜力
2. **高通量筛选**：从大型肽库中识别CPP候选物
3. **模式比较**：比较在线和离线模式的预测结果
4. **阈值优化**：根据应用需求调整分类阈值

## References Index
| File | Contents |
|------|----------|
| `references/mlcpp_guide.md` | 详细的使用指南和API参考 |
| `scripts/cpp_screening_pipeline.py` | 细胞穿透肽筛选管道脚本 |