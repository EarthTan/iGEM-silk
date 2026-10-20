> **English** | [中文](README.zh.md)

# Round 7: Final Round — iGEM-silk Antioxidant Peptide Fusion Protein Final Results

**Generated**: 2026-05-18 01:48:21
**Total constructs**: 150 (Top: 90, Bottom: 60)
**Scaffold**: silk fibroin (~346 aa) + His6 tag
**Ranking criterion**: Round 6 composite score (SASA × 0.40 + (1-aggrisk) × 0.40 + pLDDT_norm × 0.20)

---

## Full Pipeline Retrospective (stages2 fixed version ✅)

| Stage | Step | Input → Output | Main services | Notes |
|------|------|------------|---------|------|
| Step 0 | data integration | 1,081,772 → 1,055,116 | cleaning + deduplication | 3-30aa, standard amino acids |
| Round 1 | lightweight scoring | 1,055,116 → Top 50K | AnOxPePred(0.50), ToxinPred3(0.15), AlgPred2(0.10) | 3 concurrent services |
| Round 2 | additional scoring | 50K → Top 10K | +HemoPI2(0.10), +MHCflurry(0.05) | reuses the Round 1 ToxinPred3 scores |
| Round 3 | heavy-service scoring | 10K → Top 80 + Bottom 10 | +BepiPred3(0.07), +TemStaPro(0.05) | Bottom-N newly added |
| Round 4 | enumeration + construct scoring | 40 peptides + 10 Bottom → ~150 constructs | SoDoPE + full-length AnOxPePred + BepiPred3 | dual-channel + activity ratio newly added |
| Round 5 | 3D structure prediction | ~150 constructs → PDB | ESMFold + OmegaFold | two models in parallel |
| Round 6 | PDB evaluation | ~150 PDBs → SASA+Aggrescan3D | SASA, Aggrescan3D | file names fixed |
| **Round 7** | **final output** | **dual-channel ranking → result package** | — | labels fixed + Bottom ranking added |

## Ranking Criterion

Sorted from high to low by the **Round 6 composite score**. Top and Bottom are ranked independently.

## Top 5

| Rank | Construct | Peptide sequence | Position | Linker | SASA | Composite score | pLDDT |
|------|-----------|--------|------|--------|------|--------|-------|
| 1 | con_0215 | ERELPYYPGAHPMHPPK    | C | Flex_GGGGSx2 | 0.8143 | 0.5244 | 0.4522 |
| 2 | con_0199 | GTHWHPEHF            | N | Flex_GGGGSx1 | 0.7996 | 0.5238 | 0.446 |
| 3 | con_0226 | EPTMYGEILSPNYPQAYPSE | N | Flex_GGGGSx2 | 0.7697 | 0.5206 | 0.4398 |
| 4 | con_0201 | GTHWHPEHF            | Both | Flex_GGGGSx1 | 0.7633 | 0.5291 | 0.4369 |
| 5 | con_0095 | PAFELHYPHMVER        | C | Flex_GGGGSx2 | 0.7212 | 0.5321 | 0.4364 |

## Bottom 5 (worst antioxidant capacity but otherwise safe)

| Rank | Construct | Peptide sequence | Position | Linker | SASA | Composite score | pLDDT |
|------|-----------|--------|------|--------|------|--------|-------|
| 12 | con_0282 | DKKVEKVTISN          | Both | Flex_GGGGSx2 | 0.8205 | 0.4555 | 0.4184 |
| 4 | con_0277 | DKKVEKVTISN          | N | Flex_GGGGSx1 | 0.8035 | 0.4544 | 0.4383 |
| 37 | con_0279 | DKKVEKVTISN          | Both | Flex_GGGGSx1 | 0.8015 | 0.4608 | 0.4135 |
| 5 | con_0288 | ATYKVKDSSVGK         | Both | Flex_GGGGSx2 | 0.8003 | 0.4385 | 0.4325 |
| 28 | con_0297 | EKKVVKITSE           | Both | Flex_GGGGSx1 | 0.7919 | 0.4604 | 0.4148 |

## Score Distribution Overview

| Dimension | Mean | Range | Sample count |
|------|------|------|--------|
| Round 6 composite score | 0.6416 | 0.5234 ~ 0.7794 | 150 |
| SASA exposure | 0.7023 | 0.5007 ~ 0.8306 | 150 |
| construct_composite | 0.492 | 0.385 ~ 0.5482 | 150 |
| OmegaFold pLDDT | 0.4105 | 0.3666 ~ 0.4547 | 150 |
| Aggrescan3D risk | 0.3476 | 0.2889 ~ 0.3978 | 150 |

## Output Directory Structure

```
output2/round07_final/
├── README.md                        ← this report (with Top + Bottom comparison)
├── top_ranking.csv                  ← Top constructs ranking
├── top10_summary.csv                ← condensed Top 10 table
├── bottom_ranking.csv               ← Bottom constructs ranking (only when there is a Bottom)
├── bottom10_summary.csv             ← condensed Bottom 10 table
├── score_distribution.json          ← distribution statistics for each score dimension
└── constructs/                      ← a separate folder per construct
    ├── con_0001_pep000743_N_top/
    │   ├── construct.fasta
    │   ├── construct_omegafold.pdb
    │   ├── scores.json
    │   └── metadata.json
    └── ... (150 folders in total)
```

## Notes

- **Top ranking**: functional peptide fusion constructs with the highest composite score
- **Bottom ranking**: constructs with the lowest antioxidant activity (AnOxPePred) but passing the thresholds in all safety dimensions (toxicity/allergenicity/hemolysis/immunogenicity/B-cell), serving as negative controls
- The mean OmegaFold pLDDT is about 0.42, which is a medium-to-low confidence level; the SASA/A3D results are for reference only
- Recommend selecting Top 5-10 for wet-lab validation
