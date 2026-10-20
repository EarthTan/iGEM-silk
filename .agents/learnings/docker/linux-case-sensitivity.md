---
name: Linux Filesystem Case Sensitivity v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [linux, macos, case-sensitivity, filesystem, docker, iGEM-silk]
validated: true
---

> **English** | [中文](linux-case-sensitivity.zh.md)

# Gene Capsule: Linux Filesystem Case Sensitivity

## Experience

**Problem type**: APFS is case-insensitive during macOS development, while Linux (ext4/xfs) is strictly case-sensitive, causing path mismatches in cross-platform Docker builds.

**Core strategy**: Use `ls` to confirm the actual directory name character by character; do not assume it is correct just because it "looks the same". `Tipred` vs `TIPred` and `algpred2` vs `AlgPred2` are different paths.

**Key parameters**: The case of directory names must match the actual filesystem exactly

### Three Affected Places

1. The `COPY` statement in the Dockerfile
2. The `dockerfile` path in docker-compose.yml
3. The `WORKDIR` instruction in the Dockerfile

Any inconsistency in any of these causes a build failure, and the error message does not point directly at "a case-sensitivity problem".

## Environment Fingerprint

- **Task domain**: Cross-platform Docker projects
- **Input characteristics**: macOS development + Linux deployment
- **Constraints**: Docker configuration involving file paths
- **Not applicable**: Development entirely on macOS or entirely on Linux

## Audit Record

- **Validation method**: iGEM-silk Docker builds validated in the Ubuntu deployment environment
- **Failure case**: Several services failed `COPY` because of case mismatches in directory names
- **Fix validation**: Corrected uniformly after confirming the actual directory names with `ls tools/`

## Usage

- **Trigger conditions**: The build passes on macOS but COPY reports `file not found` on Linux
- **How to invoke**: List the actual directory names with `ls -1 tools/` and compare them one by one against the references in the Dockerfiles and compose files
- **Caveats**: Not only directory names—file names are the same (e.g. `service.py` vs `Service.py`)
