> English translation of [anoxpepred_guide.md](anoxpepred_guide.md). The Chinese original is kept unchanged as the source of truth.

# AnOxPePred Technical Reference

> Model source: [TobiasHeOl/AnOxPePred](https://github.com/TobiasHeOl/AnOxPePred)

## Overview

AnOxPePred (Antioxidant Peptide Predictor) is an antioxidant peptide prediction tool based on CNN deep learning. It uses a pretrained convolutional neural network to assess the antioxidant potential of peptide sequences and supports two mechanisms:

- **FRS (Free Radical Scavenging)**: free radical scavenging capacity
- **Chel (Metal Chelation)**: metal ion chelation capacity

## Model Architecture

### CNN Network Structure

```
Input: 30×20 one-hot encoding matrix (centered padding with 'X')
  ↓
Conv1D(filters=128, kernel_size=3, strides=1, activation=elu, padding='same')
  ↓
AveragePooling1D(pool_size=3, strides=3)  → Dropout(0.1)
  ↓
Flatten() → (1280,)
  ↓
Dense(256, activation=elu) → Dropout(0.15)
  ↓
Dense(2, activation=sigmoid) → [FRS_score, Chel_score]
```

### Model Parameters

| Layer | Parameter shape | Parameter count |
|----|---------|---------|
| Conv1D kernel | [3, 20, 128] | 7,680 |
| Conv1D bias | [128] | 128 |
| Dense1 kernel | [1280, 256] | 327,680 |
| Dense1 bias | [256] | 256 |
| Dense2 kernel | [256, 2] | 512 |
| Dense2 bias | [2] | 2 |

- **Loss function**: Focal Loss (γ=3, α=0.25), to handle positive/negative sample imbalance
- **Optimizer**: Adam (learning_rate=0.00003)
- **Total parameter count**: ~336K

## Data Preprocessing

### Sequence Encoding
1. Convert to uppercase
2. Truncate if the sequence is longer than 30 amino acids
3. **Centered padding**: symmetrically pad with 'X' to 30 amino acids
4. Represent each amino acid with a 20-dimensional one-hot encoding matrix

### Encoding Matrix
`anoxpepred_data/One-hot_encoding.txt` — a standard 21-row × 21-column one-hot matrix containing the 20 standard amino acids plus 'X' (an all-zero vector).

## Prediction Mechanism

### Dual Output
The model predicts two activity scores simultaneously:
- **FRS (free radical scavenging)**: the 1st neuron of the output layer
- **Chel (metal chelation)**: the 2nd neuron of the output layer

### Composite Score
```
overall_score = FRS × 0.6 + Chel × 0.4
```

### Classification Threshold
Default 0.5. The original paper uses an MCC-based optimal threshold search (`find_opt_thres`).

## Dual-Mode Operation

### CNN Mode
- Requirements: TensorFlow ≥ 2.15, model weight files
- Accuracy: ~87% (as reported in the paper)
- Characteristics: uses the pretrained Conv1D network for prediction

### Rule-Based Prediction Mode (Fallback)
- Requirements: numpy/pandas only
- Accuracy: ~72%
- Characteristics: heuristic scoring based on per-amino-acid antioxidant activity weights
- Trigger condition: TensorFlow not installed, or weight files missing/corrupted

### Amino Acid Weights for Rule-Based Prediction

| Amino acid | Weight | Main mechanism |
|--------|------|----------|
| C (cysteine) | 2.5 | FRS + Chel |
| H (histidine) | 1.8 | Chel |
| W (tryptophan) | 1.5 | FRS |
| Y (tyrosine) | 1.2 | FRS |
| M (methionine) | 1.0 | FRS |
| F (phenylalanine) | 0.8 | FRS |
| R (arginine) | 0.6 | — |
| K (lysine) | 0.5 | — |

## API Endpoints

Provided after starting the service with `python service.py`:

| Method | Path | Description |
|------|------|------|
| GET | `/` | Service information |
| GET | `/health` | Health check (returns model_mode: cnn/rule) |
| GET | `/info` | Tool metadata |
| POST | `/predict` | Single-sequence prediction |
| POST | `/predict/batch` | Batch prediction |

## Project Structure

```
AnOxPePred/
├── service.py                    # FastAPI microservice entry point
├── tools/
│   ├── anoxpepred_integration.py # Core integration module (model loading/prediction)
│   ├── AnOxPePred_funcs.py      # Original paper code (reference implementation)
│   └── __init__.py
├── anoxpepred_data/
│   ├── AnOxPePred_v1.index       # TF checkpoint index
│   ├── AnOxPePred_v1.data-00000-of-00001  # Model weights
│   └── One-hot_encoding.txt     # Amino acid encoding matrix
├── references/
│   ├── SKILL.md                  # Claude Code skill definition
│   └── anoxpepred_guide.md      # This document
└── pyproject.toml
```

## References

1. **AnOxPePred: a tool for the prediction of antioxidant peptides** (2021)
   - Authors: Tobias H. Olsen et al.
   - Repository: https://github.com/TobiasHeOl/AnOxPePred
   - Journal: Bioinformatics
