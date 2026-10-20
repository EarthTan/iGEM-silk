---
name: ESMFold Dependency Version Matrix v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [esmfold, docker, dependencies, openfold, fair-esm, cuda]
validated: true
---

> **English** | [中文](gep-esmfold-dependency-matrix.zh.md)

# Gene Capsule: ESMFold Dependency Version Matrix

## Experience

**Problem type**: Troubleshooting and fixing dependency version conflicts during the ESMFold microservice Docker build

**Core strategy**:
1. Trace the root cause from the full error stack; do not guess from the last line
2. Use elimination to confirm versions that are not directly related (pydantic/fastapi are not the key)
3. Once the key conflict is found (openfold IPA key mismatch), solve it in two directions: downgrade openfold or upgrade fair-esm
4. Downgrading openfold does not work (CUDA 12.x does not support sm_37) → take the `strict=False` route
5. Settle cascading dependency upgrades in one shot rather than one at a time (upgrade the deepspeed→pydantic→fastapi trio together)

**Key parameters**:

| Component | Available versions | Final choice | Reason |
|---|---|---|---|
| openfold | v1.0.1 (IPA-compatible, CUDA 12 build fails), v2.2.0 (builds, IPA incompatible) | **v2.2.0** + `strict=False` | The layers missing from IPA are randomly initialized and do not affect the rest of the model |
| fair-esm | 2.0.0 (PyPI version matches the checkpoint), GitHub HEAD (IPA path updated but even less compatible) | **2.0.0** | The only version that matches `esmfold_3B_v1.pt` |
| deepspeed | 0.5.9 (too old, missing `deepspeed.comm`), ≥0.9 (supports the new API) | **≥0.9.0** | Required by openfold v2.2.0 |
| fastapi + pydantic | 0.99 + 1.x (incompatible with deepspeed≥0.9), ≥0.100 + 2.x (compatible) | **≥0.100 + ≥2.0** | deepspeed≥0.9 forces an upgrade to pydantic v2 |

## Environment Fingerprint

- **Task domain**: Python Docker microservice builds, GPU/CUDA environments
- **Input characteristics**: Multi-layer dependency chain `fair-esm → openfold → deepspeed → pydantic → fastapi`
- **Constraints**: CUDA 12.1 + Python 3.10 + Ubuntu 22.04 base image
- **Key signal**: Seeing `linear_q_points.linear.weight` missing keys → immediately lock onto the openfold version problem
- **Not applicable**: Python 3.11+ (openfold has a `not` argument-name conflict); CPU-only environments (ESMFold requires a GPU)

## Audit Record

- **Validation method**: Docker build + in-container `POST /predict` structure prediction validation
- **Test cases**:
  1. Build: `docker build -f tools/ESMFold/Dockerfile -t igem-silk/esmfold:latest .` → succeeded (12.7GB)
  2. Startup: `docker run --gpus all igem-silk/esmfold:latest` → uvicorn starts, the model finishes loading in 75s
  3. Prediction: a 6-residue peptide YDFYTP → returns a PDB in 2.3s, `confidence=0.556`
- **Success rate**: 100% (3/3 validations passed)
- **Limitations**: The IPA projection layer weights are randomly initialized, and the structure prediction quality has not been quantitatively benchmarked (see Issue #15)

## Usage

- **Trigger conditions**: Any Dockerfile/pyproject change in an ESMFold-related microservice
- **How to invoke**: Refer to the three-layer structure of `tools/ESMFold/Dockerfile` and the model loading logic in `tools/ESMFold/service.py`
- **Caveats**: Never use `esm.pretrained.esmfold_v1()`; construct `ESMFold` directly with `strict=False` instead
