# iGEM-silk Stages4 最终结果

**生成日期**: 2026-05-21 10:35:53
**Construct 总数**: 250（Top: 150, Bottom: 100）
**耗时**: 1s

## 排名公式

```
round7_score = 0.4×SASA + 0.4×(1−A3D) + 0.2×pLDDT_norm
```

## Top 5（按通道各自排名）

| 全局排名 | 通道 | ID | 位置 | Linker | SASA | A3D | pLDDT | 总分 |
|---------|------|----|------|--------|------|-----|-------|------|
| 9 | top | con_0418 | C    | Flex_GGGGSx2 | 0.8104 | 0.3219 | 0.4420 | 0.7076 |
| 13 | top | con_0417 | C    | Flex_GGGGSx1 | 0.7844 | 0.3557 | 0.4514 | 0.6993 |
| 17 | top | con_0317 | Both | Flex_GGGGSx1 | 0.8228 | 0.3598 | 0.4386 | 0.6918 |
| 19 | top | con_0850 | C    | Flex_GGGGSx2 | 0.7972 | 0.3345 | 0.4372 | 0.6893 |
| 37 | top | con_0558 | Both | Flex_GGGGSx2 | 0.8158 | 0.3259 | 0.4203 | 0.6723 |

## Bottom 5

| 全局排名 | 通道 | ID | 位置 | Linker | SASA | A3D | pLDDT | 总分 |
|---------|------|----|------|--------|------|-----|-------|------|
| 1 | bottom | con_5489 | Both | Flex_GGGGSx1 | 0.6873 | 0.2925 | 0.4950 | 0.7579 |
| 2 | bottom | con_3275 | Both | Flex_GGGGSx1 | 0.6861 | 0.2927 | 0.4857 | 0.7420 |
| 3 | bottom | con_1415 | Both | Flex_GGGGSx1 | 0.7055 | 0.3301 | 0.4854 | 0.7342 |
| 4 | bottom | con_15869 | Both | Flex_GGGGSx1 | 0.8229 | 0.2753 | 0.4410 | 0.7296 |
| 5 | bottom | con_1103 | Both | Flex_GGGGSx1 | 0.6777 | 0.2946 | 0.4743 | 0.7189 |

## 快速查阅（CSV 摘要）

| 文件 | 内容 |
|------|------|
| `top10.csv` | Top 通道排名前 10 的 constructs 摘要 |
| `bottom10.csv` | Bottom 通道排名前 10 的 constructs 摘要 |

CSV 字段：`global_rank`, `channel`, `channel_rank`, `construct_id`, `position`, `linker`, `peptide_seq`, `source_database`, `source_accession`, `round7_score`

## 输出结构

```
output4/final/
├── README.md                           ← 本文件
├── top10.csv                           ← Top 10 摘要
├── bottom10.csv                        ← Bottom 10 摘要
└── constructs/
    ├── con_0293/
    │   ├── construct.json              ← 全部评分、排名、来源信息
    │   └── omegafold.pdb               ← OmegaFold 预测的 3D 结构
    ├── con_0294/
    │   ├── construct.json
    │   └── omegafold.pdb
    └── ...                             ← 共 250 个 construct
```

## 各 construct JSON 内容说明

`construct.json` 顶层字段：
- `construct_id`, `candidate_id` — 数据库 ID
- `channel` — Top / Bottom 通道
- `position` — 功能肽插入位置 (N/C/Both)
- `linker` — 连接肽类型
- `sequences` — 各片段序列（scaffold / linker / peptide / 全长）
- `source` — 来源数据库 (uniprot/mgy) + accession + header
- `scores.round1` — AnOxPePred, AlgPred2
- `scores.round2` — ToxinPred3, HemoPI2, MHCflurry
- `scores.round3` — BepiPred3, TemStaPro, SoDoPE, pLM4CPPs, GraphCPP
- `scores.construct` — construct 级别 SoDoPE, TemStaPro, BepiPred3
- `scores.structure` — OmegaFold pLDDT
- `scores.pdb_eval` — SASA, Aggrescan3D
- `rankings` — 各阶段排名 (round1/round3/round4/round7)
