---
name: Structure Prediction Microservice Docker and Model Patterns v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, cuda, pytorch, structure-prediction, microservice, esmfold, omegafold]
validated: true
---

> **English** | [中文](structure-service-pattern.zh.md)

# Gene Capsule: Structure Prediction Microservice Docker and Model Patterns

## Experience

**Problem type**: A set of standardized decisions for configuring Docker images, CUDA environments, model caches, and Python package management for native Python protein structure prediction microservices (ESMFold / OmegaFold, etc.).

**Core strategy** (a set of related best practices):

1. **Docker base image selection**: GPU structure prediction services uniformly use `nvidia/cuda:12.1.0-runtime-ubuntu22.04`, and also install `curl` for health checks. Services that need nvcc compilation (such as openfold) switch to the `devel` tag
2. **PyTorch CUDA wheel**: Always specify `--index-url https://download.pytorch.org/whl/cu121` (or the matching CUDA version), otherwise pip installs the CPU-only torch
3. **pip interpreter path**: In Docker images with multiple Python versions, use `python3.11 -m pip install` rather than `pip install` to avoid interpreter version mismatch
4. **`torch.cuda.empty_cache()` guard**: Always wrap it in `if torch.cuda.is_available():`, otherwise it crashes in CPU/MPS environments
5. **pLDDT confidence normalization**: ESMFold's raw b_factor ranges 0-100, but `StructureResult.confidence` is constrained to `le=1.0`, so it must be divided by 100
6. **pyproject.toml package name shadowing**: The package name must not be the same as an upstream pip package name (e.g. "omegafold" → "omegafold-service"), otherwise `pip install` of the upstream package silently fails
7. **Shared model cache**: Point `TORCH_HOME` at `tools/models/fair-esm/` and reuse it across services (ESMFold, BepiPred, pLM4CPPs). Mounted as a Docker volume
8. **OmegaFold cache environment variable**: `OMEGAFOLD_CACHE` defaults to `~/.cache/omegafold_ckpt/`; inside Docker set it to `/app/tools/models/omegafold`
9. **Async job endpoints**: The `StructureService` template supports `enable_async=True` to enable async job endpoints. Before use, confirm that the local/target branch includes this feature

**Key parameters**:
- Base image: `nvidia/cuda:12.1.0-runtime-ubuntu22.04` (runtime) / `nvidia/cuda:12.1.0-devel-ubuntu22.04` (devel, includes nvcc)
- Torch index: `https://download.pytorch.org/whl/cu121`
- Model cache: `TORCH_HOME` → `tools/models/fair-esm/` (volume mount)
- pLDDT normalization: `b_factor / 100.0` → confidence

## Environment Fingerprint

- **Task domain**: Docker containerization + GPU deployment of protein structure prediction microservices
- **Input characteristics**: Python microservices using the `StructureService` template, depending on PyTorch CUDA + large protein models
- **Constraints**: CUDA 12.1; multiple Python versions coexisting in one image; model caches shared between services; package names may conflict with pip upstream
- **Not applicable**:
  - CPU-only inference services (no CUDA-related configuration needed)
  - FASTA scoring services (`FastaToolService` template, a different pattern)
  - Docker-in-Docker services (such as AF3 and PEP-FOLD4, which have their own DinD mode)

## Audit Record

- **Validation method**: Docker build + run validation of the iGEM-silk ESMFold, OmegaFold, BepiPred-3.0 and other services
- **Test cases**:
  1. Build ESMFold with `nvidia/cuda:runtime` → uvicorn starts + model loads + structure prediction OK
  2. With the `omegafold` package name conflict unfixed, `pip install omegafold` → the local package shadows upstream → OK after renaming to `omegafold-service`
  3. Unnormalized pLDDT scores are rejected by `pydantic` validation → pass after dividing by 100
- **Success rate**: 100% (all structure prediction services adopt this pattern and run stably)
- **Limitations**: Does not cover the special configuration of Docker-in-DinD services; when the CUDA version is upgraded, `--index-url` must be updated in sync; the availability of `enable_async` depends on the branch version

## Usage

- **Trigger conditions**: Adding a new structure prediction microservice (ESMFold, OmegaFold and other services using the `StructureService` template)
- **How to invoke**: Copy the pattern from an existing Dockerfile (such as `tools/ESMFold/Dockerfile`); set the corresponding environment variables and volume mounts
- **Caveats**:
  - When multiple Python versions are mixed, always use `python3.11 -m pip` rather than `pip`
  - Use a `-service` suffix for `[project] name` in `pyproject.toml` to avoid package name conflicts
  - `curl` must be installed (the health check depends on it) — slim images do not include curl by default
  - The shared model cache directory must be identical across all services, mounted via Docker Compose volumes
