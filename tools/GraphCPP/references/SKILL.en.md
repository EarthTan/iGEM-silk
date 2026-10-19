---
name: graphcpp
description: Trigger this skill when the user needs a graph neural network to predict cell-penetrating peptides (CPPs). Supports local batch prediction and feature export, and can serve as the signal source for the delivery module in the fusion engine.
created: 2026-04-18
version: 1.0.0
last_updated: 2026-04-18
---

> English translation of [SKILL.md](SKILL.md). The Chinese original is kept unchanged as the source of truth.

# GraphCPP

## What It Is

GraphCPP is a graph neural network (GNN) based cell-penetrating peptide (Cell-Penetrating Peptide, CPP) prediction tool. It uses GraphSAGE convolution layers to convert peptide sequences into molecular graph representations, achieving SOTA-level CPP prediction performance (MCC 0.5787, AUC 0.8459).

**Model source**: ⚠️ **Pre-trained model, ready to load and use, no training required**

The GraphCPP repository provides an official pre-trained model (`epoch=22-step=69.ckpt`) under the `model/checkpoints/` directory. That model has already been trained and validated and is **usable out of the box**.

If retraining is needed, the repository also provides complete training code, but this is usually unnecessary.

**Problem solved**: predict whether a given peptide sequence has cell-penetrating ability

**Role in the fusion engine**:
- Sequence-level proxy for delivery / transdermal properties
- Feature input for the six-efficacy model
- Signal source for the coarse screening and the fusion engine

## When to Use

- When the cell-penetrating ability of candidate peptides needs to be predicted
- When the CPP potential of a large number of peptide sequences needs to be batch-screened
- When the CPP probability is needed as an input feature for downstream models
- When sequences with too low delivery potential need to be removed before fusion

## Methodology

### Core principles

1. **Molecular graph representation**: convert the peptide sequence into an RDKit molecular graph (atoms = nodes, chemical bonds = edges)
2. **Graph featurization**: use MolGraphConvFeaturizer to extract node and edge features
3. **Graph neural network**: use GraphSAGE convolution layers for message passing and feature learning
4. **Classification output**: binary classification probability after Sigmoid activation (threshold 0.5)

### Feature fusion

- Node embeddings output by the graph convolution layers
- Topological fingerprint
- Global representation obtained by graph pooling (mean pooling)
- Fully connected layers produce the final prediction

## Operations

### Environment installation

```bash
cd GraphCPP/
uv init --no-readme
source .venv/bin/activate

# Install the core dependencies
uv pip install torch rdkit deepchem lightning streamlit torchvision
uv pip install --no-build-isolation torch-scatter torch-sparse
uv pip install torch-geometric
```

### Predicting a single sequence

```python
import torch
import yaml
from rdkit import Chem
from graphcpp.lightning import GraphCPPModule
from graphcpp.dataset import _featurize_mol
from graphcpp.fp_generators import fp_dict

# Load the model
with open('model/hparams.yaml', 'r') as f:
    hparams = yaml.safe_load(f)
model = GraphCPPModule.load_from_checkpoint(
    checkpoint_path="model/checkpoints/epoch=22-step=69.ckpt",
    map_location=torch.device('cpu')
)
model.eval()
model.freeze()

# Prediction function
def predict_cpp(fasta_seq):
    mol = Chem.MolFromFASTA(fasta_seq)
    if mol is None:
        return None
    data = _featurize_mol(mol)
    fp = fp_dict[hparams['fingerprint_type']].GetFingerprint(mol)
    data.fp = torch.tensor([fp], dtype=torch.float32)
    
    with torch.no_grad():
        prediction = model(data)[0]
        probability = torch.sigmoid(prediction).item()
        is_cpp = probability >= 0.5
    return {'probability': probability, 'is_cpp': is_cpp}

# Example
result = predict_cpp("GRKKRRQRRRPPQ")  # TAT peptide
print(f"CPP probability: {result['probability']:.4f}")
```

### Batch prediction script

```python
import pandas as pd
from rdkit import Chem
import torch
import yaml
from graphcpp.lightning import GraphCPPModule
from graphcpp.dataset import _featurize_mol
from graphcpp.fp_generators import fp_dict

# Load the model
with open('model/hparams.yaml', 'r') as f:
    hparams = yaml.safe_load(f)
model = GraphCPPModule.load_from_checkpoint(
    checkpoint_path="model/checkpoints/epoch=22-step=69.ckpt",
    map_location=torch.device('cpu')
)
model.eval()
model.freeze()

def predict_batch(fasta_list):
    results = []
    for seq in fasta_list:
        mol = Chem.MolFromFASTA(seq)
        if mol is None:
            results.append({'sequence': seq, 'probability': None, 'is_cpp': None})
            continue
        data = _featurize_mol(mol)
        fp = fp_dict[hparams['fingerprint_type']].GetFingerprint(mol)
        data.fp = torch.tensor([fp], dtype=torch.float32)
        
        with torch.no_grad():
            prediction = model(data)[0]
            probability = torch.sigmoid(prediction).item()
            is_cpp = probability >= 0.5
        results.append({'sequence': seq, 'probability': probability, 'is_cpp': is_cpp})
    return results

# Read the FASTA file
df = pd.read_csv("candidates.csv")  # requires name and sequence columns
predictions = predict_batch(df['sequence'].tolist())
df['cpp_probability'] = [p['probability'] for p in predictions]
df['cpp_prediction'] = ['Yes' if p['is_cpp'] else 'No' for p in predictions]
df.to_csv("cpp_predictions.csv", index=False)
```

### Starting the Web UI

```bash
cd GraphCPP/
source .venv/bin/activate
streamlit run dashboard.py
# Open http://localhost:8501 in a browser
```

## Inputs and Outputs

### Input formats

**FASTA format (recommended)**
```
>Peptide1
GRKKRRQRRRPPQ
>Peptide2
RQIKIWFQNRRMKWKK
```

**SMILES format (CSV)**
```csv
name,smiles
TAT,CC(C)C(NC(=O)...
```

### Output format

| Field | Type | Description |
|------|------|------|
| Name | string | Peptide name |
| Probability | float (0-1) | CPP probability score |
| Cell-Penetrating | Yes/No | Binary classification prediction |

## Examples

**Example 1: classic CPP prediction**
```python
predict_cpp("GRKKRRQRRRPPQ")  # TAT peptide -> CPP probability > 0.9
predict_cpp("RQIKIWFQNRRMKWKK")  # Penetratin -> CPP probability > 0.9
```

**Example 2: non-CPP recognition**
```python
predict_cpp("ACDEFGHIKLMNPQRSTVY")  # random sequence -> CPP probability < 0.3
```

## Limitations

1. **Sequence length**: optimal range is 5-40 amino acids; accuracy drops above >100aa
2. **Fusion peptides**: trained on single-chain CPPs, not optimized for "functional peptide + linker + CPP" fusion structures
3. **Non-natural amino acids**: relies on RDKit's MolFromFASTA, which by default supports only the 20 standard amino acids
4. **Feature export**: the current version mainly outputs classification results; intermediate-layer features require code changes to extract

## References Index

| File | Contents |
|------|----------|
| `references/install.md` | Detailed installation instructions and dependency versions |
| `references/model-details.md` | Model architecture and training details |
| `references/dataset.md` | Dataset format and processing workflow |
