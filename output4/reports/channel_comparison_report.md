> **English** | [中文](channel_comparison_report.zh.md)

# Channel Comparison Analysis Report

**Generated**: 2026-05-21 23:04:06
**Data source**: `output4/pipeline_analysis.db` (copy of pipeline.db)
**Time**: 6.1s

---

## Premise validation: antioxidant (AnOxPePred) score distribution

**Question**: Is antioxidant activity in the Top channel really generally higher than in Bottom? If this premise does not hold, the dual-channel design loses its meaning.

| Stage | Top N | Top mean | Top median | Top min | Bottom N | Bottom mean | Bottom median | Bottom max | Gap(Tmin-Bmax) | Overlap? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|
| round1_channels (all assigned to channels)     |  1284119 | 0.3950 | 0.3881 | 0.3654 |   128411 | 0.1739 | 0.1773 | 0.1871 |  0.1783 | ✅ zero overlap    |
| round2_passed (safety passers)                 |   519524 | 0.3935 | 0.3868 | 0.3654 |    74476 | 0.1736 | 0.1771 | 0.1871 |  0.1783 | ✅ zero overlap    |
| round3_scores (deep scoring stage)             |    51227 | 0.4487 | 0.4422 | 0.4266 |    35260 | 0.1700 | 0.1729 | 0.1812 |  0.2454 | ✅ zero overlap    |
| round3_ranking (top 4324 ranked)               |      116 | 0.4534 | 0.4457 | 0.4267 |     4208 | 0.1647 | 0.1685 | 0.1812 |  0.2455 | ✅ zero overlap    |
| final 250 constructs                           |      150 | 0.4530 | 0.4451 | 0.4268 |      100 | 0.1598 | 0.1652 | 0.1798 |  0.2470 | ✅ zero overlap    |

**Conclusion: ✅ the dual-channel antioxidant premise holds.** The minimum AnOxPePred value in the Top channel is always greater than the maximum in the Bottom channel, with **zero overlap at every stage**.
The mean gap between Top and Bottom is about 2.3–2.8×, and as the pipeline advances (rate limiting, safety elimination, deep scoring and ranking) the gap widens further (gap from 0.178 → 0.247).
This confirms that the Round 1 dual-channel split was executed correctly and that later rounds did not degrade the antioxidant separation between the channels.

---

## Core question

> Are sequences in the Bottom channel (low antioxidant) generally better than those in the Top channel (high antioxidant) on **all attributes other than antioxidant activity**?

---

## Summary

| Level | Number of attributes | Bottom better | Top better | No significant difference |
|------|---------|------------|---------|-----------|
| Round 3 deep scoring (86,487 peptides)        |    4 |    3 |    0 |    1 |
| Round 3 top 4,324 ranked                      |    5 |    4 |    0 |    1 |
| Round 4 Phase 1 (2,594 constructs)            |    3 |    2 |    1 |    0 |
| Final 250 constructs                          |   10 |    7 |    3 |    0 |

---

## Level 1: Round 3 deep scoring (86,487 peptides)

Channel comparison across all 5 deep scoring services after ToxinPred3 elimination + rate limiting.

| Attribute | Top N | Top mean±SD | Top median | Bottom N | Bottom mean±SD | Bottom median | Cohen's d | p-value | Direction |
|---|---|---|---|---|---|---|---|---|---|
| BepiPred3 (B-cell epitope)     |  51227 | 0.2491 ± 0.0387 | 0.2535 |  35260 | 0.2466 ± 0.0470 | 0.2514 |  -0.057 | 0.0261 *    | ≈ no significant difference   |
| TemStaPro (thermal stability)  |  51227 | 0.4580 ± 0.1629 | 0.4547 |  35260 | 0.5793 ± 0.1531 | 0.5898 |  +0.763 | 0.0000 ***  | ⬆ Bottom >> Top      |
| SoDoPE (solubility)            |  51227 | 0.5742 ± 0.2882 | 0.6035 |  35260 | 0.8135 ± 0.2057 | 0.8939 |  +0.929 | 0.0000 ***  | ⬆ Bottom >> Top      |
| pLM4CPPs (cell penetration)    |  51227 | 0.0274 ± 0.0690 | 0.0015 |  35260 | 0.1022 ± 0.2551 | 0.0018 |  +0.437 | 0.0000 ***  | ⬆ Bottom >> Top      |
**Interpretation**:

- **BepiPred3 (B-cell epitope)**: ≈ no difference (effect size negligible, d=-0.057)
- **TemStaPro (thermal stability)**: ⬆ Bottom better than Top (effect size medium, d=0.763)
- **SoDoPE (solubility)**: ⬆ Bottom better than Top (effect size large, d=0.929)
- **pLM4CPPs (cell penetration)**: ⬆ Bottom better than Top (effect size small, d=0.437)

---

## Level 2: Round 3 top 4,324 peptides

Candidates entering Round 4 after SD-weighted ranking.

| Attribute | Top N | Top mean±SD | Top median | Bottom N | Bottom mean±SD | Bottom median | Cohen's d | p-value | Direction |
|---|---|---|---|---|---|---|---|---|---|
| Composite (SD-weighted composite)   |    116 | 0.7009 ± 0.0813 | 0.7044 |   4208 | 0.7510 ± 0.0959 | 0.7605 |  +0.524 | 0.0000 ***  | ⬆ Bottom >> Top      |
| BepiPred3 (B-cell epitope)          |    116 | 0.2802 ± 0.0353 | 0.2851 |   4208 | 0.2731 ± 0.0422 | 0.2790 |  -0.167 | 0.0935 n.s. | ≈ no significant difference   |
| TemStaPro (thermal stability)       |    116 | 0.5717 ± 0.2279 | 0.6306 |   4208 | 0.6598 ± 0.1689 | 0.6869 |  +0.516 | 0.0000 ***  | ⬆ Bottom >> Top      |
| SoDoPE (solubility)                 |    116 | 0.9315 ± 0.0702 | 0.9482 |   4208 | 0.9840 ± 0.0326 | 0.9960 |  +1.536 | 0.0000 ***  | ⬆ Bottom >> Top      |
| pLM4CPPs (cell penetration)         |    116 | 0.5587 ± 0.3136 | 0.5517 |   4208 | 0.7102 ± 0.3221 | 0.8596 |  +0.471 | 0.0000 ***  | ⬆ Bottom >> Top      |
**Interpretation**:

- **Composite (SD-weighted composite)**: ⬆ Bottom better than Top (effect size medium, d=0.524)
- **BepiPred3 (B-cell epitope)**: ≈ no difference (effect size negligible, d=-0.167)
- **TemStaPro (thermal stability)**: ⬆ Bottom better than Top (effect size medium, d=0.516)
- **SoDoPE (solubility)**: ⬆ Bottom better than Top (effect size large, d=1.536)
- **pLM4CPPs (cell penetration)**: ⬆ Bottom better than Top (effect size small, d=0.471)

---

## Level 3: Round 4 Phase 1 pass (2,594 constructs)

Constructs entering Phase 2 after SoDoPE + TemStaPro screening.

| Attribute | Top N | Top mean±SD | Top median | Bottom N | Bottom mean±SD | Bottom median | Cohen's d | p-value | Direction |
|---|---|---|---|---|---|---|---|---|---|
| SoDoPE (solubility-construct)    |     10 | 0.7907 ± 0.0296 | 0.7798 |   2584 | 0.8152 ± 0.0361 | 0.8204 |  +0.677 | 0.0184 *    | ⬆ Bottom >> Top      |
| TemStaPro (thermal stability-construct) |     10 | 0.5060 ± 0.0111 | 0.5073 |   2584 | 0.4976 ± 0.0351 | 0.4949 |  -0.241 | 0.1748 n.s. | ⬇ Top >> Bottom      |
| Phase 1 composite score          |     10 | 0.6484 ± 0.0135 | 0.6438 |   2584 | 0.6564 ± 0.0166 | 0.6519 |  +0.481 | 0.0000 ***  | ⬆ Bottom >> Top      |
**Interpretation**:

- **SoDoPE (solubility-construct)**: ⬆ Bottom better than Top (effect size medium, d=0.677)
- **TemStaPro (thermal stability-construct)**: ⬇ Top better than Bottom (effect size small, d=-0.241)
- **Phase 1 composite score**: ⬆ Bottom better than Top (effect size small, d=0.481)

---

## Level 4: Final 250 constructs (core comparison)

The Top 150 + Bottom 100 constructs selected in the end, compared on every dimension.

| Attribute | Top N | Top mean±SD | Top median | Bottom N | Bottom mean±SD | Bottom median | Cohen's d | p-value | Direction |
|---|---|---|---|---|---|---|---|---|---|
| SASA (solvent accessibility)         |    150 | 0.7285 ± 0.0877 | 0.7662 |    100 | 0.6976 ± 0.0619 | 0.6967 |  -0.394 | 0.0007 ***  | ⬇ Top >> Bottom      |
| Aggrescan3D (aggregation risk)       |    150 | 0.3344 ± 0.0203 | 0.3365 |    100 | 0.3136 ± 0.0165 | 0.3140 |  -1.099 | 0.0092 **   | ⬇ Top >> Bottom      |
| pLDDT (structural confidence)        |    150 | 0.4076 ± 0.0154 | 0.4083 |    100 | 0.4400 ± 0.0199 | 0.4364 |  +1.871 | 0.0000 ***  | ⬆ Bottom >> Top      |
| SoDoPE (solubility-construct)        |    150 | 0.7288 ± 0.0339 | 0.7252 |    100 | 0.8540 ± 0.0216 | 0.8544 |  +4.225 | 0.0000 ***  | ⬆ Bottom >> Top      |
| TemStaPro (thermal stability-construct) |    150 | 0.4759 ± 0.0283 | 0.4757 |    100 | 0.5490 ± 0.0265 | 0.5481 |  +2.656 | 0.0000 ***  | ⬆ Bottom >> Top      |
| BepiPred3 (B-cell epitope, peptide level) |    150 | 0.2724 ± 0.0372 | 0.2776 |    100 | 0.2508 ± 0.0330 | 0.2523 |  -0.607 | 0.0000 ***  | ⬇ Top >> Bottom      |
| TemStaPro (thermal stability, peptide level) |    150 | 0.6404 ± 0.2557 | 0.7378 |    100 | 0.7833 ± 0.1302 | 0.8193 |  +0.666 | 0.0000 ***  | ⬆ Bottom >> Top      |
| SoDoPE (solubility, peptide level)   |    150 | 0.9603 ± 0.0445 | 0.9799 |    100 | 0.9996 ± 0.0017 | 0.9999 |  +1.139 | 0.0000 ***  | ⬆ Bottom >> Top      |
| pLM4CPPs (cell penetration, peptide level) |    150 | 0.4803 ± 0.3637 | 0.4076 |    100 | 0.7676 ± 0.3768 | 0.9904 |  +0.778 | 0.0000 ***  | ⬆ Bottom >> Top      |
| Round 7 composite score              |    150 | 0.6128 ± 0.0468 | 0.6248 |    100 | 0.6625 ± 0.0325 | 0.6623 |  +1.192 | 0.0000 ***  | ⬆ Bottom >> Top      |
**Interpretation**:

- **SASA (solvent accessibility)**: ⬇ Top better than Bottom (effect size small, d=-0.394)
- **Aggrescan3D (aggregation risk)**: ⬆ Bottom better than Top (effect size large, d=-1.099) (⚠ Note: lower A3D = lower aggregation risk = better, so Bottom is in fact better)
- **pLDDT (structural confidence)**: ⬆ Bottom better than Top (effect size large, d=1.871)
- **SoDoPE (solubility-construct)**: ⬆ Bottom better than Top (effect size large, d=4.225)
- **TemStaPro (thermal stability-construct)**: ⬆ Bottom better than Top (effect size large, d=2.656)
- **BepiPred3 (B-cell epitope, peptide level)**: ⬇ Top better than Bottom (effect size medium, d=-0.607)
- **TemStaPro (thermal stability, peptide level)**: ⬆ Bottom better than Top (effect size medium, d=0.666)
- **SoDoPE (solubility, peptide level)**: ⬆ Bottom better than Top (effect size large, d=1.139)
- **pLM4CPPs (cell penetration, peptide level)**: ⬆ Bottom better than Top (effect size medium, d=0.778)
- **Round 7 composite score**: ⬆ Bottom better than Top (effect size large, d=1.192)

---

## Conclusion

### Judgment at the level of the final 250 constructs

**Note**: the "good" direction for Aggrescan3D is reversed (lower = lower aggregation risk = better); the counts below have already been corrected.

Among the **10** final attributes (after direction correction):
- **Bottom significantly better than Top (large effect size)**: 8
- **Bottom slightly better than Top (medium/small effect size)**: 0
- **Top significantly better than Bottom**: 1
- **Top slightly better than Bottom**: 1
- **No significant difference**: 0

### Overall conclusion

**Verdict: the observation largely holds.** The Bottom channel is better than Top on 8/10 attributes, and Top is ahead on only 2 attributes (SASA, BepiPred3).

Attributes where Bottom is significantly better: Aggrescan3D (aggregation risk), pLDDT (structural confidence), SoDoPE (solubility-construct), TemStaPro (thermal stability-construct), TemStaPro (thermal stability, peptide level), SoDoPE (solubility, peptide level), pLM4CPPs (cell penetration, peptide level), Round 7 composite score.

Attributes where Top is better: BepiPred3 (B-cell epitope, peptide level), SASA (solvent accessibility).

This may be because:
1. **Antioxidant activity and functional attributes are in an intrinsic trade-off** — highly antioxidant sequences may sacrifice solubility, thermal stability, and other functional attributes
2. **Selection pressure in the Top channel is single-track** — sorting only by AnOxPePred leaves high variance in other attributes; although the Bottom channel is poor on antioxidant activity, after subsequent rounds of screening what remains is in fact better on other attributes
3. **A demonstration that the dual-channel design works** — looking only at antioxidant activity would miss these candidates that are "low antioxidant but highly multi-functional," which is precisely why the Bottom channel exists

### Implications for pipeline design

- The existence of the Bottom channel is proven **valuable** — it does capture candidates that are weak on antioxidant activity but strong on other functions
- That Bottom outranks Top in the final ranking formula is an **expected structural phenomenon** and does not indicate a design error
- For wet-lab validation it is recommended to **select top candidates from both channels**, not only from the Top channel


---

*Analysis script: `main/analysis_validate_channel_claim.py`*
