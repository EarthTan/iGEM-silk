---
name: tipred
description: Trigger this skill when you need to predict tyrosinase inhibitory peptide (TIP) activity, screen anti-melanogenic peptides, or score TIP activity in a fusion engine.
created: 2026-04-18
version: 2.0.0
last_updated: 2026-04-21
---

> English translation of [SKILL.md](SKILL.md). The Chinese original is kept unchanged as the source of truth.

# TIPred - Tyrosinase Inhibitory Peptide Prediction

## What It Is

A computational tool for predicting the activity of **tyrosinase inhibitory peptides (TIPs)**, accelerating the screening of whitening/anti-melanogenic peptides.

### Fusion Engine Role

| Layer | Role |
|------|------|
| Feature layer | Provides a 547-dimensional multi-view feature representation |
| Prediction layer | TIP activity probability score (0-1) |
| Coarse screening layer | Removes combinations without TIP activity before full enumeration |

## When to Use

- Screening candidate anti-melanogenic peptide sequences
- Scoring the TIP activity of fusion peptides
- Serving as one of the feature inputs for the six-efficacy model
- Prediction and ranking of whitening-efficacy peptides

## Methodology

```
Peptide sequence → 7 feature encodings → 547-dimensional feature vector → Stacked Ensemble → TIP probability (0-1)
```

### Feature Encoders (7 kinds, 547 dimensions)

| Encoder | Full name | Dimensions |
|--------|------|------|
| AAC | Amino Acid Composition | 20 |
| DPC | Dipeptide Composition | 400 |
| APAAC | Amphiphilic Pseudo AAC | 40 |
| PAAC | Parallel Pseudo AAC | 40 |
| CTDC | Composition | 13 |
| CTDT | Transition | 13 |
| CTDD | Distribution | 21 |

### Stacked Ensemble

- **Base Models (Level 0)**: KNN, RF, SVM (RBF), GB
- **Meta Model (Level 1)**: Logistic Regression
- **Training strategy**: 5-fold cross-validation to generate base predictions, avoiding data leakage

## Operations

### Environment

```bash
cd Tipred/
uv init --no-readme
uv add scikit-learn pandas numpy
```

### Python API

```python
from scripts.tipredictor_full import TIPredictorMVFF

predictor = TIPredictorMVFF(model_type='stacked')
results = predictor.train(sequences, labels)  # sequences: list, labels: list (1=TIP, 0=non-TIP)
probs = predictor.predict(['YGGFL', 'GHK'])
# → [0.905, 0.060]
```

### Command Line

```bash
# Training
python scripts/tipredictor_full.py --train --input sequences.fasta --labels labels.csv --save-model mvff_model.pkl --type stacked

# Prediction
python scripts/tipredictor_full.py --model mvff_model.pkl --input queries.fasta --output results.csv
```

## Inputs and Outputs

- **Input**: FASTA / CSV (with a sequence column) / Python List
- **Output**: TIP probability (0-1), predicted class (TIP/non-TIP, threshold 0.5)

```csv
ID,Sequence,TIP_Probability,Prediction
0,YGGFL,0.905,TIP
1,GHK,0.060,non-TIP
```

## Examples

### Quick Training and Prediction

```python
from scripts.tipredictor_full import TIPredictorMVFF

sequences = ['YGGFL', 'GHK'] * 50 + ['RRRRR', 'DDDDD'] * 50
labels = [1, 1] * 50 + [0, 0] * 50

predictor = TIPredictorMVFF(model_type='stacked')
predictor.train(sequences, labels)
probs = predictor.predict(['YGGFL', 'RRRRR'])
print(f'YGGFL: {probs[0]:.3f}, RRRRR: {probs[1]:.3f}')
```

### Batch Screening

```python
import pandas as pd
from scripts.tipredictor_full import TIPredictorMVFF

predictor = TIPredictorMVFF.load('mvff_model.pkl')
df = pd.read_csv('candidates.csv')
df['TIP_Prob'] = predictor.predict(df['Sequence'].tolist())
tip_candidates = df[df['TIP_Prob'] >= 0.5]
print(f'Screened {len(tip_candidates)} TIP candidates out of {len(df)} sequences')
```

## References Index

| File | Contents |
|------|----------|
| `references/TIP-redesign.md` | Detailed feature encoding description, model comparison, limitations |
| `references/tipredictor.py` | Older simple implementation (10-dimensional features) |
| `references/test_peptides.csv` | Test data |
| `references/test_peptides.fasta` | Test data (FASTA format) |
| `scripts/train_example.py` | Example training script |
