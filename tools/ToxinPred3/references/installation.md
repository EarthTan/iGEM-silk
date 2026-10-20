> **English** | [中文](installation.zh.md)

# ToxinPred 3.0 Detailed Installation Guide

## Environment Preparation

### Using uv to Manage the Virtual Environment (Recommended)

```bash
# In the ToxinPred3 directory
cd ToxinPred3
uv venv .venv
source .venv/bin/activate
```

### Dependency Installation

```bash
uv pip install numpy pandas scikit-learn
```

## Installing the toxinpred3 Package (Optional)

```bash
uv pip install toxinpred3
```

Verify after installation:
```bash
uv run toxinpred3 -h
```

## Using the Standalone Module

Copy `toxinpred_features.py` into your project directory:

```bash
cp skills/toxinpred3/toxinpred_features.py /your/project/path/
```

## FAQ

### 1. pip install rejected (externally-managed-environment)

**Solution:** create a virtual environment with uv

```bash
uv venv .venv
source .venv/bin/activate
uv pip install <package>
```

### 2. Official CLI reports ValueError: bad delimiter

**Cause:** pandas version compatibility issue

**Solution:** use the standalone module

```python
from toxinpred_features import batch_predict_from_file
batch_predict_from_file("input.fa", "output.csv")
```

### 3. Model loading issues on Python 3.14+

**Solution:** use the standalone module, which does not depend on a pretrained model

## Suggested Directory Structure

```
your_project/
├── .venv/                 # Virtual environment
├── pyproject.toml         # Project configuration
├── toxinpred_features.py   # Standalone module
├── peptides.fa            # Input file
└── predictions.csv        # Output file
```
