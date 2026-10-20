---
name: micromamba Approach for Dockerizing a Python 2.7 Legacy Service v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [python2.7, docker, micromamba, conda, legacy, aggrescan3d, china-network]
validated: true
---

> **English** | [中文](gep-python2.7-docker-micromamba.zh.md)

# Gene Capsule: micromamba Approach for Dockerizing a Python 2.7 Legacy Service

## Experience

**Problem description**: Aggrescan3D requires Python 2.7 + the conda package `lcbio::aggrescan3d`, and building it in a 2026 Docker environment hit multiple layers of failure:

1. Pulling `continuumio/miniconda2:latest` from Docker Hub (DaoCloud mirror) returned **403 Forbidden** (the image has been archived)
2. `python:2.7-slim` (Debian Buster) apt sources returned **404 Not Found** (Buster has entered LTS archive)
3. `mambaorg/micromamba:latest` is not on the DaoCloud mirror accelerator whitelist, so the pull was denied
4. miniforge3 has Python=3.13 but aggrescan3d **only supports Python 2.7**

**Root cause**: Docker Hub access is restricted in mainland China, and official Python 2.7 images have been removed from mainstream registries. The Debian Buster apt sources are archived, which makes `apt-get install python` fail.

### Solution

**Final approach**: `ghcr.io/mamba-org/micromamba` + an independent conda environment

```
Base image: ghcr.io/mamba-org/micromamba:latest
    ↑ from GitHub Container Registry (GHCR), directly reachable from mainland China
    ↑ micromamba is a static C++ client, no Python interpreter required

Create a Python 2.7 environment inside it:
    micromamba create -y -n a3d -c conda-forge -c lcbio python=2.7 aggrescan3d
    
Activate the environment with:
    ENV AGGRESCAN_CONDA_ENV=/opt/conda/envs/a3d
    $AGGRESCAN_CONDA_ENV/bin/python service.py
```

```dockerfile
FROM ghcr.io/mamba-org/micromamba:latest

USER root

# create the Python 2.7 + aggrescan3d environment
RUN micromamba create -y -n a3d -c conda-forge -c lcbio python=2.7 aggrescan3d \
    && micromamba clean -afy

# install uv (for microservice dependencies)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY tools/template/ ./tools/template/
COPY tools/Aggrescan3D/ ./tools/Aggrescan3D/

WORKDIR /app/tools/Aggrescan3D
RUN uv sync

ENV AGGRESCAN_CONDA_ENV=/opt/conda/envs/a3d
CMD [".venv/bin/python", "service.py"]
```

**Key innovation**: The static-binary nature of micromamba lets it work in any base image without needing a Python interpreter to install conda packages. This solves the chicken-and-egg problem — Python 2.7 is needed, yet installing conda itself requires Python.

### Image Source Selection Decision Matrix

| Image source | Python 2.7 | Reachable from mainland China | Whitelist | Conclusion |
|--------|-----------|------------|--------|------|
| Docker Hub miniconda2 | ✅ | ❌ DaoCloud proxy | ✅ (inside DaoCloud whitelist) | 403, archived |
| Docker Hub python:2.7-slim | ✅ but apt 404 | ❌ | ✅ | Buster archived |
| DaoCloud mambaorg/micromamba | ✅ (can create environment) | ✅ | ❌ **not in whitelist!** | Pull denied |
| **GHCR mamba-org/micromamba** | **✅** | **✅** | **N/A** | **Success** |
| Native pip install | ❌ no Python 2.7 | ✅ | N/A | Disallowed (Docker-only rule) |

### Similar Cases (encountered in the same session)

| Service | Problem | Final solution |
|------|------|---------|
| ToxinPred3 | `scikit-learn==1.2.2` is incompatible with Python 3.13 | micromamba creates a Python 3.8 environment (`python=3.8 scikit-learn=1.2.2`) |
| AnOxPePred | PyTorch CUDA occupies 34GB and does not release it | No Docker fix; the process must be killed to release GPU memory |

### Environment Fingerprint

- **Task domain**: Docker containerization of legacy Python code
- **Input characteristics**: Python 2.x/3.x dependencies, conda-only packages, deprecated base images
- **Constraints**: China network environment (Docker Hub unreachable), modern base image (Python 3.13+), no internet apt sources
- **Trigger pattern**: A legacy conda package fails to build in modern Docker
- **Not applicable**: Modern Python with pure pip dependencies (use `python:3.11-slim` directly); services with official Docker images; services that can be compiled from source

### Alternatives

1. **conda-pack**: Run `conda pack` on a machine with network access to package the complete environment, then COPY it into the image and extract
2. **Nix/Nixpkgs**: Better version management for Python 2.7 packages, but with a steep learning curve
3. **Docker multi-stage**: First create a Python 2.7 environment with continuumio/miniconda3, then COPY it into a slim image (glibc compatibility must be solved)

### Audit Record

- **Validation method**: The Aggrescan3D Docker image built successfully and ran; all 150 PDBs were scored
- **Test cases**:
  1. `continuumio/miniconda2:latest` → 403 Forbidden (DaoCloud)
  2. `python:2.7-slim` → apt 404 (Buster archived)
  3. `mambaorg/micromamba:latest` via DaoCloud → denied (whitelist)
  4. `ghcr.io/mamba-org/micromamba:latest` via GHCR → **build succeeded**
- **Success rate**: 100% (final approach)
- **Limitations**: The Python 2.7 environment created by micromamba contains only conda packages; pip packages need extra handling. The Python 2.7 code of aggrescan3d may encounter unexpected issues on modern Linux kernels/glibc (none were found in this run).
