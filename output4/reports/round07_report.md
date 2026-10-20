> **English** | [中文](round07_report.zh.md)

# Round 7: Final Round — Final Ranking Report

**Generated**: 2026-05-21 10:20:59
**Total constructs**: 250 (Top: 150, Bottom: 100)
**Time**: 0s (0.0 min)

## Full pipeline retrospective

| Round | Description | Key services | Time |
|------|------|---------|------|
| Round 1 | peptide-level primary screening + channel split | AnOxPePred, AlgPred2, ToxinPred3, HemoPI2, MHCflurry | — |
| Round 2 | safety filtering | ToxinPred3, AlgPred2, HemoPI2 | — |
| Round 3 | heavy-service scoring + GraphCPP + ranking | BepiPred3, TemStaPro, SoDoPE, pLM4CPPs, GraphCPP | ~82 min |
| Round 4 Phase 1 | enumerate 4,324 peptides → 25,944 constructs + SoDoPE/TemStaPro | SoDoPE, TemStaPro | 16 min |
| Round 4 Phase 2 | BepiPred3 supplementary scoring (top 10%) | BepiPred3 | 105 min |
| Round 5 | OmegaFold 3D structure prediction (Top 150 + Bottom 100) | OmegaFold | 6.13h |
| Round 6 | SASA + Aggrescan3D evaluation | SASA, Aggrescan3D | 5.4 min |
| **Round 7** | **final ranking** | — | **0s** |

## Ranking formula

```
round7_score = 0.4 × SASA + 0.4 × (1 − Aggrescan3D) + 0.2 × pLDDT_norm
```

| Dimension | Weight | Direction | Meaning |
|------|------|------|------|
| SASA | 0.4 | ↑ higher is better | solvent accessibility of the functional peptide region (exposed on the outside for immune recognition) |
| 1 − Aggrescan3D | 0.4 | ↑ higher is better | inverse aggregation risk (less prone to aggregation means higher expression) |
| pLDDT_norm | 0.2 | ↑ higher is better | structural confidence after min−max normalization (reliable structure) |

## Top 10

| Rank | Channel | ID | Position | Linker | Peptide sequence | SASA | A3D | pLDDT | Total score |
|------|------|----|------|--------|--------|------|-----|-------|------|
| 9 | top | 418 | C    | Flex_GGGGSx2 | MNRPWITGHHHHHHHRRRRR | 0.8104 | 0.3219 | 0.4420 | 0.7076 |
| 13 | top | 417 | C    | Flex_GGGGSx1 | MNRPWITGHHHHHHHRRRRR | 0.7844 | 0.3557 | 0.4514 | 0.6993 |
| 17 | top | 317 | Both | Flex_GGGGSx1 | MARKKPKGYGYVHVKYKQRK | 0.8228 | 0.3598 | 0.4386 | 0.6918 |
| 19 | top | 850 | C    | Flex_GGGGSx2 | MLDRRGGGRGEGGAPPPPPH | 0.7972 | 0.3345 | 0.4372 | 0.6893 |
| 37 | top | 558 | Both | Flex_GGGGSx2 | GERSGGVVRGGHPPHAPRRA | 0.8158 | 0.3259 | 0.4203 | 0.6723 |
| 39 | top | 561 | C    | Flex_GGGGSx1 | MEKGKTEWDYRYPKQHWYKK | 0.7296 | 0.3439 | 0.4448 | 0.6711 |
| 47 | top | 660 | Both | Flex_GGGGSx2 | MERRRAVCGGEGPPGPGRRG | 0.8189 | 0.3321 | 0.4183 | 0.6676 |
| 49 | top | 521 | Both | Flex_GGGGSx1 | MGVGVGDGERVHAHMHTHMH | 0.7722 | 0.3512 | 0.4338 | 0.6671 |
| 50 | top | 768 | Both | Flex_GGGGSx2 | MKNPLQEVTPAGHPHKRKFP | 0.8201 | 0.3167 | 0.4140 | 0.6671 |
| 57 | top | 322 | C    | Flex_GGGGSx2 | MDVRTTVILKTNRHPPPKKK | 0.6506 | 0.3509 | 0.4614 | 0.6642 |

## Bottom 10

| Rank | Channel | ID | Position | Linker | Peptide sequence | SASA | A3D | pLDDT | Total score |
|------|------|----|------|--------|--------|------|-----|-------|------|
| 1 | bottom | 5489 | Both | Flex_GGGGSx1 | KKKEKKKEEKKKRQKNRKKK | 0.6873 | 0.2925 | 0.4950 | 0.7579 |
| 2 | bottom | 3275 | Both | Flex_GGGGSx1 | KRKKKKIREKKKRKKNKKKK | 0.6861 | 0.2927 | 0.4857 | 0.7420 |
| 3 | bottom | 1415 | Both | Flex_GGGGSx1 | MEEEKKKEKRKKKEKRKKKK | 0.7055 | 0.3301 | 0.4854 | 0.7342 |
| 4 | bottom | 15869 | Both | Flex_GGGGSx1 | KKMNGGKKGGKRGEKKEEKK | 0.8229 | 0.2753 | 0.4410 | 0.7296 |
| 5 | bottom | 1103 | Both | Flex_GGGGSx1 | MREKEEKKKRKEKKEKRKKK | 0.6777 | 0.2946 | 0.4743 | 0.7189 |
| 6 | bottom | 2075 | Both | Flex_GGGGSx1 | KKKDKKIRIKKKRQKKKEKK | 0.6526 | 0.2927 | 0.4791 | 0.7176 |
| 7 | bottom | 3774 | Both | Flex_GGGGSx2 | MTEQDPVKEKKKKEKKRKKK | 0.7223 | 0.3176 | 0.4644 | 0.7113 |
| 8 | bottom | 1308 | Both | Flex_GGGGSx2 | MKEGETPRLPKKKKKKKKKK | 0.7896 | 0.2937 | 0.4424 | 0.7112 |
| 10 | bottom | 2015 | Both | Flex_GGGGSx1 | KERKKGEKKKKKKKRKKKKN | 0.6938 | 0.2822 | 0.4602 | 0.7070 |
| 11 | bottom | 1541 | Both | Flex_GGGGSx1 | KKKEKKKVRKKKKKKKRKYK | 0.6831 | 0.3056 | 0.4659 | 0.7027 |

## Score distribution

| Dimension | Mean | Range | Sample count |
|------|------|------|--------|
| Round 7 composite score | 0.6327 | 0.4800 ~ 0.7579 | 250 |
| SASA exposure | 0.7161 | 0.4601 ~ 0.8322 | 250 |
| Aggrescan3D aggregation risk | 0.3261 | 0.2696 ~ 0.3857 | 250 |
| OmegaFold pLDDT | 0.4205 | 0.3742 ~ 0.4950 | 250 |
| SoDoPE solubility | 0.7789 | 0.6726 ~ 0.8959 | 250 |
| TemStaPro thermal stability | 0.5051 | 0.3901 ~ 0.6517 | 250 |

## Output files

| File | Description |
|------|------|
| `reports/top_ranking.csv` | complete ranking of the 150 Top-channel constructs |
| `reports/bottom_ranking.csv` | complete ranking of the 100 Bottom-channel constructs |
| `reports/round07_report.md` | this report |

## Recommendation

It is recommended to select the Top 5–10 for wet-lab validation.
