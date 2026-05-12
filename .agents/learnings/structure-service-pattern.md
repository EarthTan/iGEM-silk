---
name: Structure Service Docker & Model Patterns
description: Native Python structure services (ESMFold/OmegaFold) — Docker base image, torch CUDA wheel, model cache dirs, pyproject naming
type: reference
---

When adding a native Python structure prediction microservice (non-DinD):

- **Docker base**: `nvidia/cuda:12.1.0-runtime-ubuntu22.04` for GPU services; always install `curl` for healthchecks
- **PyTorch CUDA**: always use `--index-url https://download.pytorch.org/whl/cu121` or the matching CUDA version, otherwise pip installs CPU-only torch
- **pip interpreter**: use `python3.11 -m pip install` instead of `pip install` to avoid interpreter mismatch in multi-Python Docker images
- **`torch.cuda.empty_cache()`**: always guard with `if torch.cuda.is_available():` — crashes on CPU/MPS otherwise
- **pLDDT normalization**: raw ESMFold b_factor is 0-100, but `StructureResult.confidence` has `le=1.0`. Must divide by 100.
- **pyproject.toml naming**: the package name must not shadow the upstream pip package name (e.g. "omegafold" → "omegafold-service"), or `pip install` of the upstream will fail silently
- **Shared model cache**: via `TORCH_HOME` pointing to `tools/models/fair-esm/` across services (ESMFold, BepiPred, pLM4CPPs). Mount as Docker volume.
- **OmegaFold cache**: `OMEGAFOLD_CACHE` env var, default `~/.cache/omegafold_ckpt/`, in Docker set to `/app/tools/models/omegafold`
- **enable_async**: the `StructureService` template on `origin/deploy` supports `enable_async=True` for async job endpoints, but local/stale checkouts may not have it. Always verify against `origin/deploy`.
