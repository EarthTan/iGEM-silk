> **English** | [中文](model-details.zh.md)

# GraphCPP Model Architecture Details

## Model Configuration

Best hyperparameters (see `config.py`):

```python
BEST_PARAMETERS = {
    'act': 'prelu',
    'conv_aggr': 'sum',
    'conv_dropout': 0.05,
    'has_bn': False,
    'has_l2norm': False,
    'layer_fingerprints': 1,
    'fingerprint_type': 'topological',
    'hidden_channels': 128,
    'layer_type': 'sageconv',
    'layers_pre_mp': 1,
    'mp_layers': 2,
    'layers_post_mp': 1,
    'pooling': 'mean',
    'stage_type': 'stack',
    'learning_rate': 0.001,
    'weight_decay': 'cosine'
}
```

## Core Components

### 1. Molecular graph featurization

Using `MolGraphConvFeaturizer`:
- `use_edges=True`: include bond type features
- `use_chirality=True`: include chirality information

### 2. Graph convolution layers

Using GraphSAGE convolution layers:
- 2 layers of message passing (`mp_layers=2`)
- Aggregate neighbor information to update node representations

### 3. Feature fusion

1. Node embeddings pass through multiple graph convolution layers
2. Combined with a topological fingerprint (generated through `fp_dict`)
3. Mean pooling produces the global graph representation
4. Fully connected layers output the prediction

## Training Objective

- **Task**: binary classification (CPP vs Non-CPP)
- **Loss function**: BCEWithLogitsLoss
- **Evaluation metrics**: MCC, AUC, Accuracy, F1

## Performance Metrics

| Metric | Value |
|------|-----|
| Val MCC | 0.6683 |
| Val AUC | 0.9288 |
| Val Accuracy | 0.8310 |
| Test MCC | 0.5787 |
| Test AUC | 0.8459 |

## Model Files

```
model/
├── checkpoints/
│   └── epoch=22-step=69.ckpt  # pre-trained model
├── hparams.yaml                 # model hyperparameters
└── metrics.csv                  # training metrics
```
