---
name: slim Image Missing C Extension Build Dependencies v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, slim-image, build-deps, c-extensions, pip, iGEM-silk]
validated: true
---

> English translation of [slim-image-build-deps.md](slim-image-build-deps.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: slim Image Missing C Extension Build Dependencies

## Experience

**Problem type**: The slim base image lacks the headers and toolchain needed to compile C extensions, so pip install fails when installing packages with native extensions.

**Core strategy**: In any slim-image Dockerfile that installs native extensions via pip, the standard configuration should include the build dependencies: `gcc python3-dev pkg-config`.

**Key parameters**: `gcc`, `python3-dev`, `pkg-config`

`python:3.11-slim` does not include the headers and toolchain needed to compile C extensions. `pip install freesasa` needs `python3-dev` and `pkg-config`.

### Incorrect Pattern

```dockerfile
FROM python:3.11-slim
RUN pip install freesasa    # ❌ missing build dependencies, reports fatal error: Python.h: No such file or directory
```

### Standard Configuration

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev pkg-config libxml2-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install freesasa    # ✅ compiles successfully
```

## Environment Fingerprint

- **Task domain**: Python Docker image builds
- **Input characteristics**: A `python:slim` base image + pip installation of packages containing C extensions
- **Constraints**: The pip package depends on native C extensions (e.g. FreeSASA, numpy built from source, etc.)
- **Not applicable**: Pure Python packages, wheel-based installs, or the full `python:3.11` image

## Audit Record

- **Validation method**: iGEM-silk SASA service Docker build failure
- **Failure case**: `pip install freesasa` → `fatal error: Python.h: No such file or directory`
- **Fix validation**: After adding `gcc python3-dev pkg-config`, it compiles successfully

## Usage

- **Trigger conditions**: pip install reports `fatal error: Python.h: No such file or directory` or `error: command 'gcc' failed`
- **How to invoke**: Add `apt-get install gcc python3-dev pkg-config` before `pip install`
- **Caveats**: Clean the apt cache after installing (`rm -rf /var/lib/apt/lists/*`) to reduce the image size
