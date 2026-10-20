---
name: BepiPred-3.0
description: Trigger this skill when linear B-cell epitopes of peptide sequences need to be predicted, immunogenicity risk assessed, or used as a penalty term in fusion peptide screening. BepiPred-3.0 is based on the ESM-2 protein language model and can be run locally in batches.
created: 2026-04-17
version: 0.0.12.7
last_updated: 2026-04-25
---

> **English** | [中文](SKILL.zh.md)

# BepiPred-3.0 Linear B-Cell Epitope Prediction Tool

> Original repository: https://github.com/UberClifford/BepiPred-3.0
> PyPI: bp3==0.0.12.7
> Paper: Clifford, J. N., et al. (2022). "BepiPred-3.0: Improved B-cell epitope prediction using protein language models." *Protein Science*, 31(12), e4497.

## What It Is

BepiPred-3.0 is a linear B-cell epitope prediction tool based on the ESM-2 protein language model. It predicts which amino acid residues in a protein/peptide sequence are likely to be recognized by antibodies (i.e., constitute B-cell epitopes).

**Core value**: in the iGEM-silk pipeline it serves as an "exposure proxy metric" — if the functional peptide region is predicted to be a B-cell epitope, that region is exposed on the protein surface after folding (antibody-accessible), so the functional peptide has a higher probability of being effectively exposed.

## When to Use

- **Immunogenicity risk assessment**: evaluate the epitope risk score of candidate peptide sequences
- **Fusion peptide coarse screening**: use as a penalty term to remove highly immunogenic sequences
- **Peptide drug screening**: filter out potentially sensitizing sequences
- **Batch prediction**: process 20/100/1000+ candidate sequences at a time

## Methodology

**Input**: amino acid sequences in FASTA format
**Output**:
- Epitope probability score per residue (0-1)
- Smoothed linear epitope score
- FASTA file with epitope residues marked

**Core workflow**:
1. Use ESM-2 to extract protein language model representations of the sequences
2. Predict epitopes with an ensemble neural network classifier
3. Output per-residue epitope probability and smoothed scores

## Operations

### Installation

```bash
# 1. Download BepiPred-3.0
cd /path/to/BepiPred-3.0
curl -fsSL https://github.com/UberClifford/BepiPred-3.0/archive/refs/heads/main.tar.gz -o repo.tar.gz
tar -xzf repo.tar.gz && mv BepiPred-3.0-main repo

# 2. Create a virtual environment
cd repo
uv venv .venv --python 3.11
source .venv/bin/activate

# 3. Install dependencies (CPU version)
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install fair-esm numpy pandas plotly
```

### Command-Line Usage

```bash
# Activate the environment
source .venv/bin/activate

# Run prediction (variable threshold mode)
python bepipred3_CLI.py -i input.fasta -o output_dir -pred vt_pred

# Run prediction (majority vote mode)
python bepipred3_CLI.py -i input.fasta -o output_dir -pred mjv_pred

# Custom parameters
python bepipred3_CLI.py -i input.fasta -o output_dir -pred vt_pred \
    -t 0.2                    # custom threshold (default 0.1512)
    -rolling_window_size 7     # rolling window size (default 9)
    -top 0.2                   # Top 20% epitopes (default 0.2)
```

### Python API Usage

```python
import sys
from pathlib import Path

# Add the BepiPred-3.0 path
BP3_PATH = "/path/to/BepiPred-3.0/repo"
sys.path.insert(0, BP3_PATH)

from bp3 import bepipred3

# Set paths
fasta_file = Path("input.fasta")
esm_dir = Path("esm_encodings")
out_dir = Path("output")

# Create antigen objects and run prediction
antigens = bepipred3.Antigens(fasta_file, esm_dir, add_seq_len=False)
predictor = bepipred3.BP3EnsemblePredict(antigens, rolling_window_size=7, top_pred_pct=0.2)
predictor.run_bp3_ensemble()

# Write the output
predictor.create_csvfile(out_dir)
predictor.bp3_pred_variable_threshold(out_dir, var_threshold=0.1512)
```

## Input and Output

### Input Format

```fasta
>PEP_001
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG
>PEP_002
GILGFVFTLTVPSERGL
```

### Output Files

| File | Contents |
|------|------|
| `raw_output.csv` | Epitope scores per residue |
| `Bcell_epitope_preds.fasta` | Uppercase = epitope residue, lowercase = non-epitope |
| `Bcell_epitope_top_20pct_preds.fasta` | Top 20% predictions |
| `output_interactive_figures.html` | Interactive visualization |

### raw_output.csv Example

```csv
Accession,Residue,BepiPred-3.0 score,BepiPred-3.0 linear epitope score
PEP_001,M,0.148,0.070
PEP_001,K,0.206,0.078
PEP_001,F,0.086,0.083
```

## Examples

### 1. Basic Prediction Workflow

```bash
# Prepare input
cat > test.fasta << 'EOF'
>PEP_001
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG
>PEP_002
GILGFVFTLTVPSERGL
EOF

# Run prediction
python bepipred3_CLI.py -i test.fasta -o results -pred vt_pred

# Inspect results
cat results/raw_output.csv
cat results/Bcell_epitope_preds.fasta
```

### 2. Batch Screening Script

See `references/FEATURE_FUNCTIONS.md` for details

## Limitations

| Scenario | Limitation |
|------|------|
| **< 5 aa** | Prediction unreliable; ESM-2 encoding needs enough context |
| **5-10 aa** | Lower sensitivity; short peptides usually do not form typical epitopes |
| **Non-standard amino acids** | Characters such as B, Z, X, U, O are accepted but may affect accuracy |
| **Chemical modifications** | Modification information such as phosphorylation and glycosylation is not supported |
| **Compute resources** | The first run requires downloading about 2.5GB of ESM-2 model weights |

### Constraints for Fusion Peptides

- Linker regions (GGGGS, EAAAK) are usually correctly predicted as non-epitope
- Fusion boundaries may generate new epitopes and need special attention
- Predict on the complete fusion peptide rather than predicting each module separately

## References

1. Clifford, J. N., et al. (2022). "BepiPred-3.0: Improved B-cell epitope prediction using protein language models." *Protein Science*, 31(12), e4497.
2. Lin, Z., et al. (2023). "Evolutionary-scale prediction of atomic-level protein structure with a language model." *Science*, 379(6637), 1123-1130.

## References Index

| File | Contents |
|------|----------|
| `references/FEATURE_FUNCTIONS.md` | Feature extraction functions (extract_epitope_features, calculate_epitope_penalty, epitope_based_filter) |
| `references/TEST_RESULTS.md` | Detailed test results and performance data |
| `references/FUSION_PEPTIDE_TESTS.md` | Fusion peptide scenario tests |
