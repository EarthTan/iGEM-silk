> **English** | [中文](README.zh.md)

# Round 6: PDB Evaluation — Report

**Time**: 2026-05-18 01:47:07
**Duration**: 357 seconds (6.0 minutes)
**Constructs**: 150

## Scoring Formula

```
round6_score = 0.4 * SASA_exposure
             + 0.4 * (1 - aggrisk)
             + 0.2 * pLDDT_norm
```

## Score Distributions

- **construct_composite (peptide function + SoDoPE + TemStaPro)**: mean=0.4920, median=0.5207, range=[0.3850, 0.5482]
- **OmegaFold pLDDT**: mean=0.4105, median=0.4098, range=[0.3666, 0.4547]
- **SASA functional peptide exposure**: mean=0.7023, median=0.7219, range=[0.5007, 0.8306]
- **Aggrescan3D aggregation risk**: mean=0.3476, median=0.3477, range=[0.2889, 0.3978]
- **Round 6 composite score**: mean=0.6416, median=0.6358, range=[0.5234, 0.7794]

## Top 5

| Rank | Construct | Peptide | Components | Round6 |
|------|-----------|-----|------|--------|
| 1 | con_0215 | pep_238278 | cc=0.524 sasa=0.814 agg=0.351 | **0.7794** |
| 2 | con_0199 | pep_355822 | cc=0.524 sasa=0.800 agg=0.329 | **0.7684** |
| 3 | con_0256 | pep_889620 | cc=0.431 sasa=0.781 agg=0.289 | **0.7485** |
| 4 | con_0277 | pep_140158 | cc=0.454 sasa=0.803 agg=0.348 | **0.7451** |
| 5 | con_0288 | pep_078551 | cc=0.439 sasa=0.800 agg=0.321 | **0.7412** |

## Output

- `final/sasa_ranking.csv` — ranking of all 150 constructs (with channel labels)
- `final/score_distribution.json` — distribution statistics for each score dimension
- `raw/sasa_results.json` — raw SASA responses
- `raw/aggrescan3d_results.json` — raw Aggrescan3D responses
