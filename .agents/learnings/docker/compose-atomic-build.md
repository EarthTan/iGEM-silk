---
name: Docker Compose Build Atomicity Flaw v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, docker-compose, build-strategy, atomicity, iGEM-silk]
validated: true
---

> **English** | [中文](compose-atomic-build.zh.md)

# Gene Capsule: Docker Compose Build Atomicity Flaw

## Experience

**Problem type**: During a batch Docker Compose build, any single service failure rolls everything back—builds that already succeeded are wasted.

**Core strategy**: Build in batches—group by profile or build the failing services individually.

**Key parameters**: `--profile` grouping, `docker compose build <service>`

When `docker compose --profile gpu --profile cpu up -d --build` builds 15 services, any single failure **cancels everything**. The previous 10 may already have been built successfully, but all are wasted because the last one failed.

### Incorrect Pattern

```bash
# ❌ building all 15 services at once, one failure wipes out everything
docker compose --profile gpu --profile cpu up -d --build
```

### Correct Pattern

```bash
# Build in batches
docker compose --profile cpu build    # CPU services first
docker compose --profile gpu build    # then GPU services
docker compose --profile gpu --profile cpu up -d   # finally start everything
```

Or build the failing services individually:

```bash
docker compose build anoxpepred bepipred3 toxinpred3
```

## Environment Fingerprint

- **Task domain**: Multi-service Docker Compose projects
- **Input characteristics**: 5 or more services, including one known to possibly fail to build
- **Constraints**: Using the combined `--build` + `up` command
- **Not applicable**: Projects where all services build reliably

## Audit Record

- **Validation method**: In the iGEM-silk full build, one service failure invalidated the successful build results of the previous 10+ services
- **Failure case**: `docker compose --profile gpu --profile cpu up -d --build` triggered an atomic rollback with 15 services
- **Fix validation**: After splitting into batches, each build is independent and unaffected by the others

## Usage

- **Trigger conditions**: A multi-service project has a service whose build is unstable
- **How to invoke**: First build in batches with `docker compose --profile xxx build`, then `up -d` once everything passes
- **Caveats**: Batching does not change network dependencies between services—during the `up -d` stage the services can still reach each other
