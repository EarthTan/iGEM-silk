> English translation of [FEATURE_FUNCTIONS.md](FEATURE_FUNCTIONS.md). The Chinese original is kept unchanged as the source of truth.

# BepiPred-3.0 Feature Extraction Functions

This document provides feature extraction and post-processing functions for BepiPred-3.0 output.

## Feature Extraction Functions

```python
import pandas as pd

def extract_epitope_features(csv_path, threshold=0.1512):
    """Extract features from BepiPred output"""
    df = pd.read_csv(csv_path)

    return {
        'max_epitope_score': df['BepiPred-3.0 score'].max(),
        'mean_epitope_score': df['BepiPred-3.0 score'].mean(),
        'epitope_residue_count': (df['BepiPred-3.0 score'] > threshold).sum(),
        'epitope_ratio': (df['BepiPred-3.0 score'] > threshold).mean(),
        'max_linear_score': df['BepiPred-3.0 linear epitope score'].max(),
    }

def calculate_epitope_penalty(csv_path, threshold=0.1512):
    """Compute the epitope penalty score (for the fusion engine)"""
    df = pd.read_csv(csv_path)

    high_epitope_ratio = (df['BepiPred-3.0 score'] > threshold).mean()
    max_score = df['BepiPred-3.0 score'].max()

    # Penalty score
    penalty = high_epitope_ratio * 0.5 + max_score * 0.5
    return penalty

def epitope_based_filter(csv_path, max_epitope_ratio=0.3, max_score_threshold=0.5):
    """Coarse screening based on epitope prediction"""
    df = pd.read_csv(csv_path)

    epitope_ratio = (df['BepiPred-3.0 score'] > 0.1512).mean()
    max_score = df['BepiPred-3.0 score'].max()

    if epitope_ratio > max_epitope_ratio or max_score > max_score_threshold:
        return False  # does not pass the filter
    return True  # passes the filter
```

## Usage Example

```python
from pathlib import Path
from bp3_feature_functions import extract_epitope_features, calculate_epitope_penalty, epitope_based_filter

csv_path = Path("output/raw_output.csv")

# Extract features
features = extract_epitope_features(csv_path)
print(f"Max epitope score: {features['max_epitope_score']}")
print(f"Epitope ratio: {features['epitope_ratio']}")

# Compute the penalty score
penalty = calculate_epitope_penalty(csv_path)
print(f"Epitope penalty: {penalty}")

# Coarse screening decision
passed = epitope_based_filter(csv_path)
print(f"Filter passed: {passed}")
```

## Function Return Values

### extract_epitope_features return value

| Field | Type | Description |
|------|------|------|
| `max_epitope_score` | float | Maximum epitope score over all residues |
| `mean_epitope_score` | float | Mean epitope score over all residues |
| `epitope_residue_count` | int | Number of epitope residues above the threshold |
| `epitope_ratio` | float | Fraction of epitope residues among all residues |
| `max_linear_score` | float | Maximum linear epitope score |

### calculate_epitope_penalty return value

| Field | Type | Description |
|------|------|------|
| `penalty` | float | Penalty score, range 0-1. Higher means greater immunogenicity risk |

### epitope_based_filter return value

| Field | Type | Description |
|------|------|------|
| `passed` | bool | True = passes the filter, False = rejected |
