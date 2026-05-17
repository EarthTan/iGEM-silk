# Round 4：枚举 + Construct 级评分 — 报告

**时间**: 2026-05-17 20:51:06
**耗时**: 434 秒

## 评分权重

| 维度 | 权重 | 说明 |
|------|------|------|
| 肽综合分（Round 3） | 0.4 | 7 服务加权综合分 |
| SoDoPE 溶解度 | 0.25 | Construct 级全长评分 |
| **Construct AnOxPePred** | 0.2 | **新增**：全长融合蛋白抗氧化评分 |
| **Construct BepiPred3** | 0.1 | **新增**：全长融合蛋白 B 细胞表位 |
| TemStaPro 热稳定性 | 0.05 | — |

## 双通道枚举

| 通道 | 肽数 | Linker | 位置 | Construct 数 | 输出数 |
|------|------|--------|------|-------------|--------|
| Top | 40 | 2 | 3 | 240 | 90 |
| Bottom | 10 | 2 | 3 | 60 | 60 |

## 活性变化比

AnOxPePred 活性下降警告（变化比 < 0.8）: 230 个

变化比 > 1.0 = 融合后活性增强 | ≈ 1.0 = 不受 scaffold 影响 | < 0.8 = 显著下降

## Top 分组摘要

| 排名 | 肽 | Linker | N/C/Both 分 | 组最高分 |
|------|------|--------|-------------|----------|
|  1 | pep_977590   | Flex_GGGGSx2              | Both=0.5940 | C=0.5765 | N=0.5912 | 0.5940 |
|  2 | pep_977590   | Flex_GGGGSx1              | Both=0.5928 | C=0.5788 | N=0.5902 | 0.5928 |
|  3 | pep_238278   | Flex_GGGGSx2              | Both=0.5916 | C=0.5671 | N=0.5829 | 0.5916 |
|  4 | pep_033299   | Flex_GGGGSx2              | Both=0.5914 | C=0.5585 | N=0.5791 | 0.5914 |
|  5 | pep_954776   | Flex_GGGGSx2              | Both=0.5905 | C=0.5749 | N=0.5847 | 0.5905 |
|  6 | pep_954776   | Flex_GGGGSx1              | Both=0.5873 | C=0.5762 | N=0.5838 | 0.5873 |
|  7 | pep_238278   | Flex_GGGGSx1              | Both=0.5869 | C=0.5685 | N=0.5788 | 0.5869 |
|  8 | pep_033299   | Flex_GGGGSx1              | Both=0.5858 | C=0.5590 | N=0.5769 | 0.5858 |
|  9 | pep_648372   | Flex_GGGGSx2              | Both=0.5853 | C=0.5670 | N=0.5766 | 0.5853 |
| 10 | pep_648372   | Flex_GGGGSx1              | Both=0.5831 | C=0.5681 | N=0.5762 | 0.5831 |
| 11 | pep_355822   | Flex_GGGGSx2              | Both=0.5817 | C=0.5639 | N=0.5760 | 0.5817 |
| 12 | pep_679714   | Flex_GGGGSx1              | Both=0.5810 | C=0.5777 | N=0.5804 | 0.5810 |
| 13 | pep_648371   | Flex_GGGGSx2              | Both=0.5810 | C=0.5678 | N=0.5716 | 0.5810 |
| 14 | pep_679714   | Flex_GGGGSx2              | Both=0.5778 | C=0.5759 | N=0.5738 | 0.5778 |
| 15 | pep_432652   | Flex_GGGGSx2              | Both=0.5773 | C=0.5645 | N=0.5709 | 0.5773 |
| 16 | pep_648371   | Flex_GGGGSx1              | Both=0.5765 | C=0.5683 | N=0.5677 | 0.5765 |
| 17 | pep_164493   | Flex_GGGGSx1              | Both=0.5742 | C=0.5598 | N=0.5718 | 0.5742 |
| 18 | pep_355822   | Flex_GGGGSx1              | Both=0.5734 | C=0.5648 | N=0.5676 | 0.5734 |
| 19 | pep_020977   | Flex_GGGGSx2              | Both=0.5728 | C=0.5715 | N=0.5667 | 0.5728 |
| 20 | pep_432652   | Flex_GGGGSx1              | Both=0.5727 | C=0.5639 | N=0.5690 | 0.5727 |
| 21 | pep_020977   | Flex_GGGGSx1              | Both=0.5668 | C=0.5727 | N=0.5606 | 0.5727 |
| 22 | pep_142399   | Flex_GGGGSx1              | Both=0.5657 | C=0.5721 | N=0.5610 | 0.5721 |
| 23 | pep_164493   | Flex_GGGGSx2              | Both=0.5710 | C=0.5595 | N=0.5676 | 0.5710 |
| 24 | pep_142399   | Flex_GGGGSx2              | Both=0.5689 | C=0.5706 | N=0.5644 | 0.5706 |
| 25 | pep_252920   | Flex_GGGGSx1              | Both=0.5704 | C=0.5602 | N=0.5675 | 0.5704 |
| 26 | pep_299544   | Flex_GGGGSx1              | Both=0.5620 | C=0.5595 | N=0.5701 | 0.5701 |
| 27 | pep_252920   | Flex_GGGGSx2              | Both=0.5698 | C=0.5591 | N=0.5658 | 0.5698 |
| 28 | pep_233907   | Flex_GGGGSx2              | Both=0.5671 | C=0.5515 | N=0.5645 | 0.5671 |
| 29 | pep_216524   | Flex_GGGGSx2              | Both=0.5670 | C=0.5663 | N=0.5622 | 0.5670 |
| 30 | pep_216524   | Flex_GGGGSx1              | Both=0.5615 | C=0.5667 | N=0.5567 | 0.5667 |

## 分数分布

- **综合分**: n=300, mean=0.5362, max=0.5940
- **SoDoPE**: n=300, mean=0.6731
- **Construct AnOxPePred**: n=300, mean=0.3096

## 输出

- `final/constructs_top.csv` — Top 90 constructs
- `final/constructs_bottom.csv` — Bottom 60 constructs
- `final/all_constructs.fasta` — 150 条 → Round 5 3D 预测
- `final/context_effect.csv` — 游离 vs 融合活性变化
