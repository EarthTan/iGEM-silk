> English translation of [FUSION_PEPTIDE_TESTS.md](FUSION_PEPTIDE_TESTS.md). The Chinese original is kept unchanged as the source of truth.

# BepiPred-3.0 Fusion Peptide Scenario Tests

## Test Background

A fusion peptide is usually assembled from several functional modules connected by linkers (such as GGGGS, EAAAK). Testing how BepiPred-3.0 performs in this scenario is crucial for evaluating its use in the fusion engine.

## Test Cases

### Test 1: Fusion of Two Functional Modules

**Sequence**:
```
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG + GGGSEAAAK + GILGFVFTLTVPSERGL
```

**Functional modules**:
- Module 1: MKPTHPNPRG (unknown functional peptide)
- Linker: GGGGSEAAAK
- Module 2: GILGFVFTLTVPSERGL (from an influenza virus peptide)

**Prediction result**:
```
MKflillfnilclfpvlaADNHGNPKTHPNPRGGGGSEAAAKGILGFvFTltVPSERGl
```

**Analysis**:
- Most of the linker region (GGGGSEAAAK) is lowercase, indicating non-epitope ✅
- The D, N, H, G, N at the end of module 1 are predicted as epitopes
- The E, R, G, L at the end of module 2 are predicted as epitopes

### Test 2: Fusion with a Short Linker

**Sequence**:
```
SIINFEKLTEWTSV + GGGGM + MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG
```

**Result**:
```
sIINFEKLTEWTSVGGGGMmKflillfnilclfpvlaADNHGNPKTHPNPRG
```

**Observations**:
- When a short linker (GGGGM) is immediately followed by a functional module, the epitope prediction carries over
- This shows that epitope prediction is sequence-continuous, not a modular judgment

### Test 3: Single Functional Module + Long Linker

**Sequence**:
```
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG + GGGGSGGGGSGGGGS + SIINFEKLTEWTSV
```

**Result analysis**:
- Long repetitive linkers are usually predicted as non-epitope
- Functional module boundaries are hotspot regions for epitope prediction

## Effect of Linkers on Epitope Prediction

| Linker type | Length | Epitope prediction | Notes |
|-------------|------|----------|------|
| GGGGS | 5 | Non-epitope | Flexible linker, commonly used in fusion peptides |
| EAAAK | 5 | Non-epitope | Rigid linker |
| (GGGS)n | Variable | Non-epitope | Repeat structure |
| AP | 2 | Varies | Short linker, may affect the boundary |
| No linker | 0 | N/A | Direct fusion may generate new epitopes |

## Recommendations for Fusion Peptide Prediction

### 1. Prefer Full-Length Prediction

**Recommendation**: predict on the complete fusion peptide rather than predicting each functional module separately.

**Reasons**:
- The ESM-2 model needs sufficient sequence context
- Module boundaries may generate new epitopes
- The presence of a linker may affect the overall epitope distribution

### 2. Epitope Density Analysis

```python
def epitope_density_analysis(csv_path, window_size=7):
    """Analyze the epitope density distribution"""
    df = pd.read_csv(csv_path)

    # Compute sliding-window epitope density
    scores = df['BepiPred-3.0 score'].values
    densities = []

    for i in range(len(scores) - window_size + 1):
        window = scores[i:i+window_size]
        density = (window > 0.1512).mean()
        densities.append(density)

    return densities
```

### 3. Special Handling for Linker Regions

If a linker region is predicted to carry high epitope risk:
- Check whether functional module boundaries have exposed new epitopes
- Consider adjusting the linker length or sequence
- Using a longer linker may reduce boundary effects

## Integration into the Fusion Engine

### Flowchart

```
candidate fusion peptide → BepiPred-3.0 prediction → extract epitope features
                                         ↓
                    ┌─────────────────────┴─────────────────────┐
                    ↓                                           ↓
            epitope score extraction                     penalty term computation
            - max_score                                  - epitope_penalty
            - mean_score                                 - high_ratio_penalty
            - epitope_ratio                              - combined_penalty
                    ↓                                           ↓
                    └─────────────────────┬─────────────────────┘
                                            ↓
                                    fusion engine scoring
```

### Integration Example

```python
class EpitopeScorer:
    """Epitope risk scorer"""

    def __init__(self, threshold=0.1512, penalty_weight=0.3):
        self.threshold = threshold
        self.penalty_weight = penalty_weight

    def score(self, csv_path):
        """Return the epitope risk score (higher = greater risk)"""
        df = pd.read_csv(csv_path)

        max_score = df['BepiPred-3.0 score'].max()
        epitope_ratio = (df['BepiPred-3.0 score'] > self.threshold).mean()

        # Composite risk score
        risk_score = max_score * 0.6 + epitope_ratio * 0.4

        return risk_score

    def should_penalize(self, csv_path, max_risk=0.5):
        """Decide whether a penalty is needed"""
        risk = self.score(csv_path)
        return risk > max_risk
```

## Known Limitations

1. **Short peptide scenarios**: predictions are unreliable for fusion peptide modules <10 aa
2. **Boundary effects**: false positives may occur at the junction between a functional module and a linker
3. **Non-standard amino acids**: D-amino acids, β-amino acids, etc. are not supported
4. **Modified peptides**: post-translational modifications such as phosphorylation and glycosylation cannot be taken into account

## Conclusion

BepiPred-3.0 can effectively assess the epitope risk of fusion peptides, but note the following:
- Predict on the complete fusion peptide
- Linker regions are usually safe, but the boundaries need attention
- Epitope scores can serve as a penalty term to effectively reduce high-risk candidates
