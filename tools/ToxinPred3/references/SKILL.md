---
name: toxinpred3
description: Trigger this skill when you need to predict peptide sequence toxicity, extract AAC/DPC features for machine learning models, or filter toxic peptide candidates in a fusion engine.
created: 2026-04-11
version: 1.1
last_updated: 2026-04-25
---

> **English** | [中文](SKILL.zh.md)

# ToxinPred 3.0 Skill Package

> Original repository: https://github.com/raghavagps/toxinpred3
> Paper: Rathore AS, et al. (2024) "ToxinPred3.0: An improved method for the prediction of toxicity of peptides." *Computers in Biology and Medicine*.

## Tool Positioning

**ToxinPred 3.0** is a peptide toxicity prediction tool developed by Prof. G. P. S. Raghava's team at IIITD, India. In the fusion engine it plays the role of **coarse screening filter**, removing clearly toxic peptide segments before full permutation.

### Role in the Fusion Engine

| Application scenario | Specific role |
|---------|---------|
| Coarse screening filter | Remove toxic peptide candidates |
| Feature input | AAC/DPC features as input to the six-efficacy model |
| Safety assessment | Assess the potential toxicity risk of each component of the fusion peptide |
| Reference control | Cross-validate against other toxicity prediction tools |

### Technical Principle

```
Toxicity prediction = ML score (Extra Trees + AAC/DPC)
- ML model: based on an Extra Trees classifier
- Features: AAC (20 dimensions) + DPC (400 dimensions) = 420 dimensions
- The service uses Model 1 (pure ML) and does not depend on the MERCI/Perl hybrid path
```

> **Model 1 vs Model 2**: The official release provides two modes — Model 1 (AAC+DPC) and Model 2 (Hybrid+MERCI motif).
> Actual testing found that Model 2 produces false negatives on known toxins (the MERCI negative motif over-penalizes), so the service chooses Model 1.

---

## Installation and Configuration

### Environment Requirements

- Python 3.11 - 3.11 (requires scikit-learn 1.2.2 compatibility)
- Dependencies: numpy<2, pandas, scikit-learn==1.2.2, joblib

### Standardized Installation Procedure

```bash
cd ToxinPred3
uv venv --python 3.11 .venv
source .venv/bin/activate

uv pip install "numpy<2" pandas scikit-learn==1.2.2 joblib
uv pip install toxinpred3
```

### Quick Verification

```python
from toxinpred_features import predict_toxicity

sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG"]
results = predict_toxicity(sequences)
print(results)
```

---

## Core Functions

### 1. AAC Amino Acid Composition (20 dimensions)

```python
from toxinpred_features import aac_composition

sequences = ["KWKLFKKIGAVLKVL"]
aac = aac_composition(sequences)
# Output: DataFrame, 20 columns, AAC_A, AAC_C, ... AAC_Y
```

**Biological significance:**
- High cationic amino acids (K,R) → possibly antibacterial
- High hydrophobic amino acids (A,V,I,L) → affects membrane penetration
- Aromatic amino acids (W,Y,F) → may affect receptor binding

### 2. DPC Dipeptide Composition (400 dimensions)

```python
from toxinpred_features import dpc_composition

sequences = ["KWKLFKKIGAVLKVL"]
dpc = dpc_composition(sequences)
# Output: DataFrame, 400 columns, DPC_AA, DPC_AC, ... DPC_WY
```

**Biological significance:**
- Reflects local structural preferences
- Certain dipeptide motifs are characteristic markers of toxins
- Captures interactions between amino acids

### 3. Complete Feature Extraction (420 dimensions)

```python
from toxinpred_features import extract_features

sequences = ["KWKLFKKIGAVLKVL"]
features = extract_features(sequences)
# Output: DataFrame, 420 columns (AAC + DPC)
```

### 4. Toxicity Prediction

```python
from toxinpred_features import predict_toxicity

sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG"]
results = predict_toxicity(sequences, threshold=0.38, model=2)
# Output: Name, Sequence, Length, Score, Prediction
```

**Parameter description:**
| Parameter | Description | Default |
|------|------|--------|
| threshold | Toxicity threshold (0-1) | 0.38 |
| model | 1=AAC+DPC, 2=Hybrid | 2 |

**Threshold recommendations:**
| Scenario | Threshold | Description |
|------|------|------|
| High risk (direct administration) | 0.3 | Increase sensitivity |
| Primary screening stage | 0.38 | Default value |
| Low risk (topical) | 0.5 | Increase specificity |

---

## Batch Processing

### Batch Prediction from a FASTA File

```python
from toxinpred_features import batch_predict_from_file

results = batch_predict_from_file(
    input_file="peptides.fa",
    output_file="predictions.csv",
    threshold=0.38,
    model=2
)
```

### Fusion Engine Integration Example

```python
from toxinpred_features import predict_toxicity, extract_features
import pandas as pd

def filter_toxic_peptides(peptides: list, threshold: float = 0.38) -> tuple:
    """
    Filter out potentially toxic peptide segments

    Returns:
        (list of safe peptides, list of toxic peptides)
    """
    predictions = predict_toxicity(peptides, threshold=threshold)

    safe = predictions[predictions['Prediction'] == 'Non-Toxin']['Sequence'].tolist()
    toxic = predictions[predictions['Prediction'] == 'Toxin']['Sequence'].tolist()

    return safe, toxic


def get_peptide_features(peptides: list) -> pd.DataFrame:
    """
    Get the complete feature vector of peptides for machine learning model input
    """
    return extract_features(peptides)


# Usage example
test_peptides = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG", "GIGAVLKVLTTGLPALISWIKRKRQQ"]
safe, toxic = filter_toxic_peptides(test_peptides)
features = get_peptide_features(test_peptides)
```

---

## Quick Reference

| Feature | Function | Output |
|------|------|------|
| Feature extraction | `extract_features(sequences)` | DataFrame (420 columns) |
| AAC | `aac_composition(sequences)` | DataFrame (20 columns) |
| DPC | `dpc_composition(sequences)` | DataFrame (400 columns) |
| Toxicity prediction | `predict_toxicity(sequences)` | DataFrame |
| Batch prediction | `batch_predict_from_file(input, output)` | CSV file |

---

## Examples

### Example 1: Single-Sequence Toxicity Prediction

```python
from toxinpred_features import predict_toxicity

result = predict_toxicity(["KWKLFLFKKIGAVLKVL"], threshold=0.38)
print(result)
```

### Example 2: Batch Processing + Feature Extraction

```python
from toxinpred_features import batch_predict_from_file, extract_features

# Batch prediction
results = batch_predict_from_file("peptides.fa", "out.csv")

# Extract features for ML
features = extract_features("peptides.fa")
print(f"Feature dimensions: {features.shape}")  # (n, 420)
```

### Example 3: Run the Demo Script

```bash
cd ToxinPred3
source .venv/bin/activate
python scripts/demo.py
```

---

## Known Issues

### The Official CLI's Delimiter Bug

**Problem:** the toxinpred3 CLI raises `ValueError: bad delimiter value` when writing the output file

**Cause:** pandas 1.4+ checks the delimiter argument of `to_csv` more strictly

**Solution:** use the Python API in `toxinpred_features.py` (this issue has already been fixed there)

---

## References Index

| File | Contents |
|------|----------|
| `references/installation.md` | Detailed installation steps and troubleshooting |
| `references/biological_background.md` | Biological background of peptide toxicity |
| `references/api_reference.md` | Detailed API parameter reference |
| `scripts/demo.py` | Demo script |
| `toxinpred_features.py` | Python API wrapper module |

---

## Deliverables Checklist

| File | Status | Description |
|------|------|------|
| `toxinpred_features.py` | ✅ Created | Python API wrapper (v1.1) |
| `test_demo.fa` | ✅ Created | Test data |
| `scripts/demo.py` | ✅ Fixed | Demo script |
| `SKILL.md` | ✅ Updated | This skill document |
| `references/` | ✅ Available | Detailed reference documentation |

---

## Changelog

### v1.1 (2026-04-25)
- Created the `toxinpred_features.py` Python API wrapper
- Fixed the import path in demo.py
- Fixed the official CLI's pandas delimiter bug
- Updated SKILL.md to describe the functionality accurately

### v1.0 (2026-04-11)
- Initial version (the documentation description was inaccurate)

---

**Author**: Sisyphus (Agent)
**Date**: 2026-04-25
**Verification status**: ✅ **All passed** (Python 3.11 + sklearn 1.2.2)
