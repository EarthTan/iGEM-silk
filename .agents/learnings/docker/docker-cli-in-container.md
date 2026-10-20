---
name: Installing the Docker CLI Inside a Container v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, docker-socket, dind, docker-cli, iGEM-silk]
validated: true
---

> **English** | [中文](docker-cli-in-container.zh.md)

# Gene Capsule: Installing the Docker CLI Inside a Container

## Experience

**Problem type**: A container needs the `docker` CLI to call the host Docker daemon.

**Core strategy**: Prefer mounting the host's `/usr/bin/docker`, and avoid installing any Docker package inside the container.

**Key parameters**: docker.sock mount + docker binary mount

PEP-FOLD4, AlphaFold3, and Aggrescan3D need to run the `docker` command inside the container to access the host Docker daemon.

### Option 1 (not recommended): install inside the container

```dockerfile
# ❌ increases image size, and the in-container docker version may not match the host
RUN apt-get update && apt-get install -y docker.io
```

### Option 2 (recommended): mount the host binary

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - /usr/bin/docker:/usr/bin/docker
```

Avoid installing any Docker package inside the container—this reduces image size and eliminates the network dependency.

## Environment Fingerprint

- **Task domain**: Docker-outside-of-Docker architecture
- **Input characteristics**: The service needs to run commands such as `docker run`
- **Constraints**: Docker is already installed on the host
- **Not applicable**: Ordinary services that do not need to call the host Docker

## Audit Record

- **Validation method**: Validated on the three iGEM-silk services PEP-FOLD4 / AlphaFold3 / Aggrescan3D
- **Failure case**: The `docker.io` package installed from the Debian repository was incompatible with the host Docker version
- **Fix validation**: After switching to mounting the host's `/usr/bin/docker`, commands execute normally

## Usage

- **Trigger conditions**: The service needs to call the host Docker daemon
- **How to invoke**: Mount both `docker.sock` and `/usr/bin/docker` in docker-compose.yml
- **Caveats**: The container automatically stays in sync when the host Docker version is updated (because it is a mount)
