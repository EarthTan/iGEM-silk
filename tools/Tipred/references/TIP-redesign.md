# TIPred 详细参考文档

## 特征编码器详解

### AAC - Amino Acid Composition（20维）

20种标准氨基酸的出现频率。

```
AAC_i = count(aa_i) / length
```

### DPC - Dipeptide Composition（400维）

400种可能的二肽组合（20×20）的频率。

```
DPC_ij = count(aa_i-aa_j) / (length - 1)
```

### APAAC - Amphiphilic Pseudo AAC（21维）

引入两亲性（amphiphilicity）参数 λ，生成21维特征。

### PAAC - Parallel Pseudo AAC（21维）

基于并联（parallel）编码策略，引入间隔参数 λ。

### CTDC / CTDT / CTDD - Composition/Transition/Distribution

按氨基酸极性/电荷等性质分为7类：

| 类名 | 包含氨基酸 |
|------|-----------|
| hydrophobic | A, V, I, L, M, F, Y, W |
| polar | S, T, N, Q, C |
| positively_charged | K, R, H |
| negatively_charged | D, E |
| tiny | G, A, S |
| aromatic | F, Y, W |
| proline | P |

- **CTDC (13维)**: 各类别氨基酸占比
- **CTDT (13维)**: 相邻类别间转换频率
- **CTDD (21维)**: 各类别首位/末位/25%/50%/75%分位数位置

## 完整编码维度汇总

| 编码器 | 维度 |
|--------|------|
| AAC | 20 |
| DPC | 400 |
| APAAC | 21 |
| PAAC | 21 |
| CTDC | 13 |
| CTDT | 13 |
| CTDD | 21 |
| **总计** | **547** |

## 简单版 vs 完整 MVFF 版

| | Simple (`tipredictor.py`) | Full MVFF (`tipredictor_full.py`) |
|---|---|---|
| 特征维度 | 10 | **547** |
| 编码器数量 | 1 (modlamp) | **8种** |
| 模型 | 单模型 RF | **Stacked Ensemble** |
| 论文对应 | ❌ | **✅** |
| 支持序列长度 | 未明确 | **2-50 氨基酸** |

## 模型性能

| 指标 | 数值 |
|------|------|
| 特征维度 | 547 维 |
| Base Models | KNN, RF, SVM (RBF), GB |
| Meta Model | Logistic Regression |
| 训练策略 | 5-fold CV（避免数据泄露）|

## 限制与注意事项

### 短肽支持

- ✅ 支持 2-20 氨基酸的短肽
- ⚠️ 极短肽（<3 氨基酸）特征信息有限，预测置信度可能较低

### 融合肽处理

- ✅ 特征提取适用于任意肽序列
- 💡 建议：将融合肽作为整体输入，而非拆分后分别预测再合并

### 版本信息

- **model_type**: `'simple'` | `'stacked'`，默认 `'stacked'`
- 加载模型时需确保 Python 环境一致（scikit-learn 版本兼容）

## 引用文献

1. Charoenkwan P, et al. TIPred: a novel stacked ensemble approach for the accelerated discovery of tyrosinase inhibitory peptides. BMC Bioinformatics. 2023. DOI: 10.1186/s12859-023-05463-1
2. Shoombuatong W, et al. Advancing the accuracy of tyrosinase inhibitory peptides prediction via a multiview feature fusion strategy. Sci Rep. 2025. DOI: 10.1038/s41598-024-81807-y
