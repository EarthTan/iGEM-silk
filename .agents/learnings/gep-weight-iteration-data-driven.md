---
name: 权重迭代与数据驱动决策 — construct_composite 集中度失效发现 v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [weighting, data-driven, eda, composite-score, distribution-analysis, decision-making]
validated: true
---

# Gene Capsule: 权重迭代与数据驱动决策 — construct_composite 集中度失效发现

## Experience

**问题描述**: 初始 Round 6 评分公式给 construct_composite 分配了 0.50 权重，期望它在最终排名中反映肽功能+SoDoPE+TemStaPro 的综合质量。但在 Top 90 construct 中，construct_composite 的分布高度集中 —— P25=0.5225, P75=0.5336，中间 50% 的 spread 仅 **0.011**。

**症状**:
- construct_composite 加权重后几乎完全决定了排名（因为 SASA/A3D 的 spread 大但权重低）
- SASA 和 Aggrescan3D 的实际区分力被稀释到无意义
- 问题在运行 Round 6 前无法发现——数据分布特征需要实际跑完前序步骤才能获得

**根因**: 经过 Round 1-5 的多轮筛选（1M → 150），候选肽的质量趋于同质化。这是"筛选漏斗"的必然结果——顶部候选在前期各维度都高分，进入最终轮时差异极小。

```
筛选过程本身就是方差缩减过程：
  1M 肽 → 各维度方差大 → 多轮加权筛选 → 只剩高分肽
  → 高分肽在各维度上都高分 → 综合分差异极小（σ ≈ 0.011）
  → 综合分失去区分能力
```

### 解决方案

**数据驱动决策流程**：

1. **先跑数据，再看分布，后定权重**

```python
# 步骤 1：先跑一轮（含 construct_composite）
constructs = load_constructs()
scores = [c["construct_composite"] for c in constructs]

# 步骤 2：分析分布
import numpy as np
vals = sorted(scores)
p25, p75 = np.percentile(vals, [25, 75])
spread = p75 - p25
# Top 90: spread = 0.011 → 无区分能力

# 步骤 3：决策
if spread < 0.05:  # 高度集中
    W_CONSTRUCT = 0.0   # 忽略
    W_SASA = 0.40       # 提升 SASA 权重
    W_AGG = 0.40        # 提升 Aggrescan3D 权重
    W_pLDDT = 0.20      # 保留结构置信度
else:
    W_CONSTRUCT = 0.50  # 保留原权重
```

2. **用 EDA 替换假设**

| 假设 | 数据验证 | 结论 |
|------|---------|------|
| "construct_composite 应该能拉开差距" | P25-P75 spread=0.011 | ❌ 高度集中 |
| "SASA spread 不够大" | min=0.501, max=0.831 | ✅ spread=0.33 |
| "Aggrescan3D 有区分力" | 0.289–0.398 | ✅ spread=0.11 |
| "pLDDT 太差不可用" | 0.3666–0.4547 | ⚠️ 中等，可作质量控制 |

3. **最终 Round 6 公式**（移除 construct_composite 后）：

```
round6 = 0.40 × SASA + 0.40 × (1 - aggrisk) + 0.20 × pLDDT_norm
```

### 关键洞察

**不要预设权重，让数据说话。** 尤其是在多轮筛选流水线的后期阶段，早期有效的权重在后期可能完全失效。每一轮的权重应基于该轮输入数据的实际分布重新评估。

### 通用诊断方法

| 步骤 | 操作 | 判断标准 |
|------|------|---------|
| 1. 计算 P25/P75 | `np.percentile(vals, [25, 75])` | spread < 0.05 → 高度集中 |
| 2. 计算 CV | `std/mean` | CV < 0.05 → 高度集中 |
| 3. 可视化 | histogram/distplot | 单峰窄分布 → 无区分力 |
| 4. 比较各维度 spread | 所有评分维度的 spread 排名 | 选 spread 最大的 2-3 个维度做主权重 |

### Environment Fingerprint

- **任务域**: 多维度加权评分流水线
- **输入特征**: 经过多轮筛选的候选集（方差递减）
- **约束条件**: 最终排名需要最大区分度；各评分维度量纲不同
- **触发模式**: 筛选流水线的后期轮次（funnel 末端），数据已经高度同质化
- **不适用**: 初始筛选轮次（方差大，预设权重合理）；单维度评分场景；分类（而非排序）任务

### Audit Record

- **验证方式**: Top 90 construct_composite 分布实际计算 + 移除权重后 SASA/A3D 起作用的排名对比
- **测试用例**:
  1. 原权重（construct=0.50）: Top 10 与 construct_composite 排序几乎一致 → SASA/A3D 无效
  2. 新权重（construct=0.00）: Top 10 与 SASA 排序一致 → SASA/A3D 真正决定排名
- **成功率**: 100%（数据验证了决策的正确性）
- **局限性**: 如果 SASA 和 Aggrescan3D 本身也无区分力（所有候选在 3D 层面相似），则需要回到肽序列层面寻找新维度。当前 Top 90 的 SASA spread 0.33 足够大。
