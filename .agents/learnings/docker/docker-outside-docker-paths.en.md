---
name: Docker-outside-Docker Path Resolution v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, docker-socket, volume-mount, path-resolution, iGEM-silk]
validated: true
---

> English translation of [docker-outside-docker-paths.md](docker-outside-docker-paths.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Docker-outside-Docker Path Resolution

## Experience

**Problem type**: Path resolution errors when calling a nested Docker socket—the source path of `docker run --volume` is resolved by the host Docker daemon, not by a path inside the API container.

**Core strategy**: Separate the "container path" (used by health checks) from the "host path" (used by Docker socket `--volume`), and pass them through independent environment variables.

**Key parameters**: `AF3_MODEL_DIR` (in-container), `AF3_MODEL_HOST_DIR` (absolute host path)

When the API container uses the mounted `/var/run/docker.sock` to call the host Docker daemon and run other containers, the source path of `docker run --volume` is resolved by the **host Docker daemon**, not by a path inside the API container.

### Incorrect Pattern

```yaml
# docker-compose.yml
environment:
  - AF3_MODEL_DIR=/root/models           # ❌ passed to service.py as the --volume source path
volumes:
  - /home/lenovo/af_models:/root/models
```

```python
# service.py
cmd = ["docker", "run", "--volume", f"{self._model_dir}:/root/models", ...]
# self._model_dir = "/root/models" → this path does not exist on the host
```

### Correct Pattern

```yaml
environment:
  - AF3_MODEL_DIR=/root/models                    # container path (for health checks)
  - AF3_MODEL_HOST_DIR=${AF3_MODEL_DIR}            # host path (for Docker socket)
volumes:
  - ${AF3_MODEL_DIR:-/tmp/af3_models}:/root/models
```

```python
self._model_host_dir = os.environ.get("AF3_MODEL_HOST_DIR", self._model_dir)
cmd = ["docker", "run", "--volume", f"{self._model_host_dir}:/root/models", ...]
```

## Environment Fingerprint

- **Task domain**: Docker containerized deployment
- **Input characteristics**: Services that use a `docker.sock` mount + `docker run --volume`
- **Constraints**: Docker-outside-of-Docker architecture
- **Applicable scenarios**:
  - `tools/AlphaFold3/` — mounts the model parameter and database directory
  - `tools/PEP-FOLD4/` — mounts the workspace directory
  - `tools/Aggrescan3D/` — mounts the workspace directory
- **Not applicable**: Services that operate purely on in-container paths and do not involve docker.sock

## Audit Record

- **Validation method**: The AlphaFold3 service in the Ubuntu deployment environment was validated with a health check plus an actual prediction task
- **Known limitation**: The `/health` endpoint only verifies that the in-container path exists (the docker-compose volume mount creates a mount point), but **does not verify that the Docker socket path resolves on the host**. A passing health check does not mean prediction will work
- **Diagnostic chain**: the real host path → docker-compose volumes mapping → environment variable passing → use in service.py → existence of the host path

## Usage

- **Trigger conditions**: The service runs child containers through docker.sock and needs volume mounts
- **How to invoke**: Set both the container path and the host path environment variables in docker-compose.yml
- **Caveats**: Do not assume the container path and the host path are the same; a passing health check does not mean the path is correct
