> **English** | [中文](README.zh.md)

# iGEM-silk Stages4 Final Results

**Generated**: 2026-05-21 10:35:53
**Total constructs**: 250 (Top: 150, Bottom: 100)
**Time**: 1s

## Ranking formula

```
round7_score = 0.4×SASA + 0.4×(1−A3D) + 0.2×pLDDT_norm
```

## Top 5 (ranked within each channel)

| Global rank | Channel | ID | Position | Linker | SASA | A3D | pLDDT | Total score |
|---------|------|----|------|--------|------|-----|-------|------|
| 9 | top | con_0418 | C    | Flex_GGGGSx2 | 0.8104 | 0.3219 | 0.4420 | 0.7076 |
| 13 | top | con_0417 | C    | Flex_GGGGSx1 | 0.7844 | 0.3557 | 0.4514 | 0.6993 |
| 17 | top | con_0317 | Both | Flex_GGGGSx1 | 0.8228 | 0.3598 | 0.4386 | 0.6918 |
| 19 | top | con_0850 | C    | Flex_GGGGSx2 | 0.7972 | 0.3345 | 0.4372 | 0.6893 |
| 37 | top | con_0558 | Both | Flex_GGGGSx2 | 0.8158 | 0.3259 | 0.4203 | 0.6723 |

## Bottom 5

| Global rank | Channel | ID | Position | Linker | SASA | A3D | pLDDT | Total score |
|---------|------|----|------|--------|------|-----|-------|------|
| 1 | bottom | con_5489 | Both | Flex_GGGGSx1 | 0.6873 | 0.2925 | 0.4950 | 0.7579 |
| 2 | bottom | con_3275 | Both | Flex_GGGGSx1 | 0.6861 | 0.2927 | 0.4857 | 0.7420 |
| 3 | bottom | con_1415 | Both | Flex_GGGGSx1 | 0.7055 | 0.3301 | 0.4854 | 0.7342 |
| 4 | bottom | con_15869 | Both | Flex_GGGGSx1 | 0.8229 | 0.2753 | 0.4410 | 0.7296 |
| 5 | bottom | con_1103 | Both | Flex_GGGGSx1 | 0.6777 | 0.2946 | 0.4743 | 0.7189 |

## Quick reference (CSV summary)

| File | Contents |
|------|------|
| `top10.csv` | Summary of the top 10 constructs in the Top channel |
| `bottom10.csv` | Summary of the top 10 constructs in the Bottom channel |

CSV fields: `global_rank`, `channel`, `channel_rank`, `construct_id`, `position`, `linker`, `peptide_seq`, `source_database`, `source_accession`, `round7_score`

## Output structure

```
output4/final/
├── README.md                           ← this file
├── top10.csv                           ← Top 10 summary
├── bottom10.csv                        ← Bottom 10 summary
└── constructs/
    ├── con_0293/
    │   ├── construct.json              ← all scores, rankings, source information
    │   └── omegafold.pdb               ← 3D structure predicted by OmegaFold
    ├── con_0294/
    │   ├── construct.json
    │   └── omegafold.pdb
    └── ...                             ← 250 constructs in total
```

## Description of each construct JSON

Top-level fields of `construct.json`:
- `construct_id`, `candidate_id` — database ID
- `channel` — Top / Bottom channel
- `position` — functional peptide insertion position (N/C/Both)
- `linker` — linker peptide type
- `sequences` — sequence of each segment (scaffold / linker / peptide / full length)
- `source` — source database (uniprot/mgy) + accession + header
- `scores.round1` — AnOxPePred, AlgPred2
- `scores.round2` — ToxinPred3, HemoPI2, MHCflurry
- `scores.round3` — BepiPred3, TemStaPro, SoDoPE, pLM4CPPs, GraphCPP
- `scores.construct` — construct-level SoDoPE, TemStaPro, BepiPred3
- `scores.structure` — OmegaFold pLDDT
- `scores.pdb_eval` — SASA, Aggrescan3D
- `rankings` — rankings at each stage (round1/round3/round4/round7)
