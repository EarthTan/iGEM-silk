> English translation of [methodology.md](methodology.md). The Chinese original is kept unchanged as the source of truth.

# AlgPred2 Methodology and Technical Background

## Algorithm Positioning

**AlgPred2** is an allergenicity prediction tool developed by Prof. G. P. S. Raghava's team. Its core positioning is:

> Converting the allergenicity risk of peptide/protein sequences into a quantifiable machine learning score, used for conservative risk assessment in the preliminary screening stage.

## Role in the Fusion Engine

According to the definition in TASK.md, AlgPred2 plays the following roles in the fusion engine:

| Role | Description |
| --- | --- |
| **Risk screening layer** | Acts as a conservative penalty term, filtering sequences with high allergenicity risk |
| **Feature signal source** | Provides ML_Score as one of the input signals for subsequent scoring |

## Methodology

### Core Idea

1. **Sequence encoding**: convert amino acid sequences into numerical features
2. **Machine learning model**: predict allergenicity probability based on a trained model
3. **Threshold decision**: decide whether the sequence is an allergen based on the threshold

### Technical Implementation

- **Underlying framework**: scikit-learn
- **Model format**: pickle binary model
- **Dependency**: numpy 1.26.4 (matrix operations)

### Input Limitations

| Dimension | Limitation |
| --- | --- |
| Sequence length | No explicit upper limit; long sequences are processable in practice |
| Amino acid types | The 20 standard amino acids |
| Input format | FASTA or plain sequence text |

## Fusion Engine Integration Recommendations

### As a Penalty Term

```python
# Pseudocode example
def calculate_penalty(score):
    if score.prediction == "Allergen":
        return 1.0  # Exclude entirely
    elif score.ml_score > 0.5:
        return 0.5  # Down-weight high risk
    else:
        return 0.0  # Low risk, pass
```

### Threshold Selection Recommendations

| Application scenario | Recommended threshold |
| --- | --- |
| Conservative screening (safety first) | 0.3 (default) |
| Balanced mode | 0.5 |
| Lenient screening (activity first) | 0.7 |

## Limitations

### Confirmed Limitations

1. **Not out of the box**: additional dependencies must be installed manually
2. **Incomplete top-level API**: cannot be called directly as a Python function
3. **File-input oriented**: not suitable for embedding as a purely functional API
4. **Not optimized for short peptides**: mainly designed for proteins; effectiveness on short peptides may be limited

### Caveats for Fusion Peptide Scenarios

For fusion peptide scenarios, the recommended use of AlgPred2 is:

1. **Evaluate each component separately**: assess each functional module of the fusion peptide individually
2. **Linker region risk**: linker sequences may introduce new allergenicity risk
3. **Combination effects**: the allergenicity after fusion may not equal the sum of the components
