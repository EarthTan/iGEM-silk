---
name: Docker latest Tag Version Uncertainty v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, version-pinning, uv, pip, reproducibility, iGEM-silk]
validated: true
---

> **English** | [中文](latest-tag-pinning.zh.md)

# Gene Capsule: Docker latest Tag Version Uncertainty

## Experience

**Problem type**: The base image's `:latest` tag pulls different versions at different times, causing build failures from incompatible CLI arguments.

**Core strategy**: Pin a specific version number or use a more stable installation method. Do not use `:latest`.

**Key parameters**: The image tag (`:latest` vs `:0.4.30`)

`ghcr.io/astral-sh/uv:latest` pulls different versions at different times. uv removed the `--system` argument in 0.5.x, so `uv sync --system --no-dev` errors in the new version.

### Three Fix Options (in order of recommendation)

1. Pin the version: `ghcr.io/astral-sh/uv:0.4.30`
2. Use `.venv/bin/python`: `CMD [".venv/bin/python", "service.py"]`
3. Fall back to pip install (more stable, independent of the uv version)

### Incorrect Pattern

```dockerfile
FROM ghcr.io/astral-sh/uv:latest   # ❌ suddenly stopped working one day
RUN uv sync --system --no-dev       # uv 0.5.x removed --system
```

### Correct Pattern

```dockerfile
FROM ghcr.io/astral-sh/uv:0.4.30   # ✅ version pinned
RUN uv sync --system --no-dev
```

## Environment Fingerprint

- **Task domain**: Docker image builds
- **Input characteristics**: Base images using `:latest` or floating tags
- **Constraints**: Build steps that depend on specific CLI arguments or behavior
- **Not applicable**: Images using a fixed version number or digest

## Audit Record

- **Validation method**: Reproduced during the full iGEM-silk Docker build
- **Failure case**: `uv sync --system --no-dev` reported `unexpected argument '--system' found` on the latest version
- **Fix validation**: After pinning to 0.4.30 the build passed

## Usage

- **Trigger conditions**: A previously working Docker build suddenly fails with a CLI argument error
- **How to invoke**: Check whether the base image has a breaking change → pin to a known working version
- **Caveats**: Not just uv—any base image with a `:latest` tag carries this risk
