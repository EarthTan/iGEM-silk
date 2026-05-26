# Round 4 Construct 枚举 + 评分报告

## 设计决策

| 决策 | 结论 |
|------|------|
| His-tag 重复 | silk.fasta 自带 LEHHHHHH 已去除，仅 build_full_sequence 追加一次 |
| AnOxPePred | 跳过 — 截断到 30aa 导致 C/Both 位置不可靠 |
| 枚举规模 | 全量 4,324 肽 × 6 combos = 25,944 constructs |
| Phase 1 筛选 | SoDoPE+TemStaPro 综合分 Top 10% |
| Phase 2 | BepiPred3 只跑 Phase 1 子集 |

## Phase 1: 枚举 + SoDoPE + TemStaPro

运行时间: 23:24 → 23:40 (15.9 min)

| 项目 | 数值 |
|------|------|
| 输入肽 | 4,324 (116 Top + 4,208 Bottom) |
| 枚举 constructs | 25,944 (Top 696 + Bottom 25,248) |
| SoDoPE + TemStaPro 评分 | 25,944 ✅ |
| 综合分范围 | 0.0012 – 0.7218 (avg ~0.53) |
| 筛选 Top 10% | 2,594 constructs |
| His-tag | 骨架去重: 364aa (原 372aa) ✅ |

SoDoPE 极快 (<3s)，TemStaPro 在 400aa 序列上实际吞吐 ~5.5 seq/s（比 166/s 慢很多）。

## Phase 2: BepiPred3 补充评分

运行时间: 00:01 → 01:46 (104.8 min)

| 项目 | 数值 |
|------|------|
| 输入 constructs | 2,594 (Phase 1 Top 10%) |
| BATCH_SIZE | 50 |
| 实际耗时 | 6,285s (104.8 min) — 接近预估的 1.7h |
| BepiPred3 评分 | **2,594/2,594 ✅ (100%)** |
| 分数范围 | 0.1206 – 0.1625 |
| 平均值 | 0.1472 |
| 标准差 | **0.0053**（极低区分度） |

### BepiPred3 区分度分析

BepiPred3 在 construct 级别的区分度极低 (SD=0.0053)，远低于 Round 3 肽级别 (SD=0.042)。
主要原因：400aa 全长序列中 ~90% 是共享的骨架 + linker，只有 ~10% 是功能肽。
B 细胞表位预测主要被骨架序列驱动，不同 construct 之间的差异被淹没。

结论：**construct 级别的 BepiPred3 对筛选帮助有限**，后续 round 应考虑使用 Round 3 肽级别的 BepiPred3 分数。

## 位置分布 (Phase 1 通过的 2,594 constructs)

| 位置 | 数量 | 占比 |
|------|------|------|
| Both | 2,249 | 86.7% |
| C | 265 | 10.2% |
| N | 80 | 3.1% |

"Both" 位置因双拷贝功能肽，在 SoDoPE (溶解度) 和 TemStaPro (热稳定) 上显著更优。

## 通道分布

| 通道 | 数量 |
|------|------|
| Top | 10 |
| Bottom | 2,584 |

Bottom 通道占绝对多数 — 与 Round 3 排名一致（Bottom 通道的 composite_score 最高达 0.948，高于 Top 的 0.870）。

## 关键发现

1. **His-tag 修复成功**：骨架去重 + 统一追加，无重复
2. **TemStaPro 在长序列上比预期慢**（5.5/s vs 166/s），但 Phase 1 整体仍在 16 min 完成
3. **BepiPred3 construct 级别区分度极低** (SD=0.005)，后续 round 可考虑跳过 construct 级别 BepiPred3
4. **"Both" 位置在 SoDoPE+TemStaPro 上表现最好**（86.7% of Top 10%）
