# Round 7：Final Round — iGEM-silk 抗氧化肽融合蛋白最终结果

**生成日期**: 2026-05-18 01:48:21
**Construct 总数**: 150（Top: 90, Bottom: 60）
**骨架**: 丝素蛋白 (~346 aa) + His6 标签
**排名标准**: Round 6 综合评分（SASA × 0.40 + (1-aggrisk) × 0.40 + pLDDT_norm × 0.20）

---

## 全流程回顾（stages2 修复版 ✅）

| 阶段 | 步骤 | 输入 → 输出 | 主要服务 | 说明 |
|------|------|------------|---------|------|
| Step 0 | 数据整合 | 1,081,772 → 1,055,116 | 清洗+去重 | 3-30aa, 标准氨基酸 |
| Round 1 | 轻量评分 | 1,055,116 → Top 50K | AnOxPePred(0.50), ToxinPred3(0.15), AlgPred2(0.10) | 3 并发服务 |
| Round 2 | 追加评分 | 50K → Top 10K | +HemoPI2(0.10), +MHCflurry(0.05) | 复用 Round 1 ToxinPred3 |
| Round 3 | 重服务评分 | 10K → Top 80 + Bottom 10 | +BepiPred3(0.07), +TemStaPro(0.05) | 新增 Bottom-N |
| Round 4 | 枚举+Construct评分 | 40 肽+10 Bottom → ~150 construct | SoDoPE+全长AnOxPePred+BepiPred3 | 新增双通道+活性比 |
| Round 5 | 3D 结构预测 | ~150 construct → PDB | ESMFold + OmegaFold | 双模型并发 |
| Round 6 | PDB 评估 | ~150 PDB → SASA+Aggrescan3D | SASA, Aggrescan3D | 修复文件名 |
| **Round 7** | **最终输出** | **双通道排名→结果包** | — | 修复标签+新增Bottom排名 |

## 排名标准

按 **Round 6 综合分** 从高到低排序。Top 和 Bottom 各自独立排序。

## Top 5

| 排名 | Construct | 肽序列 | 位置 | Linker | SASA | 综合分 | pLDDT |
|------|-----------|--------|------|--------|------|--------|-------|
| 1 | con_0215 | ERELPYYPGAHPMHPPK    | C | Flex_GGGGSx2 | 0.8143 | 0.5244 | 0.4522 |
| 2 | con_0199 | GTHWHPEHF            | N | Flex_GGGGSx1 | 0.7996 | 0.5238 | 0.446 |
| 3 | con_0226 | EPTMYGEILSPNYPQAYPSE | N | Flex_GGGGSx2 | 0.7697 | 0.5206 | 0.4398 |
| 4 | con_0201 | GTHWHPEHF            | Both | Flex_GGGGSx1 | 0.7633 | 0.5291 | 0.4369 |
| 5 | con_0095 | PAFELHYPHMVER        | C | Flex_GGGGSx2 | 0.7212 | 0.5321 | 0.4364 |

## Bottom 5（抗氧化最差但其他安全）

| 排名 | Construct | 肽序列 | 位置 | Linker | SASA | 综合分 | pLDDT |
|------|-----------|--------|------|--------|------|--------|-------|
| 12 | con_0282 | DKKVEKVTISN          | Both | Flex_GGGGSx2 | 0.8205 | 0.4555 | 0.4184 |
| 4 | con_0277 | DKKVEKVTISN          | N | Flex_GGGGSx1 | 0.8035 | 0.4544 | 0.4383 |
| 37 | con_0279 | DKKVEKVTISN          | Both | Flex_GGGGSx1 | 0.8015 | 0.4608 | 0.4135 |
| 5 | con_0288 | ATYKVKDSSVGK         | Both | Flex_GGGGSx2 | 0.8003 | 0.4385 | 0.4325 |
| 28 | con_0297 | EKKVVKITSE           | Both | Flex_GGGGSx1 | 0.7919 | 0.4604 | 0.4148 |

## 分数分布概览

| 维度 | 均值 | 范围 | 样本数 |
|------|------|------|--------|
| Round 6 综合分 | 0.6416 | 0.5234 ~ 0.7794 | 150 |
| SASA 暴露度 | 0.7023 | 0.5007 ~ 0.8306 | 150 |
| construct_composite | 0.492 | 0.385 ~ 0.5482 | 150 |
| OmegaFold pLDDT | 0.4105 | 0.3666 ~ 0.4547 | 150 |
| Aggrescan3D 风险 | 0.3476 | 0.2889 ~ 0.3978 | 150 |

## 输出目录结构

```
output2/round07_final/
├── README.md                        ← 本报告（含 Top + Bottom 对比）
├── top_ranking.csv                  ← Top constructs 排名
├── top10_summary.csv                ← Top 10 精简表
├── bottom_ranking.csv               ← Bottom constructs 排名（仅当有 Bottom 时）
├── bottom10_summary.csv             ← Bottom 10 精简表
├── score_distribution.json          ← 各分数维度分布统计
└── constructs/                      ← 每个 construct 独立文件夹
    ├── con_0001_pep000743_N_top/
    │   ├── construct.fasta
    │   ├── construct_omegafold.pdb
    │   ├── scores.json
    │   └── metadata.json
    └── ...（共 150 个文件夹）
```

## 注意事项

- **Top 排名**: 综合分最高的功能肽融合 construct
- **Bottom 排名**: 抗氧化活性（AnOxPePred）最低、但所有安全维度（毒性/致敏/溶血/免疫/B 细胞）均通过阈值的 construct，作为阴性对照
- OmegaFold pLDDT 均值约 0.42，属于中等偏低置信度，SASA/A3D 结果仅供参考
- 建议选取 Top 5-10 进行 wet-lab 验证
