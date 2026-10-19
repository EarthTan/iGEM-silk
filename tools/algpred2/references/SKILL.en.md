---
name: algpred2-risk-prediction
description: Trigger this skill when the user needs to predict the allergenicity risk of peptide/protein sequences locally and use the result as a screening penalty term or conservative filter layer in a fusion engine. Also use when allergenicity risk screening is needed for candidate peptides and the result will serve as a penalty signal in a fusion engine.
created: 2026-04-16
version: 1.4
last_updated: 2026-04-24
---

> English translation of [SKILL.md](SKILL.md). The Chinese original is kept unchanged as the source of truth.

# AlgPred2 Allergenicity Risk Prediction

## What It Is

**AlgPred2** is a CLI-first allergenicity risk prediction tool that evaluates the allergenicity probability of peptide/protein sequences through machine learning models.

In the fusion engine it plays the role of a **risk screening layer**:
- Outputs `ML_Score` (0-1) and `Prediction` (Allergen/Non-Allergen)
- High-risk sequences can serve as a penalty term or filtering signal

## When to Use

- When you need coarse allergenicity risk screening of candidate peptides
- When you want "possibly an allergen" to serve as a penalty term in the fusion engine
- When you need a prediction tool that runs locally and processes files in batch

**Not suitable for**: out-of-the-box use, zero-parameter-tuning, or direct Python API call scenarios

## Methodology

1. **Treat as CLI-first**: do not assume a Python API exists; use the command line directly
2. **Fix dependencies first**: after installation you must manually install `joblib` and pin the scikit-learn/numpy versions
3. **Validate output format**: confirm the CSV column names and the meaning of the results before connecting to downstream processes

## Operations

### Quick Start

```bash
# 1. Install dependencies
uv add algpred2
uv add joblib
uv add "scikit-learn==1.2.2" "numpy==1.26.4"

# 2. Text input prediction
uv run algpred2 -i ./input.txt -o ./output.csv -m 1 -d 2

# 3. FASTA input prediction
uv run algpred2 -i ./input.fasta -o ./output.csv -m 1 -d 2
```

### CLI Parameters

| Parameter | Description | Default |
| --- | --- | --- |
| `-i INPUT` | Input file (FASTA or plain sequence text) | **Required** |
| `-o OUTPUT` | Output CSV | outfile.csv |
| `-t THRESHOLD` | Threshold (0-1) | 0.3 |
| `-m {1,2}` | 1=Allergen, 2=Non-Allergen | 1 |
| `-d {1,2}` | 1=only allergens, 2=all peptides | 1 |

## Inputs and Outputs

- **Input**: a FASTA file or a text file with one sequence per line
- **Output**: a CSV file

| Column name | Description |
| --- | --- |
| ID | Sequence identifier |
| Sequence | Peptide sequence |
| ML_Score | Machine learning score (0-1) |
| Prediction | Allergen / Non-Allergen |

## Examples

### Example 1: Batch prediction and filtering of high-risk sequences

```bash
# Predict
uv run algpred2 -i ./candidates.fasta -o ./risk_results.csv -m 1 -d 2

# Extract high-risk sequences (ML_Score > 0.5)
# Filter with other tools or review manually
```

### Example 2: Integration into a fusion engine as a penalty term

```python
# Pseudocode - penalty logic in the fusion engine
if prediction == "Allergen":
    apply_penalty(1.0)  # Exclude entirely
elif ml_score > 0.5:
    apply_penalty(0.5)  # Down-weight high risk
```

## Known Issue

The shebang path of `.venv/bin/algpred2` may be wrong. If running it directly fails, use the Python import approach:

```python
from algpred2.python_scripts.algpred2 import main
import sys
sys.argv = ['algpred2', '-i', './input.txt', '-o', './output.csv', '-m', '1', '-d', '2']
main()
```

## Limitations

- Not out of the box; dependencies must be fixed manually
- The top-level Python API is unavailable
- Mainly designed for proteins; effectiveness on short peptides may be limited
- Large-scale stress testing (1000+ sequences) has not been completed

## References Index

| File | Contents |
| --- | --- |
| `references/installation.md` | Detailed installation guide and dependency versions |
| `references/cli_usage.md` | Detailed CLI parameters and invocation methods |
| `references/methodology.md` | Algorithm principles and fusion engine integration recommendations |
| `references/test_results.md` | Measured results and scenario analysis |
