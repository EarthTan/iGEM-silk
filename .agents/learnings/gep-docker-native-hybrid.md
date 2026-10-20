---
name: Fallback to Host-Native Execution When Docker Is Unreachable v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [docker, hybrid, china-network, conda, native, fallback]
validated: true
---

> **English** | [中文](gep-docker-native-hybrid.zh.md)

# Gene Capsule: Fallback to Host-Native Execution When Docker Is Unreachable

## Experience

**Problem type**: In mainland China network environments Docker Hub is unreachable, so some microservices (Aggrescan3D) cannot have their Docker images built and must switch to a host-native conda environment for direct invocation.

**Core strategy**:
1. **First check whether a local alternative runtime exists**: Aggrescan3D provides a conda package (`conda install -c lcbio aggrescan3d`) that can be installed and run directly on the host
2. **Environment-variable-driven switching**: `AGGRESCAN_CONDA_ENV` controls the conda env path, so you can switch from Docker to native without changing code
3. **Native execution is often faster**: Aggrescan3D in a native conda environment takes ~4s/PDB, while Docker-in-Docker mode (mounting docker.sock to start a temporary container) is slower due to nested overhead
4. **The microservice wrapper stays the same**: even with native invocation, the same interface is exposed through the FastAPI microservice, so callers are completely unaware of the difference underneath

**Key parameters**:

| Deployment mode | Pros | Cons |
|----------|------|------|
| Docker-in-Docker | Fully isolated environment, reproducible | Image pulls depend on the network; nested Docker has a performance cost |
| Host conda native | No network dependency; fast | The environment is coupled to the host; dependencies must be pre-installed |

**Environment variable interface**:
```
AGGRESCAN_CONDA_ENV=/path/to/conda/env    # conda environment path
A3D_KEEP_WORKSPACE=1                       # keep temporary files for debugging
A3D_WORKSPACE=/tmp/a3d_workspace           # working directory
A3D_TIMEOUT=900                            # timeout in seconds
```

## Environment Fingerprint

- **Task domain**: Deploying Docker microservices to mainland China servers, network-restricted environments
- **Input characteristics**: Dockerfiles using `FROM continuumio/miniconda2`, or similar services that pull base images from Docker Hub
- **Constraints**: `registry-1.docker.io` unreachable; no VPN/proxy; base image > 100MB (cannot be bypassed by transferring small files)
- **Not applicable**:
  - Native invocation that needs a GPU (the conda environment may have CUDA version conflicts)
  - Services with complex system dependencies (apt packages, system libraries)
  - Production deployments that need full environment isolation

## Audit Record

- **Validation method**: Validated on the iGEM-silk Aggrescan3D service
- **Test cases**:
  1. Docker build → `docker pull continuumio/miniconda2` timed out → build failed
  2. Host conda install → `conda install -c lcbio aggrescan3d` → succeeded (Python 2.7 environment)
  3. Native run of `main/stages/stage06_pdb_eval.py` → all 90 PDBs succeeded, ~360s total (~4s/PDB)
  4. Switching environments via `AGGRESCAN_CONDA_ENV` → no code changes needed
- **Success rate**: 100% (90/90 PDB scoring succeeded)
- **Limitations**: The conda-installed Aggrescan3D depends on Python 2.7, which may cause environment conflicts with other services; some tools have only a Docker version and no conda version

## Usage

- **Trigger conditions**: `docker compose build` or `docker pull` fails due to network problems, or Docker-in-Docker performance does not meet requirements
- **How to invoke**:
  1. Check whether the tool has a native installation method such as conda/pip/npm
  2. Confirm dependency compatibility of the native environment (Python version, CUDA version, system libraries)
  3. Add environment variables in service.py to control the run mode (conda env path / binary path)
  4. Parameterize all paths so switching needs no code changes
  5. The microservice interface stays unchanged and callers notice nothing
- **Caveats**: Hybrid mode requires a pre-installed environment on the host and is not suitable for automated CI/CD; the conda environment's Python version may differ from the project's main environment, so isolate it with `conda create -n <env> python=2.7`
