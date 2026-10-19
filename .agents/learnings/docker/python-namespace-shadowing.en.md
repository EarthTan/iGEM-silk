---
name: Python Namespace Shadowing v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [python, namespace, import, package, docker, iGEM-silk]
validated: true
---

> English translation of [python-namespace-shadowing.md](python-namespace-shadowing.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Python Namespace Shadowing

## Experience

**Problem type**: In the Python import system, a microservice's internal `tools/` subdirectory shadows the project-level `tools/` namespace package, causing `ModuleNotFoundError`.

**Core strategy**: Rename the microservice's internal SDK directory to a unique name (such as `anoxpepred_sdk/`) to avoid a conflict with the project-level `tools/`.

**Key parameters**: `sys.path[0]` (CWD), the presence of `__init__.py`

### Symptoms

`from tools.template.fasta_service import ...` works in service A but raises `ModuleNotFoundError` in service B.

### Root Cause

1. Project structure: `/app/tools/` contains `template/` (framework code, no `__init__.py`—a namespace package) and `AnOxPePred/` (microservice code)
2. AnOxPePred has an internal `tools/AnOxPePred/tools/` subdirectory (its bundled SDK) that contains `__init__.py` (a regular package)
3. Docker's `WORKDIR /app/tools/AnOxPePred` adds the CWD to `sys.path[0]`
4. When Python resolves `import tools`, it **finds the local `tools/` first** (the one with `__init__.py`), shadowing the project-level `tools/`

### Fix

```bash
# Rename the internal tools/ to a unique name
mv tools/AnOxPePred/tools tools/AnOxPePred/anoxpepred_sdk
mv tools/SoDoPE_paper_2020/tools tools/SoDoPE_paper_2020/sodope_sdk
```

### Prevention

The top-level `tools/` is the project framework namespace package. Microservices' internal code directories **must not use `tools/`** as a directory name.

## Environment Fingerprint

- **Task domain**: Python multi-package projects
- **Input characteristics**: The project uses a namespace package (no `__init__.py`) plus a regular package with `__init__.py` in a subdirectory
- **Constraints**: WORKDIR is set inside the subdirectory
- **Not applicable**: Standard Python projects where every package has `__init__.py`

## Audit Record

- **Validation method**: Reproduced and fixed in the AnOxPePred and SoDoPE services during iGEM-silk Docker builds
- **Failure case**: `from tools.template.fasta_service import FastaToolService` → `ModuleNotFoundError: No module named 'tools.template'`
- **Fix validation**: After renaming the internal SDK directory, imports work normally

## Usage

- **Trigger conditions**: The Docker build passes but `import tools.xxx` raises ModuleNotFoundError at runtime, while local development works
- **How to invoke**: Check whether a directory with the same name containing `__init__.py` exists under `sys.path[0]`; use `python -c "import tools; print(tools.__path__)"` to confirm which package is actually loaded
- **Caveats**: This is the most insidious Docker build problem—the build passes (COPY succeeds) and only the runtime fails; and it is triggered only under a specific WORKDIR
