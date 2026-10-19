---
name: anoxpepred
description: Trigger this skill when the user needs to predict the antioxidant activity of peptide sequences. It predicts the antioxidant potential of peptides with a machine learning model and supports multiple antioxidant mechanisms and batch processing.
created: 2026-04-18
version: 1.1.0
last_updated: 2026-04-25
---

> English translation of [SKILL.md](SKILL.md). The Chinese original is kept unchanged as the source of truth.

# AnOxPePred

## What It Is
AnOxPePred (Antioxidant Peptide Predictor) is a deep-learning-based antioxidant peptide prediction tool. It uses a pretrained convolutional neural network model to assess the antioxidant potential of peptide sequences, supporting several antioxidant mechanisms, including:
- **FRS (Free Radical Scavenging)**: free radical scavenging capacity
- **Chel (Metal Chelation)**: metal ion chelation capacity

Model source: [TobiasHeOl/AnOxPePred](https://github.com/TobiasHeOl/AnOxPePred)

## When to Use
- **Antioxidant peptide screening**: identify potential antioxidant candidates from peptide libraries
- **Functional food development**: evaluate the antioxidant activity of food-derived peptides
- **Drug discovery**: find antioxidant peptides with therapeutic potential
- **Peptide engineering**: design peptide variants with enhanced antioxidant activity
- **Bioinformatics analysis**: batch-analyze the antioxidant potential of protein hydrolysates

## Methodology
AnOxPePred uses a deep convolutional neural network for prediction:
1. **Sequence encoding**: represent the peptide sequence with a 30x20 one-hot encoding matrix
2. **Convolutional layer**: 128 filters, kernel size 3, elu activation
3. **Pooling layer**: average pooling, pool size 3
4. **Fully connected layer**: 256 neurons, elu activation, dropout 0.15
5. **Output layer**: 2 neurons (corresponding to FRS and Chel), sigmoid activation
6. **Loss function**: Focal Loss (to handle class imbalance)

## Operations

### Installation

**Option 1: use uv (recommended)**
```bash
# Create a virtual environment
cd /path/to/AnOxPePred
uv sync

# Optional: install full functionality (deep learning model)
uv sync --extra ml

# Optional: install visualization dependencies
uv sync --extra viz
```

**Option 2: use pip (not recommended)**
```bash
pip install pandas numpy
pip install tensorflow biopython matplotlib seaborn  # full functionality
```

### Model Files

The deep learning model requires the following files (already included in the `anoxpepred_data/` directory):
- `AnOxPePred_v1.data-00000-of-00001`: model weight file
- `AnOxPePred_v1.index`: model index file
- `One-hot_encoding.txt`: amino acid encoding matrix

If the model files are missing, the tool automatically falls back to a rule-based prediction mode based on amino acid composition.

### Quick Start

```python
import sys
sys.path.insert(0, '/path/to/AnOxPePred')  # add the project path

from tools.anoxpepred_integration import AnOxPePredIntegration

# Initialize the predictor
predictor = AnOxPePredIntegration()

# Predict the antioxidant activity of a single peptide
peptide = "YVPLPNVPQG"
result = predictor.predict_single(peptide, peptide_id="test_peptide")

print(f"Antioxidant probability: {result.overall_score:.3f}")
print(f"Predicted class: {result.overall_class}")
print(f"Free radical scavenging score (FRS): {result.frs_score:.3f}")
print(f"Metal chelation score (Chel): {result.chel_score:.3f}")
print(f"Confidence: {result.confidence}")
```

### Batch Prediction

```python
# Batch-predict multiple peptides
peptides = {
    "pep1": "YVPLPNVPQG",
    "pep2": "FFVAPFPEVFGK",
    "pep3": "KVEPLRAD"
}

batch_results = predictor.predict_batch(peptides)

# Print the results
for peptide_id, result in batch_results.items():
    print(f"{peptide_id}: {result.sequence} -> {result.overall_class} (score: {result.overall_score:.4f})")

# Export the results
predictor.export_results(batch_results, "anoxpepred_results.csv", format="csv")
```

### Predicting from Files

```python
# Predict from a FASTA file
results = predictor.predict_from_fasta("peptides.fasta", threshold=0.5)

# Predict from a CSV file
results = predictor.predict_from_csv("peptides.csv", seq_col="sequence", id_col="id")
```

## Inputs and Outputs
- **Input**:
  - Peptide sequence (as a string, usually 2-50 amino acids)
  - Peptide ID (optional)
  - File path (FASTA or CSV format)
- **Output**:
  - `overall_score`: composite antioxidant score (0-1)
  - `overall_class`: predicted class (Antioxidant / Non-antioxidant)
  - `frs_score`: free radical scavenging score (0-1)
  - `chel_score`: metal chelation score (0-1)
  - `confidence`: confidence level (high / medium / low / very_low)
  - `mechanism_scores`: dictionary of scores per mechanism

## Examples

1. **Single peptide evaluation**:
```python
result = predictor.predict_single("CCHHPLLLLLLA", peptide_id="cysteine_rich")
print(f"Antioxidant: {result.is_antioxidant}, score: {result.overall_score:.3f}")
```

2. **High-throughput screening**:
```python
# Read the test data
import pandas as pd
df = pd.read_csv("peptides.csv")
sequences = {str(i): seq for i, seq in enumerate(df['sequence'])}

# Batch prediction
results = predictor.predict_batch(sequences)

# Filter for highly active peptides
antioxidant_peptides = {
    pid: r for pid, r in results.items() if r.is_antioxidant
}
print(f"Found {len(antioxidant_peptides)} antioxidant peptides")
```

3. **Mechanism analysis**:
```python
result = predictor.predict_single("YVPLPNVPQG")
print(f"Free radical scavenging: {result.mechanism_scores['radical']:.3f}")
print(f"Metal chelation: {result.mechanism_scores['metal']:.3f}")
```

## References Index
| File | Contents |
|------|----------|
| `references/anoxpepred_guide.md` | Detailed technical documentation, algorithm description and feature engineering |
| `scripts/antioxidant_screening.py` | Antioxidant peptide screening pipeline script |
| `tools/anoxpepred_integration.py` | Core integration module |
| `anoxpepred_data/` | Model weights and encoding matrix |

## Limitations

1. **Sequence length**: the model is designed for peptides of 2-50 amino acids; overly long sequences may be inaccurate
2. **Non-standard amino acids**: sequences containing non-standard amino acids (B, J, Z, U, O, X) may not be encoded correctly
3. **Model availability**: the deep learning model requires TensorFlow; if it is not installed, the tool automatically falls back to rule-based prediction
4. **Prediction modes**:
   - Deep learning mode: uses the pretrained model, higher accuracy
   - Rule-based prediction mode: based on amino acid composition, lower accuracy but no extra dependencies
