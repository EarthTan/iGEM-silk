---
name: mhcflurry
description: Trigger this skill when the user needs to predict MHC class I peptide binding affinity. It uses deep learning models to predict the binding strength between peptides and MHC molecules, supporting multiple alleles and batch processing.
created: 2026-04-18
version: 1.0.0
last_updated: 2026-04-25
---

> English translation of [SKILL.md](SKILL.md). The Chinese original is kept unchanged as the source of truth.

# MHCflurry

## What It Is
MHCflurry is a deep learning based MHC class I peptide binding affinity prediction tool. It uses pre-trained neural network models to predict the binding strength between peptides and major histocompatibility complex (MHC) molecules, providing key information for vaccine design and immunogenicity assessment.

## When to Use
- **Vaccine design**: identify potential T-cell epitopes
- **Immunogenicity assessment**: predict the MHC binding ability of peptides
- **Cancer immunotherapy**: screen tumor neoantigens
- **Autoimmune disease research**: identify autoreactive peptides
- **High-throughput screening**: batch-analyze potential epitopes in a proteome

## Methodology
MHCflurry predicts using the following methods:
1. **Deep learning model**: neural network based binding affinity prediction
2. **Allele specificity**: supports more than 14000 MHC alleles
3. **Affinity scoring**: provides IC50 values (half-maximal inhibitory concentration) and percentile ranks
4. **Binding classification**: classifies peptides into binders or non-binders based on thresholds (strong binder ≤50nM, weak binder 50-500nM, non-binder >500nM)

## Operations

### Installation

Create a virtual environment with uv and install the dependencies:

```bash
cd MHCflurry/
uv sync
```

### Downloading the pre-trained models

The pre-trained models must be downloaded before first use:

```python
import sys

# Python 3.14 compatibility patch
if sys.version_info >= (3, 13):
    import shutil
    class FakePipes:
        @staticmethod
        def quote(s):
            import shlex
            return shlex.quote(s)
    sys.modules['pipes'] = FakePipes()

from mhcflurry.downloads_command import run
run()
```

Or use subprocess:

```python
import subprocess
import sys

wrapper_code = '''
import sys
import shutil
class FakePipes:
    @staticmethod
    def quote(s):
        import shlex
        return shlex.quote(s)
sys.modules['pipes'] = FakePipes()
from mhcflurry.downloads_command import run
run()
'''

subprocess.run([sys.executable, '-c', wrapper_code, 'fetch', 'models_class1_pan'])
```

### Quick start

```python
from mhcflurry import Class1AffinityPredictor

# Load the predictor
predictor = Class1AffinityPredictor.load()

# Predict a single peptide
peptides = ["SIINFEKL"]
alleles = ["HLA-A*02:01"]
predictions = predictor.predict(peptides=peptides, alleles=alleles)

print(f"Prediction: {predictions[0]:.2f} nM")

# Manually build a results table
import pandas as pd
results = []
for i, peptide in enumerate(peptides):
    for allele in alleles:
        results.append({
            "peptide": peptide,
            "allele": allele,
            "affinity_nM": predictions[i] if len(predictions) == len(peptides) else predictions[0]
        })

df = pd.DataFrame(results)
print(df)
```

### Batch prediction

```python
from mhcflurry import Class1AffinityPredictor
import pandas as pd

predictor = Class1AffinityPredictor.load()

# Batch predict multiple peptides
peptides = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL"]
alleles = ["HLA-A*02:01", "HLA-A*01:01"]

# Because predict_to_dataframe has compatibility issues, use a loop
results = []
for peptide in peptides:
    for allele in alleles:
        affinity = predictor.predict(peptides=[peptide], alleles=[allele])[0]
        results.append({
            "peptide": peptide,
            "allele": allele,
            "affinity_nM": round(affinity, 2)
        })

df = pd.DataFrame(results)
print(df)

# Filter strong binders (≤50 nM)
strong_binders = [r for r in results if r['affinity_nM'] <= 50]
print(f"\nNumber of strong binders: {len(strong_binders)}")
```

## Inputs and Outputs

- **Input**:
  - list of peptide sequences (strings, usually 8-15 amino acids)
  - list of MHC alleles (e.g. "HLA-A*02:01")
- **Output**:
  - predicted affinity values (nM; lower means stronger binding)
  - percentile rank (between 0-1; lower means stronger binding)
  - a DataFrame containing fields such as peptide, allele, prediction, percentile_rank

## Examples

1. **Check the supported alleles**:
```python
predictor = Class1AffinityPredictor.load()
print(f"Supports {len(predictor.supported_alleles)} alleles")
print("First 5:", predictor.supported_alleles[:5])
```

2. **Vaccine candidate screening**:
```python
# Read peptide sequences from FASTA
from Bio import SeqIO
peptides = [str(record.seq) for record in SeqIO.parse("vaccines.fasta", "fasta")]

# Batch prediction (loop workaround)
predictor = Class1AffinityPredictor.load()
results = []
for peptide in peptides:
    for allele in ["HLA-A*02:01", "HLA-B*07:02"]:
        affinity = predictor.predict(peptides=[peptide], alleles=[allele])[0]
        results.append({
            "peptide": peptide,
            "allele": allele,
            "affinity_nM": affinity
        })

import pandas as pd
df = pd.DataFrame(results)

# Filter strong binders
strong = [r for r in results if r['affinity_nM'] <= 50]
print(f"Number of strong binders: {len(strong)}")
```

## References Index

| File | Contents |
|------|----------|
| `references/mhcflurry_guide.md` | Detailed usage guide, API reference, performance optimization, and troubleshooting |
| `references/allele_support.md` | List of supported MHC alleles and selection guidance |
| `references/threshold_explanation.md` | Explanation of binding thresholds and customization methods |
