# Round 5：3D 结构预测 — 报告

**时间**: 2026-05-18 01:02:03
**耗时**: 12605 秒 (210.1 分钟)

## 结果

| 指标 | 值 |
|------|-----|
| 总数 | 150 |
| OmegaFold 成功 | 150/150 |

### pLDDT 分布

**OmegaFold** (n=150): mean=0.4105, median=0.4098, min=0.3666, max=0.4547

## Top 5 by pLDDT

| 排名 | Construct | 肽 | Linker | 位置 | OmegaFold |
|------|-----------|-----|--------|------|-----------|
| 1 | con_0259 | pep_206019 | Flex_GGGGSx1 | N | 0.4547 |
| 2 | con_0247 | pep_895244 | Flex_GGGGSx1 | N | 0.4526 |
| 3 | con_0215 | pep_238278 | Flex_GGGGSx2 | C | 0.4522 |
| 4 | con_0291 | pep_988471 | Flex_GGGGSx1 | Both | 0.4471 |
| 5 | con_0199 | pep_355822 | Flex_GGGGSx1 | N | 0.4460 |

## 输出

```
output2/round05_3d/
├── constructs/con_XXXX/   ← 每个 construct 独立文件夹
│   ├── con_XXXX_omegafold.pdb
│   ├── metadata.json
│   └── scores.json
└── final/
    ├── all_results.csv
    └── round6_input.json
```
