---
name: Weight Iteration and Data-Driven Decisions — Discovering That construct_composite Had Lost Its Discriminative Power v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [weighting, data-driven, eda, composite-score, distribution-analysis, decision-making]
validated: true
---

> English translation of [gep-weight-iteration-data-driven.md](gep-weight-iteration-data-driven.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Weight Iteration and Data-Driven Decisions — Discovering That construct_composite Had Lost Its Discriminative Power

## Experience

**Problem description**: The initial Round 6 scoring formula assigned a 0.50 weight to construct_composite, expecting it to reflect the combined quality of peptide function + SoDoPE + TemStaPro in the final ranking. But among the Top 90 constructs, the construct_composite distribution was highly concentrated — P25=0.5225, P75=0.5336, and the spread of the middle 50% was only **0.011**.

**Symptoms**:
- After weighting, construct_composite almost completely determined the ranking (because SASA/A3D have large spread but low weight)
- The actual discriminative power of SASA and Aggrescan3D was diluted into meaninglessness
- The problem could not be found before running Round 6 — the data distribution characteristics can only be obtained by actually finishing the preceding steps

**Root cause**: After multiple rounds of screening in Rounds 1-5 (1M → 150), the quality of candidate peptides tends toward homogeneity. This is the inevitable outcome of the "screening funnel" — top candidates score high in every dimension in earlier rounds, so by the final round the differences are tiny.

```
The screening process is itself a variance-reduction process:
  1M peptides → large variance in each dimension → multiple rounds of weighted screening → only high-scoring peptides remain
  → high-scoring peptides score high in every dimension → tiny differences in the composite score (σ ≈ 0.011)
  → the composite score loses its discriminative ability
```

### Solution

**Data-driven decision workflow**:

1. **Run the data first, look at the distribution next, decide the weights last**

```python
# Step 1: run one round first (including construct_composite)
constructs = load_constructs()
scores = [c["construct_composite"] for c in constructs]

# Step 2: analyze the distribution
import numpy as np
vals = sorted(scores)
p25, p75 = np.percentile(vals, [25, 75])
spread = p75 - p25
# Top 90: spread = 0.011 → no discriminative power

# Step 3: decide
if spread < 0.05:  # highly concentrated
    W_CONSTRUCT = 0.0   # ignore
    W_SASA = 0.40       # increase the SASA weight
    W_AGG = 0.40        # increase the Aggrescan3D weight
    W_pLDDT = 0.20      # retain structure confidence
else:
    W_CONSTRUCT = 0.50  # keep the original weight
```

2. **Replace assumptions with EDA**

| Assumption | Data validation | Conclusion |
|------|---------|------|
| "construct_composite should be able to separate candidates" | P25-P75 spread=0.011 | ❌ highly concentrated |
| "SASA spread is not large enough" | min=0.501, max=0.831 | ✅ spread=0.33 |
| "Aggrescan3D has discriminative power" | 0.289–0.398 | ✅ spread=0.11 |
| "pLDDT is too poor to be usable" | 0.3666–0.4547 | ⚠️ moderate, usable for quality control |

3. **Final Round 6 formula** (after removing construct_composite):

```
round6 = 0.40 × SASA + 0.40 × (1 - aggrisk) + 0.20 × pLDDT_norm
```

### Key Insight

**Do not preset weights; let the data speak.** This is especially true in the later stages of a multi-round screening pipeline: weights that worked early may fail completely later on. The weights of each round should be re-evaluated based on the actual distribution of that round's input data.

### General Diagnosis Method

| Step | Operation | Criterion |
|------|------|---------|
| 1. Compute P25/P75 | `np.percentile(vals, [25, 75])` | spread < 0.05 → highly concentrated |
| 2. Compute CV | `std/mean` | CV < 0.05 → highly concentrated |
| 3. Visualize | histogram/distplot | single narrow peak → no discriminative power |
| 4. Compare the spread of each dimension | spread ranking of all scoring dimensions | pick the 2-3 dimensions with the largest spread as the main weights |

### Environment Fingerprint

- **Task domain**: Multi-dimensional weighted scoring pipeline
- **Input characteristics**: Candidate sets that have gone through multiple rounds of screening (decreasing variance)
- **Constraints**: The final ranking needs maximum discrimination; the scoring dimensions have different scales
- **Trigger pattern**: Late rounds of a screening pipeline (end of the funnel), where the data is already highly homogeneous
- **Not applicable**: Initial screening rounds (large variance, preset weights are reasonable); single-dimension scoring scenarios; classification (rather than ranking) tasks

### Audit Record

- **Validation method**: Actual computation of the Top 90 construct_composite distribution + comparison of rankings with the weight removed, where SASA/A3D take effect
- **Test cases**:
  1. Original weights (construct=0.50): Top 10 almost identical to the construct_composite ranking → SASA/A3D ineffective
  2. New weights (construct=0.00): Top 10 consistent with the SASA ranking → SASA/A3D genuinely determine the ranking
- **Success rate**: 100% (the data confirmed the decision was correct)
- **Limitations**: If SASA and Aggrescan3D themselves also lack discriminative power (all candidates are similar at the 3D level), new dimensions must be sought back at the peptide sequence level. The current SASA spread of the Top 90, 0.33, is large enough.
