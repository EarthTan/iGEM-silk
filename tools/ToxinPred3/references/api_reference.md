> **English** | [中文](api_reference.zh.md)

# ToxinPred 3.0 API Reference

## Main Functions

### extract_features(sequences)

Extract the complete AAC + DPC feature set.

**Parameters:**
- `sequences`: `List[str]` or `str`
  - A list of peptide sequences, or a FASTA file path

**Returns:**
- `pd.DataFrame`: a 420-column feature matrix

**Example:**
```python
from toxinpred_features import extract_features

# From a sequence list
features = extract_features(["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG"])

# From a file
features = extract_features("peptides.fa")
```

---

### aac_composition(sequences)

Compute amino acid composition (AAC).

**Parameters:**
- `sequences`: `List[str]` - list of peptide sequences

**Returns:**
- `pd.DataFrame`: 20 columns (AAC_A, AAC_C, ... AAC_Y)

---

### dpc_composition(sequences, step=1)

Compute dipeptide composition (DPC).

**Parameters:**
- `sequences`: `List[str]` - list of peptide sequences
- `step`: `int` (default 1) - step size; 1 means consecutive dipeptides

**Returns:**
- `pd.DataFrame`: 400 columns (DPC_AA, DPC_AC, ... DPC_WY)

---

### predict_toxicity(sequences, threshold=0.38)

Predict the toxicity of peptide sequences.

**Parameters:**
- `sequences`: `List[str]` or `str` - peptide sequences or a file path
- `threshold`: `float` (default 0.38) - toxicity threshold

**Returns:**
- `pd.DataFrame` containing:
  - `Name`: sequence name
  - `Sequence`: peptide sequence
  - `Length`: sequence length
  - `Toxicity_Score`: toxicity score (0-1)
  - `Prediction`: "Toxin" or "Non-Toxin"

---

### batch_predict_from_file(input_file, output_file='toxinpred_results.csv', threshold=0.38)

Batch prediction from a file, saving the results.

**Parameters:**
- `input_file`: `str` - input file path (FASTA or one sequence per line)
- `output_file`: `str` (default "toxinpred_results.csv") - output CSV path
- `threshold`: `float` (default 0.38) - toxicity threshold

**Returns:**
- `pd.DataFrame` - prediction results

---

### read_fasta(file_path)

Read a FASTA-format file.

**Parameters:**
- `file_path`: `str` - FASTA file path

**Returns:**
- `Tuple[List[str], List[str]]`: (list of sequence names, list of sequences)

---

### calculate_toxicity_score(sequence)

Compute a simplified toxicity score based on sequence composition.

**Parameters:**
- `sequence`: `str` - peptide sequence

**Returns:**
- `float`: toxicity score (0-1)

**Note:** This is a simplified rule-based score, not an ML model.
