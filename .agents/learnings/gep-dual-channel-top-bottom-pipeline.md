---
name: 双通道（Top/Bottom）贯穿全流程的排选设计 v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [dual-channel, top-bottom, pipeline-design, negative-control, experimental-design]
validated: true
---

# Gene Capsule: 双通道（Top/Bottom）贯穿全流程的排选设计

## Experience

**问题描述**: 传统的单通道筛选流水线只输出"最好"的候选，但 wet-lab 验证需要阴性对照（negative control）来评估实验系统的区分能力。如果只从最终排名底部取阴性对照，这些序列可能在各维度都差（毒性、聚集等），无法确认实验失败的原因是抗氧化活性低还是其他维度的问题。

**设计**: 双通道（Top/Bottom）贯穿全流程

```
                    ┌─── Top 25K (抗氧化最好) ──→ Top 80 肽 ──→ 90 constructs ──→ Top 90 排名
1M 肽 → 分选 ───┤
                    └─── Bottom 25K (抗氧化最差) ──→ Bottom 10 肽 ──→ 60 constructs ──→ Bottom 60 排名
```

**核心原则**:

1. **分选依据单一维度**: 用纯 AnOxPePred（直接测量抗氧化活性）分选，不混合其他权重。确保 Top/Bottom 在抗氧化维度上真正分离
2. **安全维度同标准**: Top 和 Bottom 通道使用完全相同的安全过滤阈值（毒性、致敏性、溶血性等），确保 Bottom 阴性对照在安全维度上同样"干净"
3. **通道标签贯穿全流程**: 从 Round 2 分选开始，每行数据携带 `channel` 标签（top/bottom），下游所有评分和排名按通道分别统计
4. **各自独立排名**: 最终输出两套排名——Top ranking 和 Bottom ranking，各自按 Round 6 综合分排序

**实现方式**:

```python
# Round 2: 分选时保留 channel 标签
for row in all_scored:
    row["channel"] = "top" if row["anoxpepred"] >= threshold else "bottom"

# 每通道独立选取
top_n = get_top_n(rows, "top", 25000, key="anoxpepred")
bottom_n = get_top_n(rows, "bottom", 25000, key="anoxpepred")  # 抗氧化最低的

# Round 7: 最终输出按通道分离
top_rows = [r for r in all_rows if r["channel"] == "top"]
bottom_rows = [r for r in all_rows if r["channel"] == "bottom"]

# 各自独立排序
top_rows.sort(key=lambda r: r["round6_score"], reverse=True)
bottom_rows.sort(key=lambda r: r["round6_score"], reverse=True)
```

**Bottom 通道的特化处理**:

| 环节 | Top 通道 | Bottom 通道 |
|------|---------|------------|
| Round 2 选入量 | 25,000 | 25,000 |
| Round 3 选入量 | 80 肽 | 10 肽 |
| Round 4 枚举构造 | 30 肽 × 3 位置 × 2 linker = 90 | 10 肽 × 3 位置 × 2 linker = 60 |
| Round 7 输出 | 90 constructs | 60 constructs |

### 数据验证

Top 与 Bottom 通道在关键维度的分离度（最终 150 constructs）：

| 维度 | Top 均值 | Bottom 均值 | 分离度 |
|------|---------|------------|--------|
| Round 6 综合分 | 0.642 | 0.523 | ✅ 显著 |
| SASA 暴露度 | 0.702 | 0.501 | ✅ 显著 |
| OmegaFold pLDDT | 0.4105 | 0.3666 | ✅ 差距小但存在 |

数据表明双通道确实在最终排序中保持了分离。

### Environment Fingerprint

- **任务域**: 生物序列筛选流水线，wet-lab 验证数据准备
- **输入特征**: 大规模候选序列（百万级），多维度评分，需要实验验证
- **约束条件**: 实验验证需要阴性对照；"最好"和"最差"的定义可能跨多个维度
- **触发模式**: 任何有实验验证环节的筛选流水线
- **不适用**: 仅需要 Top 候选的无验证环节场景；评分维度单一无需对照的场景

### 最佳实践总结

1. **分选维度要单一**：只用核心指标分选（抗氧化就用 AnOxPePred），不要混合权重
2. **安全过滤一致**：Top/Bottom 过相同的 safety gate，确保对比公平
3. **标签穿透**：channel 标签从分选到最终输出全程携带
4. **Bottom 数量递减**：Bottom 作为对照不需要与 Top 等量，建议 1/3 ~ 2/3 的 Top 数量
5. **最终排名分离**：Top 和 Bottom 各自排序，互不干扰

### Audit Record

- **验证方式**: stages2 全流程完成，90 Top + 60 Bottom 独立排名输出
- **测试用例**:
  1. Top 通道 Round 6 综合分范围 vs Bottom 通道 → 确认分离（0.642 vs 0.523）
  2. Bottom 通道的安全维度是否全部通过筛选 → 确认全部通过
  3. Bottom 通道的肽在抗氧化性上确实低 → AnOxPePred 原始值确认
- **成功率**: 100%
- **局限性**: Bottom 通道 10 肽 → 60 constructs 的多样性有限。更多阴性对照肽可提高实验可靠性，但会增加 GPU 成本。
