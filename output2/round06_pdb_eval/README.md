# Round 6：PDB 评估 — 报告

**时间**: 2026-05-18 01:47:07
**耗时**: 357 秒 (6.0 分钟)
**Construct 数**: 150

## 评分公式

```
round6_score = 0.4 * SASA_exposure
             + 0.4 * (1 - aggrisk)
             + 0.2 * pLDDT_norm
```

## 分数分布

- **construct_composite（肽功能+SoDoPE+TemStaPro）**: mean=0.4920, median=0.5207, range=[0.3850, 0.5482]
- **OmegaFold pLDDT**: mean=0.4105, median=0.4098, range=[0.3666, 0.4547]
- **SASA 功能肽暴露度**: mean=0.7023, median=0.7219, range=[0.5007, 0.8306]
- **Aggrescan3D 聚集风险**: mean=0.3476, median=0.3477, range=[0.2889, 0.3978]
- **Round 6 综合评分**: mean=0.6416, median=0.6358, range=[0.5234, 0.7794]

## Top 5

| 排名 | Construct | 肽 | 分量 | Round6 |
|------|-----------|-----|------|--------|
| 1 | con_0215 | pep_238278 | cc=0.524 sasa=0.814 agg=0.351 | **0.7794** |
| 2 | con_0199 | pep_355822 | cc=0.524 sasa=0.800 agg=0.329 | **0.7684** |
| 3 | con_0256 | pep_889620 | cc=0.431 sasa=0.781 agg=0.289 | **0.7485** |
| 4 | con_0277 | pep_140158 | cc=0.454 sasa=0.803 agg=0.348 | **0.7451** |
| 5 | con_0288 | pep_078551 | cc=0.439 sasa=0.800 agg=0.321 | **0.7412** |

## 输出

- `final/sasa_ranking.csv` — 全部 150 个 construct 排名（含 channel 标签）
- `final/score_distribution.json` — 各分数维度分布统计
- `raw/sasa_results.json` — SASA 原始返回
- `raw/aggrescan3d_results.json` — Aggrescan3D 原始返回
