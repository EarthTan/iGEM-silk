---
name: sodope
description: 蛋白质溶解度预测（Solubility-Weighted Index）。根据氨基酸序列快速评估蛋白在大肠杆菌中表达时的可溶性，适用于 iGEM 队员筛选高可溶性蛋白/肽候选物。
created: 2026-05-11
version: 1.0
---

# SoDoPE — Solubility-Weighted Index

## What It Is

SoDoPE 是一个基于 SWI (Solubility-Weighted Index) 的蛋白质溶解度快速预测工具。它使用 20 种标准氨基酸的经验溶解度权重表，通过简单的加权平均 + 逻辑回归，从序列直接预测蛋白在表达时的可溶性。

预测结果包括：
- **SWI** (Solubility-Weighted Index): 0-1 范围的原始加权分数
- **Probability of Solubility**: 经由逻辑回归映射的溶解概率 (0-1)
- **Soluble / Insoluble**: 二分类标签（阈值 0.5）

## When to Use（iGEM 场景）

- 你有多个候选蛋白/肽，不确定用哪个才能高效表达，需要挑出最容易溶解的
- 对蛋白做了突变改造，想快速验证突变是否可能影响可溶性
- 高通量筛选大量序列时（SWI 速度极快），先筛掉不可溶的序列
- 作为实验前初步过滤步骤，需要快速、无需外部依赖的评分工具

## Methodology

```
FASTA 序列 → 逐残基查表 (20 aa 权重) → 取均值 = SWI → sigmoid(A·SWI + B) = 溶解概率
```

- 20 种标准氨基酸各有一个经验权重值（通过 eSOL 数据集对数优化得到）
- 值越大 → 该氨基酸越倾向出现在可溶蛋白中
- 所有残基权重取算术平均即为 SWI
- 经逻辑回归常数 A=81.0581, B=-62.7775 映射到溶解概率
- 整个过程无模型加载、无 GPU 需求，纯内存计算

## Inputs and Outputs

- **Input**: 氨基酸序列（单字母，大小写均可，仅支持 20 种标准氨基酸 ACDEFGHIKLMNPQRSTVWY）
- **Output**:
  | 字段 | 含义 |
  |------|------|
  | `score` | 溶解概率 (0-1)，≥0.5 表示预测为可溶 |
  | `label` | `Soluble` 或 `Insoluble` |
  | `swi` | 原始 SWI 分数 |
  | `probability` | 溶解概率值与 score 相同 |
  | `sequence_length` | 序列长度 |

## Requirements

### 软件

- Python 3.11+
- numpy

### 硬件

- 任意 CPU。SWI 无需 GPU，无需显卡，无需模型文件下载。
- 速度：单条序列预测 < 1ms

## Examples

**例 1 — 从候选蛋白中挑最可溶的**

你从 NCBI 找了 3 个来自不同物种的纤维素酶序列，不确定用哪个做大肠杆菌表达。把它们全部发到 `/predict/batch`，比较 `score` 和 `swi`。选择溶解概率最高的那个去合成表达。

**例 2 — 验证突变是否改善了可溶性**

你对某个低溶解度的蛋白做了表面氨基酸替换（如引入更多 Glu/Asp/Lys），想验证改造是否有效。把野生型和突变体的序列分别预测，对比 `swi` 分数。如果突变体的 SWI 明显更高，说明改造方向正确。

**例 3 — 高通量初步筛选**

你有一个 500 条短肽的文库，需要在合成前先筛掉可能不溶的序列。用 `/predict/batch` 批量预测，过滤掉 `label == "Insoluble"` 的序列，大幅减少合成和测试成本。

## References

| 文件 | 内容 |
|------|------|
| `sodope_integration.py` | SWI 算法实现，包含所有权重和逻辑回归常数 |
| `service.py` | 微服务入口，基于 FastaToolService 模板 |
| `../../tools/template/fasta_service.py` | 微服务基类，定义统一 API 接口 |

## Citation

```
@article{10.1093/bioinformatics/btaa578,
    author = {Bhandari, Bikash K and Gardner, Paul P and Lim, Chun Shen},
    title = "{Solubility-Weighted Index: fast and accurate prediction of protein solubility}",
    journal = {Bioinformatics},
    volume = {36},
    number = {22-23},
    pages = {5531-5539},
    year = {2020},
    doi = {10.1093/bioinformatics/btaa578},
}
```
