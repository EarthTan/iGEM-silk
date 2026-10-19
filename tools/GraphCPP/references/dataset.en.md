> English translation of [dataset.md](dataset.md). The Chinese original is kept unchanged as the source of truth.

# GraphCPP Dataset Format

## Dataset Location

```
dataset/
├── train.csv   # training set
├── val.csv     # validation set
└── test.csv    # test set
```

## CSV Format

```csv
name,smiles,label
TAT,CC(C)C(NC(=O)...,1
Penetratin,CC(C)C(NC(=O)...,1
Random,CC(C)C(NC(=O)...,0
```

- `name`: peptide name
- `smiles`: sequence in SMILES format
- `label`: 1=CPP, 0=Non-CPP

## Data Sources

The training data mainly comes from:
- The CPP1708 dataset (1708 peptides)
- Classic CPPs (TAT, Penetratin, etc.) and their variants
- The MLCPP2 independent test set

## Featurization Workflow

1. **SMILES → RDKit Mol object**: `Chem.MolFromSmiles()`
2. **Mol → graph data**: `MolGraphConvFeaturizer`
3. **Graph data → PyG Data**: `GraphData.to_pyg_graph()`
4. **Add fingerprint**: topological fingerprint `fp_dict['topological'].GetFingerprint(mol)`

## Fusion Engine Integration

Using GraphCPP as the delivery module in the fusion engine:

```python
# Feature engineering
features = {
    'cpp_probability': predict_cpp(sequence)['probability'],
    'net_charge': calculate_charge(sequence),
    'hydrophobicity': calculate_hydrophobicity(sequence),
}

# Input to the six-efficacy model
efficacy_score = efficacy_model.predict(features)
```

## Coarse Screening Filter Example

```python
def pre_screen(peptide):
    cpp_score = predict_cpp(peptide)['probability']
    if cpp_score < 0.3:  # delivery potential too low
        return False
    if calculate_charge(peptide) > +5:  # extreme charge
        return False
    if calculate_hydrophobicity(peptide) > 0.8:  # extreme hydrophobicity
        return False
    return True

candidates = [p for p in all_candidates if pre_screen(p.sequence)]
```
