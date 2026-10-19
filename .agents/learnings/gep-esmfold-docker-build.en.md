---
name: ESMFold Docker Three-Layer Build Pattern v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [esmfold, docker, buildkit, cuda, dockerfile]
validated: true
---

> English translation of [gep-esmfold-docker-build.md](gep-esmfold-docker-build.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: ESMFold Docker Three-Layer Build Pattern

## Experience

**Problem type**: Building the ESMFold microservice Docker image—optimizing build speed and cache reuse in a CUDA 12.1 + Python 3.10 environment.

**Core strategy**:
1. A three-layer Dockerfile structure separated by change frequency: apt+torch (almost never changes) → openfold CUDA compilation (~12min, rarely changes) → pip dependencies (change often)
2. Use `nvidia/cuda:12.1.0-devel-ubuntu22.04` as the base image (the devel tag includes nvcc; the runtime tag does not, and openfold CUDA compilation needs nvcc)
3. The numpy version must be pinned in Layer 1 together with torch (`numpy<2`); do not add it in Layer 3—deepspeed loads numpy at import time, and installing it too late breaks things
4. Never merge Layer 2 and Layer 3—openfold compilation is the main time cost and pip dependencies change often; once merged, every dependency change recompiles openfold
5. Expect a build size of ~12.7GB; be prepared for it

**Key parameters**:

| Layer | Contents | Change frequency | Build time |
|---|---|---|---|
| Layer 1 | apt (python3.10, build-essential, ninja, git) + pip install torch + `numpy<2` | Very low | ~2min |
| Layer 2 | pip install openfold v2.2.0 from GitHub (CUDA compilation) | Low | ~12min |
| Layer 3 | pip install (biotite, deepspeed≥0.9, fastapi≥0.100, fair-esm==2.0.0) | High | ~1min |

Build command: `docker build -f tools/ESMFold/Dockerfile -t igem-silk/esmfold:latest .`

## Environment Fingerprint

- **Task domain**: Python Docker microservice builds, GPU/CUDA environments, protein structure prediction
- **Input characteristics**: Multi-layer Dockerfile including a CUDA compilation step (openfold) and a long dependency chain
- **Constraints**: CUDA 12.1 + Python 3.10 + Ubuntu 22.04 base image; the devel tag is mandatory (contains nvcc); image size ~12.7GB
- **Not applicable**:
  - CPU-only environments (ESMFold requires a GPU)
  - Cache behavior is inconsistent with `docker compose build`; use `docker build -f Dockerfile` directly
  - Python 3.11+ (openfold has a `not` argument-name conflict)
  - Scenarios requiring a small image (base image ~3GB, openfold build artifacts ~5GB)
  - Using the `nvidia/cuda:runtime` tag (missing nvcc)
- **Note**: `docker compose build` cache behavior may differ from `docker build`. In CI, use `docker build -f Dockerfile .` directly

## Audit Record

- **Validation method**: Docker build + in-container startup + structure prediction validation
- **Test cases**:
  1. Build: `docker build -f tools/ESMFold/Dockerfile -t igem-silk/esmfold:latest .` → succeeded (12.7GB)
  2. Startup: `docker run --gpus all igem-silk/esmfold:latest` → uvicorn starts, the model finishes loading in 75s
  3. Prediction: a 6-residue peptide YDFYTP → returns a PDB in 2.3s, `confidence=0.556`
- **Success rate**: 100% (3/3 validations passed)
- **Limitations**: The first build takes ~15min (openfold CUDA compilation accounts for 12min); the image is ~12.7GB; not suitable for high-frequency CI triggers

## Usage

- **Trigger conditions**: Any Dockerfile modification, dependency version change, or base image upgrade in an ESMFold-related microservice
- **How to invoke**: Refer to the three-layer structure of `tools/ESMFold/Dockerfile`
- **Caveats**:
  - When upgrading the CUDA version, update the PyTorch wheel URL accordingly (`--index-url https://download.pytorch.org/whl/cu121`)
  - When the openfold version changes, check fair-esm compatibility at the same time (see gep-esmfold-dependency-matrix.md)
  - Model weights are mounted via volume at `tools/models/` and are not baked into the image
  - If `docker compose build` behaves abnormally, fall back to building directly with `docker build -f Dockerfile .`
