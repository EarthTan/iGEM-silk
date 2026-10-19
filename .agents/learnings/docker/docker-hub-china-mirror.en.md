---
name: Docker Hub Unreachable in China v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, china, network, registry-mirror, iGEM-silk]
validated: true
---

> English translation of [docker-hub-china-mirror.md](docker-hub-china-mirror.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Docker Hub Unreachable in China

## Experience

**Problem type**: Network unreachability causes Docker image pulls to fail—`registry-1.docker.io` is unreachable from most networks in mainland China.

**Core strategy**: Configure a Docker Hub registry mirror.

**Key parameters**: The `registry-mirrors` configuration

`registry-1.docker.io` is unreachable from most networks in mainland China. `docker pull` and `docker compose build` (pulling base images) both time out.

### Configuration

```json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```

Write it to `/etc/docker/daemon.json` and restart Docker:

```bash
sudo systemctl restart docker
```

### Note

Modifying daemon.json requires sudo privileges; tell the user to prepare for this before deployment.

## Environment Fingerprint

- **Task domain**: Docker image pulls
- **Input characteristics**: Located on a mainland China network
- **Constraints**: sudo privileges are required to modify daemon.json
- **Not applicable**: Overseas networks, or environments with another proxy/VPN already configured

## Audit Record

- **Validation method**: Full build of 15 iGEM-silk services; the DaoCloud registry mirror works
- **Failure case**: Without the registry mirror configured, every `docker compose build` timed out because `registry-1.docker.io` was unreachable
- **Fix validation**: After configuring it, `docker pull python:3.11-slim` succeeded

## Usage

- **Trigger conditions**: `docker pull` or `docker compose build` reports `dial tcp: connect: connection timed out` to `registry-1.docker.io`
- **How to invoke**: Write to daemon.json → restart Docker → retry the pull
- **Caveats**: The registry mirror may lag; the newest tags may not be synced
