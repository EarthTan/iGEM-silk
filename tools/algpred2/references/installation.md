> **English** | [中文](installation.zh.md)

# AlgPred2 Installation and Environment Configuration

## Environment Requirements

- **Platform**: macOS / Linux / Windows (via WSL)
- **Python**: >= 3.11
- **Package manager**: uv (mandatory, not pip)

## Installation Steps

### 1. Initialize the Project

```bash
cd algpred2-risk-prediction
uv init --no-readme
```

### 2. Install AlgPred2 and Its Dependencies

```bash
uv add algpred2
uv add joblib
uv add "scikit-learn==1.2.2" "numpy==1.26.4"
```

> ⚠️ **Important**: you must pin `scikit-learn==1.2.2` and `numpy==1.26.4`; otherwise model pickle compatibility or binary compatibility issues may occur.

### 3. Verify the Installation

```bash
# Verify the Python import
uv run python -c "import algpred2; print(dir(algpred2))"

# Verify the CLI entry point
uv run python -c "from algpred2.python_scripts.algpred2 import main; print('CLI OK')"
```

## Dependency Version Information

| Package | Version | Description |
| --- | --- | --- |
| algpred2 | >=1.4 | Core prediction tool |
| joblib | >=1.5.3 | Required for model loading |
| scikit-learn | ==1.2.2 | **Version must be pinned** |
| numpy | ==1.26.4 | **Version must be pinned** |

## Known Issues

### Shebang Path Error

The shebang of the `.venv/bin/algpred2` script may contain an incorrect path.

**Workaround**: invoke the CLI through Python import

```bash
# Run directly (may fail)
algpred2 -h

# Python import approach (recommended)
uv run python -c "from algpred2.python_scripts.algpred2 import main; import sys; sys.argv = ['algpred2', '-h']; main()"
```

### Incomplete Dependencies

After installation AlgPred2 is **not out of the box**; additional dependencies must be installed manually.

## pyproject.toml Example

```toml
[project]
name = "algpred2-risk-prediction"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "algpred2>=1.4",
    "joblib>=1.5.3",
    "numpy==1.26.4",
    "scikit-learn==1.2.2",
]
```
