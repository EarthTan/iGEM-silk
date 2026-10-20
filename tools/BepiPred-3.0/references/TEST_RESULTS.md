> **English** | [中文](TEST_RESULTS.zh.md)

# BepiPred-3.0 Detailed Test Results

## Test Environment

- **Platform**: macOS (Darwin)
- **Python**: 3.11
- **PyTorch**: 2.11.0 (CPU)
- **fair-esm**: 2.0.0
- **Device**: Apple M1, CPU mode

## Installation Verification

### Dependency Installation Commands

```bash
uv venv .venv --python 3.11
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
uv pip install fair-esm numpy pandas plotly
```

### First Run

On the first run, the ESM-2 model weights (about 2.5GB) are downloaded automatically:

```
Downloading: "https://dl.fbaipublicfiles.com/fair-esm/models/esm2_t33_650M_UR50D.pt"
Downloading: "https://dl.fbaipublicfiles.com/fair-esm/models/esm2_t33_650M_UR50D-contact-regression.pt"
```

## Functional Tests

### Test 1: Basic Prediction (3 Sequences)

**Input**:
```fasta
>TEST_PEP1
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG
>TEST_PEP2
GILGFVFTLTVPSERGL
>TEST_PEP3
SIINFEKLTEWTSV
```

**Output**:
- ✅ `raw_output.csv` - contains per-residue scores
- ✅ `Bcell_epitope_preds.fasta` - epitope flags
- ✅ completed in about 5 seconds

**Key findings**:
- Uppercase letters indicate residues predicted as epitopes
- Residues such as D, N, H, G, N, P, K in TEST_PEP1 were flagged as epitopes

### Test 2: Fusion Peptide Scenario

**Input**:
```fasta
>FUSION_1
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRGGGGSEAAAKGILGFVFTLTVPSERGL
```

**Results**:
- Part of the linker region (GGGGSEAAAK) is predicted as non-epitope (lowercase)
- Part of the fusion region boundary is predicted as epitope

**Observations**:
- Linkers (GGGGS, EAAAK) are usually correctly predicted as non-epitope
- Functional module boundary regions may generate new epitope signals

### Test 3: Short Peptide Limitations

| Sequence | Length | Max score | Threshold | Predicted as epitope |
|------|------|----------|------|------------|
| GGGGS | 5 aa | 0.24 | 0.1512 | No |
| DYKDDDDK | 8 aa | ~0.15 | 0.1512 | Suspect |
| X | 1 aa | 0.15 | 0.1512 | No |

**Conclusion**: predictions for short peptides (<10 aa) should be interpreted with caution.

## Batch Processing Performance

### 20-Sequence Test

```
Number of sequences: 20
Average length: 25-45 aa
Processing time: ~7 seconds (ESM encoding already cached)
```

### 100-Sequence Test

```
Number of sequences: 100
Average length: 15-55 aa
Processing time: ~14 seconds (cold start, including ESM encoding)
```

**Performance conclusions**:
- Batch processing of 100 sequences completes within 15 seconds
- ESM encoding can be cached, making subsequent runs faster
- Memory usage: about 2-3GB when processing 100 sequences

## Python API Test

```python
from bp3 import bepipred3
from pathlib import Path

antigens = bepipred3.Antigens(fasta_file, esm_dir, add_seq_len=False)
predictor = bepipred3.BP3EnsemblePredict(antigens, rolling_window_size=7, top_pred_pct=0.2)
predictor.run_bp3_ensemble()
predictor.create_csvfile(out_dir)
```

✅ API call succeeded

## Output Format Details

### raw_output.csv Fields

| Field | Description |
|------|------|
| Accession | Sequence identifier |
| Residue | Amino acid residue (one letter) |
| BepiPred-3.0 score | Raw epitope prediction score (0-1) |
| BepiPred-3.0 linear epitope score | Smoothed linear epitope score |

### Threshold Notes

- **Default threshold**: 0.1512 (recommended in the paper)
- **Score > threshold**: predicted as an epitope residue
- **Score < threshold**: predicted as a non-epitope residue

## Comparison with BepiPred-2.0

| Feature | BepiPred-2.0 | BepiPred-3.0 |
|------|--------------|--------------|
| Underlying model | Empirical model | ESM-2 language model |
| Installation | Requires downloading the IEDB tool | Just clone from GitHub |
| Dependencies | Linux 64-bit | Python environment |
| Batch processing | Must go through the web | CLI/Python API |
| Deployment difficulty | Higher | Lower |

**Recommendation**: use BepiPred-3.0; local integration is more convenient.
