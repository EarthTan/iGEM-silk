> English translation of [install.md](install.md). The Chinese original is kept unchanged as the source of truth.

# GraphCPP Installation Guide

## ⚠️ Important: pre-trained model, usable out of the box

GraphCPP provides an **official pre-trained model** at `model/checkpoints/epoch=22-step=69.ckpt`.

**You do not need to train the model yourself**. After installing the dependencies, simply load the model to start predicting.

To retrain the model if needed (optional):
```bash
python main.py --dataset dataset  # full training
python cv.py                      # cross-validation
```

## Environment Requirements

- Python 3.9+
- CUDA 11.7+ (optional, for GPU acceleration)
- Memory: 4GB+ (batch of 100)

## Installing with uv (recommended)

```bash
cd GraphCPP/
uv init --no-readme
source .venv/bin/activate

# Install the core dependencies
uv pip install torch rdkit deepchem lightning streamlit torchvision

# Install the torch-geometric dependencies (requires special handling)
uv pip install --no-build-isolation torch-scatter torch-sparse
uv pip install torch-geometric
```

## Installing with conda/mamba (alternative)

```bash
# GPU version
mamba env create -f environment.yml
mamba activate graphcpp

# CPU version
mamba env create -f cpu.yml
mamba activate graphcpp_cpu
```

## Dependency List

| Package | Version requirement | Purpose |
|----|---------|------|
| python | 3.9+ | Runtime environment |
| pytorch | 1.13.1+ | Deep learning framework |
| pytorch-geometric | 2.3.0+ | Graph neural network |
| rdkit | 2022.09.5+ | Molecular processing |
| deepchem | 2.7.1+ | Molecular featurization |
| lightning | 2.0.1+ | Training framework |
| streamlit | 1.21.0+ | Web UI |
| torchvision | 0.14.1+ | Dataset utilities |

## Verifying the Installation

```bash
source .venv/bin/activate
python -c "import torch; import rdkit; import deepchem; import lightning; import torch_geometric; print('All imports successful!')"
```

## Common Issues

### Insufficient CUDA memory

```python
# Use the CPU version
model = GraphCPPModule.load_from_checkpoint(
    checkpoint_path="model/checkpoints/epoch=22-step=69.ckpt",
    map_location=torch.device('cpu')
)
```

### Missing tensorflow/dgl and similar dependencies

These are optional dependencies and do not affect the core prediction functionality:
- tensorflow: skip (needed by some DeepChem models)
- dgl: skip (alternative graph neural network backend)
- transformers: skip (needed by some pre-trained models)
