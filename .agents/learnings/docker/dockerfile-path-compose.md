---
name: docker-compose dockerfile Path Consistency v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, docker-compose, build-context, path-resolution, iGEM-silk]
validated: true
---

> **English** | [中文](dockerfile-path-compose.zh.md)

# Gene Capsule: docker-compose dockerfile Path Consistency

## Experience

**Problem type**: In Docker Compose, the `dockerfile` path is relative to `context` rather than to the compose file's location, so the Dockerfile is not found.

**Core strategy**: The `dockerfile` path is relative to `context`. When `context: ..` while the Dockerfile lives under `tools/<name>/`, you must write `dockerfile: tools/<name>/Dockerfile`.

**Key parameters**: The relative relationship between `context` and `dockerfile`

### Incorrect Pattern

```yaml
# tools/docker-compose.yml
services:
  anoxpepred:
    build:
      context: ..
      dockerfile: Dockerfile    # ❌ relative to context (project root), but it is actually at tools/AnOxPePred/Dockerfile
```

### Correct Pattern

```yaml
services:
  anoxpepred:
    build:
      context: ..
      dockerfile: tools/AnOxPePred/Dockerfile
```

### Batch Validation

```bash
grep 'dockerfile:' docker-compose.yml
# compare one by one with ls tools/*/Dockerfile
```

## Environment Fingerprint

- **Task domain**: Docker multi-service project builds
- **Input characteristics**: `context` and `dockerfile` in docker-compose.yml are not in the same directory
- **Constraints**: Most error-prone during first configuration or when adding a service
- **Not applicable**: Simple cases where `context` and `dockerfile` are in the same directory

## Audit Record

- **Validation method**: Validated with a full docker compose build of 15 iGEM-silk services
- **Failure case**: Several services had dockerfile paths pointing to the project root instead of the `tools/<name>/` subdirectory, so `docker compose build` could not find the Dockerfile
- **Fix validation**: After a full `grep` + `ls` comparison and the fixes, the rebuild passed

## Usage

- **Trigger conditions**: Adding a microservice, or modifying the build configuration in docker-compose.yml
- **How to invoke**: Immediately after the first configuration, use a script to compare all dockerfile paths
- **Caveats**: Do not fix them one by one from memory—a single full grep scan is far more efficient than waiting for CI to report each error
