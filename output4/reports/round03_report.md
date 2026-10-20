> **English** | [中文](round03_report.zh.md)

# Round 3 Deep Scoring Report

## Overview

Deep scoring + ToxinPred3 hard threshold + variance-weighted ranking + GraphCPP supplementary scoring.
Two-phase design: Phase 1 runs 5 services (BepiPred3/TemStaPro/SoDoPE/pLM4CPPs/ToxinPred3),
Phase 2 runs GraphCPP on the Round 4 candidates.

| Stage | Input | Processed | Time |
|------|------|--------|------|
| Phase 1 (5 services) | 103,469 | 86,487 passed ToxinPred3 | ~6.75h |
| Phase 2 (GraphCPP) | 4,324 | 4,324 all scored | ~42min |
| **Total** | **103,469** | **→ 4,324 ranked** | **~7.5h** |

## Input sources

| Channel | Round 2 passed | Rate-limit cap | Actually used |
|------|-------------|---------|---------|
| Top (high antioxidant) | 519,524 | 150,000 | 53,469 |
| Bottom (low antioxidant) | 74,476 | 50,000 | 50,000 |
| **Total** | **594,000** | **200,000** | **103,469** |

The Bottom channel actually fell short of 50,000 and had only 50,000.

## ToxinPred3 hard threshold

| Metric | Value |
|------|------|
| Threshold | ≥0.38 eliminated |
| Eliminated | 16,982 (16.4%) |
| Passed | 86,487 (83.6%) |
| ≥0.38* among survivors | 828 (float32 precision residue) |

\* Because of precision issues with the DuckDB FLOAT type, some 0.38 values are stored as 0.37999; the DELETE comparison against 0.38 (float64) passes, but a SELECT read-out shows them slightly below 0.38.

## Score distribution per service (n=86,487)

| Service | Non-null | Min | Mean | Median | Max | Standard deviation |
|------|------|--------|--------|--------|--------|--------|
| BepiPred3 | 86,487 | 0.052 | 0.248 | 0.253 | 0.361 | 0.042 |
| TemStaPro | 86,487 | 0.001 | 0.507 | 0.514 | 0.987 | 0.170 |
| SoDoPE | 86,487 | 0.000 | 0.672 | 0.749 | 1.000 | 0.283 |
| pLM4CPPs | 86,487 | 0.000 | 0.058 | 0.002 | 1.000 | 0.175 |
| ToxinPred3 | 86,487 | 0.000 | 0.219 | 0.210 | 0.380 | 0.081 |
| GraphCPP* | 4,324 | 0.022 | 0.647 | 0.691 | 0.999 | 0.224 |

\* GraphCPP runs only on the top 4,324 Phase 2 candidates.

### Key observations

- **SoDoPE has the largest variance** (SD=0.283) → receives the highest normalized weight
- **BepiPred3 has the smallest variance** (SD=0.042) → low discriminating power, low weight
- **pLM4CPPs is extremely skewed** (median 0.002, mean 0.058) → most peptides are predicted non-penetrating
- **ToxinPred3 is concentrated** (range 0.08-0.38), and the hard threshold effectively eliminates ~16%

## Variance weights (Phase 1: 4 services)

| Service | Normalized weight |
|------|-----------|
| SoDoPE | 0.3175 |
| pLM4CPPs | 0.1965 |
| TemStaPro | 0.1888 |
| BepiPred3 | 0.0467 |

## Variance weights (Phase 2: +GraphCPP, 5 services, top 4,324)

| Service | Normalized weight |
|------|-----------|
| SoDoPE | 0.3175 |
| GraphCPP | 0.2505 |
| pLM4CPPs | 0.1965 |
| TemStaPro | 0.1888 |
| BepiPred3 | 0.0467 |

## Ranking distribution (n=4,324)

| Metric | Value |
|------|------|
| Min | 0.499 |
| Mean | 0.750 |
| Median | 0.758 |
| Max | 0.948 |

## Channel distribution

| Channel | Count | Top composite |
|------|------|--------------|
| Top (high antioxidant) | 116 | 0.870 |
| Bottom (low antioxidant) | 4,208 | 0.948 |

Note: the Top composite of the Bottom channel is higher (0.948 > 0.870),
because ranking is based on multi-service weighting rather than on AnOxPePred alone.

## Peptide length distribution (in the ranking)

| Metric | Value |
|------|------|
| Min | 8 aa |
| Mean | 26.8 aa |
| Median | 27 aa |
| Max | 30 aa |

## Flow

```
round2_passed (594,000)
  ├── rate limiting: Top ≤150K + Bottom ≤50K
  └── input: 103,469
        ├── Phase 1: 5 services scored in parallel
        │     ├── BepiPred3  (GPU, ~7/s, bottleneck)
        │     ├── TemStaPro  (GPU, ~166/s)
        │     ├── SoDoPE     (CPU, ~11K/s)
        │     ├── pLM4CPPs   (GPU, ~633/s)
        │     └── ToxinPred3 (CPU×3, ~33/s)
        ├── ToxinPred3 hard threshold eliminates 16,982
        ├── SD-weighted ranking → 4,324
        └── Phase 2: GraphCPP supplementary scoring (GPU, ~1.7/s)
              └── re-rank including GraphCPP → Round 4
```

## Execution parameters

```bash
# Phase 1
uv run python -m main.stages4.s4_round03_deep_scoring \
    --max-top 150000 --max-bottom 50000 --top-pct 5

# Phase 2
uv run python -m main.stages4.s4_round03_phase2_graphcpp \
    --limit 4324 --top-pct 5
```
