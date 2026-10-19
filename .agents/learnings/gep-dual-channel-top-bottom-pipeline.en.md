---
name: Dual-Channel (Top/Bottom) Selection Design Running Through the Entire Pipeline v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [dual-channel, top-bottom, pipeline-design, negative-control, experimental-design]
validated: true
---

> English translation of [gep-dual-channel-top-bottom-pipeline.md](gep-dual-channel-top-bottom-pipeline.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Dual-Channel (Top/Bottom) Selection Design Running Through the Entire Pipeline

## Experience

**Problem description**: Conventional single-channel screening pipelines only output the "best" candidates, but wet-lab validation needs a negative control to assess the experimental system's discriminating power. If the negative control is simply taken from the bottom of the final ranking, those sequences may be bad in every dimension (toxicity, aggregation, etc.), making it impossible to confirm whether an experiment's failure is due to low antioxidant activity or to a problem in some other dimension.

**Design**: Dual-channel (Top/Bottom) running through the entire pipeline

```
                      ┌─── Top 25K (best antioxidant) ──→ Top 80 peptides ──→ 90 constructs ──→ Top 90 ranking
1M peptides → split ──┤
                      └─── Bottom 25K (worst antioxidant) ──→ Bottom 10 peptides ──→ 60 constructs ──→ Bottom 60 ranking
```

**Core principles**:

1. **Channel split based on a single dimension**: Split using pure AnOxPePred (which directly measures antioxidant activity) without mixing in other weights. This ensures Top/Bottom are genuinely separated along the antioxidant dimension
2. **Same standard for safety dimensions**: The Top and Bottom channels use exactly the same safety filter thresholds (toxicity, allergenicity, hemolysis, etc.), ensuring the Bottom negative controls are equally "clean" on the safety dimensions
3. **Channel labels run through the entire pipeline**: Starting from the Round 2 split, every data row carries a `channel` label (top/bottom); all downstream scoring and ranking are computed separately per channel
4. **Independent rankings**: The final output contains two rankings—Top ranking and Bottom ranking—each sorted by the Round 6 composite score

**Implementation**:

```python
# Round 2: keep the channel label when splitting
for row in all_scored:
    row["channel"] = "top" if row["anoxpepred"] >= threshold else "bottom"

# select independently per channel
top_n = get_top_n(rows, "top", 25000, key="anoxpepred")
bottom_n = get_top_n(rows, "bottom", 25000, key="anoxpepred")  # lowest antioxidant

# Round 7: split the final output by channel
top_rows = [r for r in all_rows if r["channel"] == "top"]
bottom_rows = [r for r in all_rows if r["channel"] == "bottom"]

# sort each independently
top_rows.sort(key=lambda r: r["round6_score"], reverse=True)
bottom_rows.sort(key=lambda r: r["round6_score"], reverse=True)
```

**Bottom-channel specialization**:

| Stage | Top channel | Bottom channel |
|------|---------|------------|
| Round 2 intake | 25,000 | 25,000 |
| Round 3 intake | 80 peptides | 10 peptides |
| Round 4 construct enumeration | 30 peptides × 3 positions × 2 linkers = 90 | 10 peptides × 3 positions × 2 linkers = 60 |
| Round 7 output | 90 constructs | 60 constructs |

### Data Validation

Separation between the Top and Bottom channels on key dimensions (final 150 constructs):

| Dimension | Top mean | Bottom mean | Separation |
|------|---------|------------|--------|
| Round 6 composite score | 0.642 | 0.523 | ✅ significant |
| SASA exposure | 0.702 | 0.501 | ✅ significant |
| OmegaFold pLDDT | 0.4105 | 0.3666 | ✅ small but present |

The data shows that the dual-channel design does maintain separation in the final ranking.

### Environment Fingerprint

- **Task domain**: Biological sequence screening pipeline, wet-lab validation data preparation
- **Input characteristics**: Large-scale candidate sequences (millions), multi-dimensional scoring, requiring experimental validation
- **Constraints**: Experimental validation needs negative controls; the definitions of "best" and "worst" may span multiple dimensions
- **Trigger pattern**: Any screening pipeline with an experimental validation stage
- **Not applicable**: Scenarios that need only Top candidates and have no validation stage; scenarios with a single scoring dimension that need no control

### Best Practices Summary

1. **Keep the split dimension single**: Split using only the core metric (use AnOxPePred for antioxidant) and do not mix weights
2. **Consistent safety filtering**: Top/Bottom pass the same safety gate, ensuring a fair comparison
3. **Labels penetrate the whole pipeline**: The channel label is carried from the split all the way to the final output
4. **Bottom count decreases**: Bottom serves as a control and need not match Top in count; 1/3 to 2/3 of the Top count is recommended
5. **Separate final rankings**: Top and Bottom are each ranked independently without interfering with each other

### Audit Record

- **Validation method**: The full stages2 pipeline completed, outputting independent rankings of 90 Top + 60 Bottom
- **Test cases**:
  1. Round 6 composite score range of the Top channel vs. the Bottom channel → separation confirmed (0.642 vs 0.523)
  2. Whether all Bottom-channel sequences pass the safety screen → confirmed that all pass
  3. Whether Bottom-channel peptides are indeed low in antioxidant activity → confirmed by raw AnOxPePred values
- **Success rate**: 100%
- **Limitations**: 10 peptides → 60 constructs in the Bottom channel gives limited diversity. More negative control peptides would improve experimental reliability but would increase GPU cost.
