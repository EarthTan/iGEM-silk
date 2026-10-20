---
name: hemopi2
description: Trigger this skill when the user needs to predict the hemolytic activity of peptides, assess toxicity risk, or design low-hemolysis mutants. Used for antimicrobial peptide safety screening, virtual screening, toxicity prediction, and similar scenarios.
version: "1.3"
last_updated: "2026-04-11"
---

> **English** | [中文](SKILL.zh.md)

# HemoPI2 Hemolysis Prediction Tool

> ⚠️ **Timeliness statement**: This Skill was written based on actual test results from 2026-04-11. After tool versions or dependencies change, please verify whether the following information is still valid.

---

## Version and Timeliness Information

| Attribute | Value |
|------|-----|
| **Skill creation date** | 2026-04-11 |
| **Tested hemopi2 version** | 1.3 (pip install) |
| **Tested Python version** | 3.12.12 |
| **Tested torch version** | 2.11.0 |
| **Latest official version** | Check https://pypi.org/project/hemopi2/ |

> 📝 **Recommendation**: Before use, run pip show hemopi2 to confirm the version; if there is any difference, record the change in `.memory/`.

---

## Build Log (.memory/ record template)

> Each time this Skill is built or validated, briefly record in `.memory/`:
> - test date
> - specific versions installed
> - which features were actually tested
> - bugs or anomalies found

**Template:**
```markdown
# HemoPI2 Build Log

## YYYY-MM-DD
- hemopi2 version: X.X
- Python version: X.X
- Features tested: job=1, job=2, ...
- Issues found: ...
- Notes: ...
```

## What It Is

**HemoPI2** is a **peptide hemolysis prediction tool** developed by the IIITD Raghava team. It can perform the following on peptides:

1. **Classification prediction**: determine whether a sequence is "Hemolytic" or "Non-Hemolytic"
2. **HC50 regression prediction**: predict the concentration required for 50% hemolysis (μM); the lower the value, the stronger the toxicity

### Core value
- When developing antimicrobial peptides, assess in advance the risk of damage to mammalian red blood cells
- Virtual screening and risk grading of large-scale candidate peptides
- Guide the design and optimization of low-hemolysis mutants

---

## When to Use

- **Scenario 1**: You have a candidate peptide and want to quickly judge hemolysis risk → use `job=1`
- **Scenario 2**: You have a long peptide and want to know which segment is most dangerous → use `job=2` (protein scan)
- **Scenario 3**: You want to verify the effect of substituting a specific amino acid at a position → use `job=3` (single-point mutation)
- **Scenario 4**: You want to know which amino acid is best at a position → use `job=4` (full mutation scan)
- **Scenario 5**: You want to check whether a sequence contains known hemolytic/non-hemolytic feature motifs → use `job=5` (motif scan)
- **Scenario 6**: You want not only the classification but also the toxicity strength (HC50 value) → use **regression mode**

---

## Methodology (How It Works)

### Tool architecture

```
Input: FASTA-format peptide sequence (or one sequence per line)
   ↓
┌────────────────────────────────────────────┐
│                  HemoPI2                   │
├────────────────────────────────────────────┤
│  Classification (hemopi2_classification)   │
│  ├── Model 1: Random Forest (RF)           │
│  ├── Model 2: Hybrid1 (RF+MERCI)           │
│  ├── Model 3: ESM2-t6 (deep learning)      │
│  └── Model 4: Hybrid2 (ESM+MERCI)          │
├────────────────────────────────────────────┤
│  Regression (hemopi2_regression)           │
│  └── HC50 concentration prediction         │
└────────────────────────────────────────────┘
   ↓
Output: CSV file (classification/regression results)
```

### Job type methodology

| Job | Name | Essence | Analogy |
|-----|------|------|------|
| `1` | Routine prediction | The whole sequence directly yields a conclusion | Medical checkup report: tells you directly whether you are sick |
| `2` | Protein scan | Sliding window segmentation analysis | CT scan: examines layer by layer which section has a tumor |
| `3` | Single-point mutation design | Substitute a specified amino acid at a specified site | Targeted surgery: excise and replace one spot |
| `4` | Full mutation scan | Substitute all 20 amino acids at a specified site | Batch cultivation: plant 20 seeds at the same position and see how they do |
| `5` | Motif scan | Match known dangerous/safe fingerprints | Fingerprint comparison: check for a criminal record |

---

## Operations

### Environment preparation

```bash
# 1. Enter the project directory
cd /path/to/HemoPI2

# 2. Activate the virtual environment
source .venv/bin/activate

# 3. Check that the Python version is 3.12
python --version  # should show Python 3.12.x

# 4. Important: if the hemopi2 package compatibility has not been fixed yet, apply the following fix
#    (the fix changes os.system('python3') to os.system(f'{sys.executable}'))
.venv/bin/python -c "
import sys
for script in ['hemopi2_classification.py', 'hemopi2_regression.py']:
    path = f'.venv/lib/python3.12/site-packages/hemopi2/python_scripts/{script}'
    with open(path, 'r') as f:
        content = f.read()
    if 'import sys' not in content:
        content = content.replace('import os', 'import os\nimport sys')
    content = content.replace(\"os.system(f'python3 \", \"os.system(f'{sys.executable} \")
    with open(path, 'w') as f:
        f.write(content)
    print(f'{script} fixed')
"

# 5. Check that the installation succeeded
hemopi2_classification -h
hemopi2_regression -h
```

### Command quick reference

#### Classification mode (hemopi2_classification)

```bash
# Basic usage
hemopi2_classification -i input.fasta -o result.csv -j 1 -m 1 -wd workdir

# Parameter description
# -i, --input     : input FASTA file
# -o, --output    : output CSV file (default outfile.csv)
# -j, --job       : job type 1-5 (see Methodology above)
# -m, --model     : model selection 1-4
#                   1 = Random Forest (default, fast)
#                   2 = Hybrid1 (RF+MERCI, more accurate)
#                   3 = ESM2-t6 (deep learning, accurate)
#                   4 = Hybrid2 (ESM+MERCI, recommended but buggy)
# -t, --threshold : threshold 0-1 (defaults: RF/Hybrid1=0.46, ESM/Hybrid2=0.55)
# -wd, --working  : working directory (required; the script reads and writes temporary files here)
```

#### Regression mode (hemopi2_regression)

```bash
# Basic usage
hemopi2_regression -i input.fasta -o hc50_result.csv -j 1 -wd workdir

# Parameter description
# -j, --job: 1=routine prediction, 2=protein scan
```

#### Job-specific parameters

```bash
# job=3 (single-point mutation) requires extra parameters
hemopi2_classification -i input.fasta -o result.csv -j 3 -m 1 -p 5 -r A -wd workdir
# -p, --Position : mutation position (1-indexed, counting from 1)
# -r, --Residues : amino acid after mutation (single letter, e.g. A, G, K)

# job=4 (full mutation scan) only needs the position; all 20 amino acids are tried automatically
hemopi2_classification -i input.fasta -o result.csv -j 4 -m 1 -p 5 -wd workdir

# job=2 (protein scan) allows adjusting the window length
hemopi2_classification -i input.fasta -o result.csv -j 2 -m 1 -w 10 -wd workdir
# -w, --winleng : window length 8-20 (default 8)
```

---

## Inputs and Outputs

### Input format

**FASTA format (recommended)**:
```fasta
>Peptide1
KFLKKIAKVI
>Peptide2
GLFDIVKKVG
```

**Simple format (one sequence per line)**:
```
KFLKKIAKVI
GLFDIVKKVG
```

### Output format

#### Classification output (job=1)
```csv
SeqID,Sequence,ML Score,Prediction
Peptide1,KFLKKIAKVI,0.100,Non-Hemolytic
Peptide2,GLFDIVKKVG,0.235,Non-Hemolytic
Peptide3,LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES,0.815,Hemolytic
```
- `ML Score`: hemolysis risk score (0-1); the higher, the more dangerous
- `Prediction`: Hemolytic / Non-Hemolytic

#### Regression output (HC50)
```csv
SeqID,Sequence,HC50(μM),Prediction
Peptide1,KFLKKIAKVI,177.647,Non-Hemolytic
Peptide3,LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES,18.949,Hemolytic
```
- `HC50(μM)`: concentration required for 50% hemolysis; the lower the value, the stronger the toxicity

#### Protein scan output (job=2)
```csv
SeqID,Pattern ID,Start,End,Sequence,ML Score,Prediction
Peptide3,Pattern_1,1,10,LLGDFFRKSK,0.270,Non-Hemolytic
Peptide3,Pattern_2,2,11,LGDFFRKSKE,0.270,Non-Hemolytic
...
```
Shows the score of each window along the sequence, making it possible to locate the highest-risk segment

#### Mutation design output (job=3)
```csv
SeqID,Original Sequence,ML Score,Prediction,Mutant Sequence,Position,ML Score,Prediction
Peptide1,KFLKKIAKVI,0.1,Non-Hemolytic,AFLKKIAKVI,1,0.12,Non-Hemolytic
```
Comparison of the original sequence with the mutated sequence

#### Full mutation scan output (job=4)
```csv
SeqID,Mutant_ID,Sequences,ML Score,Prediction
Peptide1,Original_Seq1,KFLKKIAKVI,0.100,Non-Hemolytic
Peptide1,Mutant_K1A,AFLKKIAKVI,0.120,Non-Hemolytic
Peptide1,Mutant_K1C,CFLKKIAKVI,0.270,Non-Hemolytic
...
```
Predictions after substituting all 20 amino acids at that position

#### Motif scan output (job=5)
```csv
SeqID,Positive Hits,Negative Hits,Prediction
Peptide1,0,1,Non-Haemolytic
Peptide2,0,1,Non-Haemolytic
```
- `Positive Hits`: number of matched hemolysis-related motifs
- `Negative Hits`: number of matched non-hemolysis-related motifs

---

## Examples

### Example 1: quickly judging the hemolysis risk of a peptide

```bash
# Predict with the RF model
hemopi2_classification -i test.fasta -o result.csv -j 1 -m 1 -wd workdir

# View the results
cat workdir/result.csv
```

### Example 2: locating the most dangerous segment in a long peptide

```bash
# Window scan of a 30-amino-acid peptide (window=10)
hemopi2_classification -i long_peptide.fasta -o scan.csv -j 2 -m 1 -w 10 -wd workdir

# Analyze the results: find the highest-scoring window
# High-scoring windows (>0.5) are the most dangerous segments
```

### Example 3: verifying whether substituting alanine at position 5 reduces hemolysis

```bash
# Single-point mutation test
hemopi2_classification -i test.fasta -o mutant.csv -j 3 -m 1 -p 5 -r A -wd workdir

# Compare the original score with the mutated score
```

### Example 4: systematically finding the best substitution at position 1

```bash
# Full mutation scan (all 20 amino acids tried automatically)
hemopi2_classification -i test.fasta -o all_mutants.csv -j 4 -m 1 -p 1 -wd workdir

# Find the mutant with the lowest ML Score in the results
```

### Example 5: predicting the HC50 toxic concentration

```bash
# Regression mode
hemopi2_regression -i test.fasta -o hc50.csv -j 1 -wd workdir

# HC50 < 50 μM usually indicates high toxicity
# HC50 > 100 μM usually indicates low toxicity
```

### Example 6: batch prediction of multiple peptides (suitable for virtual screening)

```bash
# Prepare a FASTA file (multiple sequences)
cat > peptides.fasta << 'EOF'
>Candidate1
KFLKKIAKVI
>Candidate2
GLFDIVKKVG
>Candidate3
LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES
EOF

# Batch prediction
hemopi2_classification -i peptides.fasta -o screening.csv -j 1 -m 1 -t 0.46 -wd workdir

# Coarse screening with a higher threshold (keep only low-risk peptides)
hemopi2_classification -i peptides.fasta -o safe.csv -j 1 -m 1 -t 0.7 -wd workdir
```

---

## Limits and Boundaries

### Known limitations

1. **Sequence length limit**: sequences longer than 40 amino acids are truncated (first 40 positions)
2. **Hybrid2 bug**: Model 4 has a MERCI file path bug in some cases (missing `/`)
3. **Python version**: requires Python 3.11 or 3.12 (3.13+ is not supported)
4. **Unsupported amino acids**: sequences containing B, J, O, U, X, Z raise an error

### ⚠️ hemopi2 package compatibility fix

**Problem description:**
hemopi2 v1.3 internally uses `os.system('python3 ...')` to invoke the system Python rather than the venv Python. When the system Python version is ≥ 3.14, it fails because `csv.writer(delimiter='\n')` is no longer accepted.

**Symptom:**
```
ValueError: bad delimiter value
```

**Solution:**
The hemopi2 package in the venv must be fixed, replacing `python3` with `sys.executable`:

```bash
cd HemoPI2

# Fix hemopi2_classification.py
.venv/bin/python -c "
import sys
script_path = '.venv/lib/python3.12/site-packages/hemopi2/python_scripts/hemopi2_classification.py'
with open(script_path, 'r') as f:
    content = f.read()
if 'import sys' not in content:
    content = content.replace('import os', 'import os\\nimport sys')
content = content.replace(\"os.system(f'python3 \", \"os.system(f'{sys.executable} \")
with open(script_path, 'w') as f:
    f.write(content)
print('hemopi2_classification.py fixed')
"

# Fix hemopi2_regression.py
.venv/bin/python -c "
import sys
script_path = '.venv/lib/python3.12/site-packages/hemopi2/python_scripts/hemopi2_regression.py'
with open(script_path, 'r') as f:
    content = f.read()
if 'import sys' not in content:
    content = content.replace('import os', 'import os\\nimport sys')
content = content.replace(\"os.system(f'python3 \", \"os.system(f'{sys.executable} \")
with open(script_path, 'w') as f:
    f.write(content)
print('hemopi2_regression.py fixed')
"
```

**Note:** this fix must be executed after the venv is activated. If the hemopi2 package is reinstalled, the fix must be applied again.

### Version verification commands

```bash
# Show the installed version
pip show hemopi2

# Show the Python version
python --version

# Check whether torch is installed
python -c "import torch; print(torch.__version__)"

# Verify whether the hemopi2 package has been fixed (check the use of sys.executable)
grep -l "sys.executable" .venv/lib/python3.12/site-packages/hemopi2/python_scripts/*.py
# If two script names are printed, the fix has been applied
```

### Not applicable scenarios

- Non-peptide molecules (only amino acid sequences are supported)
- Peptides with unknown modifications (for chemically modified peptides, the older HemoPI-MOD is recommended)
- Red blood cells from species other than mammals (the model was trained on mammalian RBCs)

### Notes

- **Threshold selection**: the default threshold is not optimal and can be adjusted for the actual dataset
  - Conservative screening (retain as much as possible): use a high threshold such as 0.7
  - Lenient screening (only remove high risk): use a low threshold such as 0.4
- **First run**: the ESM2 model downloads pre-trained weights on first use and requires a network connection
- **Working directory**: the `-wd` parameter is required, and the path should not contain special characters

---

## Quick Reference Card

```
╔════════════════════════════════════════════════════════════════╗
║                    HemoPI2 Quick Reference                     ║
╠════════════════════════════════════════════════════════════════╣
║ Classification     │ hemopi2_classification -i X -o Y -j 1     ║
║ HC50 regression    │ hemopi2_regression -i X -o Y -j 1         ║
║ Locate risk zones  │ -j 2 -w 10                                ║
║ Single mutation    │ -j 3 -p 5 -r A                            ║
║ Full mutation scan │ -j 4 -p 5                                 ║
║ Motif scan         │ -j 5                                      ║
╠════════════════════════════════════════════════════════════════╣
║ Model choice       │ -m 1(RF) 2(Hybrid1) 3(ESM2) 4(Hybrid2)    ║
║ Thresholds         │ RF: 0.46 / ESM: 0.55                      ║
╚════════════════════════════════════════════════════════════════╝
```

---

## Version Update Check

> After a new version of the tool is released, usage or features may change. Check before use:

```bash
# 1. Check the latest version on pip
pip index versions hemopi2

# 2. View the currently installed version
pip show hemopi2

# 3. Check whether GitHub has updates
# https://github.com/raghavagps/HemoPI2/releases
```

If a version update exists, record the changes in `.memory/`.

---

## Citations

- Paper: Rathore et al., Commun Biol 8, 176 (2025)
- Website: https://webs.iiitd.edu.in/raghava/hemopi2/
- GitHub: https://github.com/raghavagps/HemoPI2
- PyPI: https://pypi.org/project/hemopi2/
