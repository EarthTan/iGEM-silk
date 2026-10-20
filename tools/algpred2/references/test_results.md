> **English** | [中文](test_results.zh.md)

# AlgPred2 Measured Results and Scenario Analysis

## Test Environment

- **Platform**: macOS (Darwin)
- **Python**: 3.11.14
- **uv**: configured
- **Validation date**: 2026-04-24

## Functional Validation Results

### 1. Python Import Test

```bash
uv run python -c "import algpred2; print(dir(algpred2))"
```

**Result**: ✅ Success

**Output**:
```
['__doc__', '__file__', '__loader__', '__name__', '__package__', '__path__', '__spec__']
```

**Conclusion**: the top-level namespace is almost empty, confirming that it is not suitable for direct use as a Python API.

### 2. Submodule Check

```bash
uv run python scripts/inspect_submodules.py
```

**Result**: ✅ Success

**Findings**:
- The `python_scripts` submodule exists
- console script entry point: `algpred2 -> algpred2.python_scripts.algpred2:main`

### 3. Dependency Version Validation

```bash
uv run python -c "import joblib, sklearn, numpy; print(f'joblib: {joblib.__version__}, sklearn: {sklearn.__version__}, numpy: {numpy.__version__}')"
```

**Result**: ✅ Success

**Versions**:
- joblib: 1.5.3
- scikit-learn: 1.2.2
- numpy: 1.26.4

### 4. Text Input Prediction

**Input** (`test_input/test_lines.txt`):
```
ACDEFGHI
KKLLKLLKL
```

**Command**:
```python
from algpred2.python_scripts.algpred2 import main
import sys
sys.argv = ['algpred2', '-i', './test_input/test_lines.txt', '-o', './outputs/test_algpred2.csv', '-m', '1', '-d', '2']
main()
```

**Result**: ✅ Success

**Output CSV**:
```csv
ID,Sequence,ML_Score,Prediction
Seq_1,ACDEFGHI,0.458,Allergen
Seq_2,KKLLKLLKL,0.367,Allergen
```

### 5. FASTA Input Prediction

**Input**: a FASTA file with 100 sequences

**Command**:
```python
from algpred2.python_scripts.algpred2 import main
import sys
sys.argv = ['algpred2', '-i', './test_input/test_peptides.fasta', '-o', './outputs/test_algpred2_fasta.csv', '-m', '1', '-d', '2']
main()
```

**Result**: ✅ Successfully processed 100 sequences

## Batch Capability Assessment

| Scale | Result | Notes |
| --- | --- | --- |
| 2 sequences | ✅ Success | Text input test |
| 100 sequences | ✅ Success | FASTA file test |

**Conclusion**: supports small- to medium-scale batch prediction.

## Known Issues

### Shebang Path Error

Contents of the `.venv/bin/algpred2` file:

```bash
#!/Users/concerto391/Documents/GitHub/iGEM-Tools/from.Lehan/algpred2-risk-prediction/.venv/bin/python
```

**Problem**: the path uses `from.Lehan` (dot) where it should actually be `from-Lehan` (hyphen)

**Impact**: running the `algpred2` command directly reports a "bad interpreter" error

**Workarounds**:
1. Use `uv run algpred2 ...`
2. Call it through Python import

## Scenario Suitability Analysis

### ✅ Suitable Scenarios

1. **Allergenicity risk coarse screening**: preliminary risk assessment of candidate peptide sequences
2. **Penalty term source**: `Prediction = Allergen` or a high `ML_Score` as a fusion engine penalty signal
3. **Batch file processing**: offline analysis that needs to process multiple sequences

### ⚠️ Scenarios to Watch

1. **Short peptides (< 10 aa)**: may not be the optimal choice
2. **Fusion peptides**: recommended to evaluate each component separately
3. **Modified peptides**: not optimized for chemically modified peptides
