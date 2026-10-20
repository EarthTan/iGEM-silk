> **English** | [中文](cli_usage.zh.md)

# AlgPred2 CLI Detailed Usage

## CLI Parameter Description

```
algpred2 [-h] -i INPUT [-o OUTPUT] [-t THRESHOLD] [-m {1,2}] [-d {1,2}]
```

| Parameter | Long form | Description | Default value |
| --- | --- | --- | --- |
| `-i` | `--input` | Input file (FASTA or text with one sequence per line) | **Required** |
| `-o` | `--output` | Output CSV file | outfile.csv |
| `-t` | `--threshold` | Threshold (0-1) | 0.3 |
| `-m` | `--model` | Model: 1=Allergen, 2=Non-Allergen | 1 |
| `-d` | `--display` | Display: 1=Allergen, 2=all peptides | 1 |

## Invocation Methods

Because of the shebang path issue, the following invocation methods are recommended:

### Method 1: Use uv run (recommended)

```bash
# Text input
uv run algpred2 -i ./input.txt -o ./output.csv -m 1 -d 2

# FASTA input
uv run algpred2 -i ./input.fasta -o ./output.csv -m 1 -d 2
```

### Method 2: Python import (alternative)

```python
from algpred2.python_scripts.algpred2 import main
import sys

# Set the arguments
sys.argv = ['algpred2', '-i', './input.txt', '-o', './output.csv', '-m', '1', '-d', '2']
main()
```

## Input Format

### Text format (one sequence per line)

```
ACDEFGHI
KKLLKLLKL
ACDEFGHIKLMNPQRSTVWY
```

### FASTA format

```
>SEQ_001
ATCGATCGA
>SEQ_002
GCTAGCTAG
```

## Output Format

A CSV file containing the following columns:

| Column name | Description | Example |
| --- | --- | --- |
| ID | Sequence identifier | Seq_1, SEQ_001 |
| Sequence | Peptide sequence | ACDEFGHI |
| ML_Score | Machine learning score (0-1) | 0.264 |
| Prediction | Prediction result | Allergen / Non-Allergen |

## Example Output

```csv
ID,Sequence,ML_Score,Prediction
Seq_1,ACDEFGHI,0.264,Non-Allergen
Seq_2,KKLLKLLKL,0.367,Allergen
```

## Batch Processing

### Processing Multiple Sequences

```bash
# Prepare the input file (one sequence per line)
echo -e "ACDEFGHI\nKKLLKLLKL\nMKWVTFISLLFLFSSAYSR" > sequences.txt

# Run the prediction
uv run algpred2 -i ./sequences.txt -o ./batch_results.csv -m 1 -d 2
```

### Processing a FASTA File

```bash
uv run algpred2 -i ./test_peptides.fasta -o ./fasta_results.csv -m 1 -d 2
```

## Notes

1. **Threshold adjustment**: the default threshold 0.3 is fairly lenient; it can be adjusted to a more conservative 0.5 or higher as needed
2. **Model selection**: `-m 1` predicts allergens, `-m 2` predicts non-allergens
3. **Display mode**: `-d 2` shows results for all peptides, `-d 1` shows only peptides predicted as allergens
