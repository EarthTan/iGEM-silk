> **English** | [中文](Docker.zh.md)

# Docker Operations Guide — iGEM-silk

> This document consolidates every Docker-related lesson from `.agents/learnings/` (23 capsules)
> and serves as the single reference for Docker deployment, operation, and troubleshooting in this project.
>
> **Last updated**: 2026-05-18

---

## 1. Core Principles

### 1.1 All services must run in Docker

Every microservice in production **must** run through Docker Compose. Starting one directly on the host machine with `python service.py` is forbidden.

Rationale:
- Each microservice has its own Python environment and system dependencies; the host machine cannot satisfy all dependency versions at the same time
- Model file paths are hardcoded per environment, so running directly on the host fails because the paths are wrong
- The Docker environment has already been validated at build time; running directly means skipping all of that validation
- Leftover processes on the host machine occupy GPU memory and interfere with subsequent Docker services

The only exception: during **development and debugging** you may run a single service on the host, but it must be re-validated in Docker once debugging is finished.

### 1.2 On-demand startup, shut down when done

**Do not start all 16 microservices at once.** Each pipeline step should start only the services that step actually depends on.

- GPU services compete for GPU memory (48GB in total; a single GPU service may occupy 6-34GB)
- Unnecessary services waste system resources (CPU, memory, network connections)
- The more services there are, the longer the health-check chain and the more complex troubleshooting becomes

Which services each step starts is defined by `main/stages3/service_map.py` and managed uniformly through `ensure_services()` in `docker_utils.py`.

### 1.3 No bare-metal execution

| ❌ Forbidden | ✅ Correct |
|---------|--------|
| `cd tools/AnOxPePred && python service.py` | `docker compose --profile gpu up -d anoxpepred` |
| `cd tools/SASA && python service.py` | `docker compose --profile cpu up -d sasa` |
| Modifying `uvicorn.run(host="0.0.0.0")` to control the exposure scope | Control the exposure scope in `ports:` of `docker-compose.yml` |

**Special note**: `uvicorn.run(host="0.0.0.0")` in all service code is **correct and required**. Communication inside a Docker container requires binding to `0.0.0.0`; the exposure scope is controlled by the Compose port mapping:
- `"8001:8001"` — reachable from the LAN (default)
- `"127.0.0.1:8001:8001"` — reachable only from the local machine
Never modify the host binding in service code.

---

## 2. Service Overview

### 2.1 Microservice inventory

There are 19 microservices in total, split into two profiles:

#### GPU services (`--profile gpu`)

| Service | Port | Group | GPU memory usage | Startup wait | Notes |
|------|------|------|---------|---------|------|
| anoxpepred | 8001 | score | ~10GB | 30s | TensorFlow GPU |
| bepipred3 | 8002 | score | ~6GB | 60s | ESM-2 650M model |
| hemopi2 | 8004 | filter | ~2GB | 60s | |
| mhcflurry | 8005 | score | ~2GB | 120s | Slow model loading |
| plm4cpps | 8006 | score | ~6GB | 60s | ESM-2 + TF |
| graphcpp | 8009 | score | ~4GB | 30s | torch-geometric |
| temstapro | 8010 | score | ~11GB | 120s | HuggingFace model |
| alphafold3 | 8201 | structure | (wrapper) | 15s | Docker socket wrapper |
| esmfold | 8203 | structure | ~17GB | 120s | openfold compilation |
| omegafold | 8204 | structure | ~11GB | 120s | Synchronous inference blocks the event loop |

> **Note**: `alphafold3` is a Docker-in-Docker wrapper. It does not occupy the GPU itself, but it launches the real AF3 image through the Docker socket.

#### CPU services (`--profile cpu`)

| Service | Port | Group | Notes |
|------|------|------|------|
| toxinpred3 | 8003 | filter | sklearn single-threaded, prone to hanging |
| algpred2 | 8008 | filter | |
| sodope | 8012 | score | |
| tipred | 8007 | score | Not yet used in the pipeline |
| sasa | 8101 | pdb_score | |
| aggrescan3d | 8102 | pdb_score | Python 2.7 via micromamba |
| waveflow | 8205 | structure | Tamarind.bio API wrapper |
| pepfold4 | 8202 | structure | Docker socket wrapper |

### 2.2 Actual profile distribution (differences from the planning documents)

Early planning assumed most scoring services were CPU, but the actual `docker-compose.yml` configuration differs:

| Actually GPU | Actually CPU |
|----------|---------|
| anoxpepred, bepipred3, plm4cpps, graphcpp, temstapro, mhcflurry, hemopi2 | toxinpred3, algpred2, sodope, tipred |

This means most pipeline steps need both the `gpu` and `cpu` profiles started at the same time.

### 2.3 Step dependency map

```
step0: []                          — pure local preprocessing
step1: [anoxpepred, algpred2]      — gpu + cpu
step2: [anoxpepred, bepipred3,     — gpu + cpu (9 services)
        plm4cpps, graphcpp,
        temstapro, sodope,
        mhcflurry, toxinpred3,
        hemopi2]
step3: [sodope, temstapro]         — cpu + gpu
step4: [omegafold]                 — gpu only
step5: [sasa, aggrescan3d]         — cpu only
step6: []                          — pure local ranking
```

---

## 3. Docker Compose Usage

### 3.1 Build and start (correct order)

#### Incorrect

```bash
cd tools
docker compose --profile gpu --profile cpu up -d --build
# ↑ 15 services built together; one failure rolls everything back
```

#### Correct

```bash
cd tools

# 1. Build in batches by profile to isolate failures
docker compose --profile cpu build
docker compose --profile gpu build

# 2. Start only after all builds pass
docker compose --profile gpu --profile cpu up -d

# Or start only the services the current step needs
docker compose --profile gpu up -d anoxpepred
docker compose --profile cpu up -d algpred2
```

#### Rebuilding a single service only

```bash
docker compose build anoxpepred
docker compose up -d anoxpepred
```

> **Key point**: `docker compose up -d --build` is atomic — if even one of the 15 services fails to build, the 10 that already built successfully are discarded. Always separate build from start (up).

### 3.2 Common pitfalls

#### Pitfall 1: the dockerfile path is relative to the build context

```yaml
# In docker-compose.yml:
build:
  context: ..          # context = tools/..
  dockerfile: tools/AnOxPePred/Dockerfile   # ✅ Correct
  # dockerfile: Dockerfile                   # ❌ Wrong — it will be looked up in the context root
```

After configuring, verify with `grep 'dockerfile:' docker-compose.yml`.

#### Pitfall 2: COPY misses shared dependencies

The Dockerfiles of almost every service depend on shared files in the project root. A missing COPY does not fail the build, but it throws `ModuleNotFoundError` at runtime.

**Files that must be COPYed**:
```dockerfile
COPY tools/utils.py ./tools/utils.py           # GPU detection utility
COPY tools/template/ ./tools/template/         # FastAPI template
```

**Audit command**:
```bash
for f in tools/*/Dockerfile; do
  if ! grep -q 'COPY.*utils\.py' "$f" 2>/dev/null; then
    echo "MISS utils.py: $f"
  fi
  if ! grep -q 'COPY.*template' "$f" 2>/dev/null; then
    echo "MISS template: $f"
  fi
done
```

#### Pitfall 3: the `latest` tag causes sudden CI failures

```dockerfile
# ❌ Do not use latest
FROM ghcr.io/astral-sh/uv:latest

# ✅ Pin the version
FROM ghcr.io/astral-sh/uv:0.4.30
```

`latest` pulls different versions at different times. After upstream publishes a new version, your build suddenly fails without any code change.

#### Pitfall 4: Linux file name case sensitivity

The macOS file system (APFS) is case-insensitive by default; Linux (ext4/xfs) is case-sensitive.
- On macOS, `Tipred` and `TIPred` point to the same directory
- On Linux they point to different directories

```bash
# Use this command to confirm the real directory name; do not eyeball it
ls -1 tools/
```

Affected areas: Dockerfile `COPY`, docker-compose `dockerfile` paths, and `WORKDIR` inside Dockerfiles.

#### Pitfall 5: Python namespace shadowing (the most insidious error)

`tools/` in the project root is a namespace package (no `__init__.py`).
If a microservice contains a same-named subdirectory `tools/` (with an `__init__.py`),
Python finds the local package first, causing `from tools.template.fasta_service import ...` to throw `ModuleNotFoundError`.

**Diagnosis**:
```bash
python -c "import tools; print(tools.__path__)"
```

**Fix**: an internal code directory of a microservice must never be named `tools/`. For example `mv tools/AnOxPePred/tools tools/AnOxPePred/anoxpepred_sdk`.

#### Pitfall 6: slim images lack C extension build dependencies

```dockerfile
# ❌ This fails — the slim image has no Python.h
FROM python:3.11-slim
RUN pip install freesasa

# ✅ Install the build dependencies first
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev pkg-config libxml2-dev \
    && rm -rf /var/lib/apt/lists/*
```

### 3.3 Base image selection

The Dockerfiles in this project use 7 base image patterns:

| Pattern | Base image | Applicable scenario | Service examples |
|------|---------|---------|---------|
| **A** | `pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime` | GPU PyTorch | BepiPred3, HemoPI2, MHCflurry, pLM4CPPs, TemStaPro, GraphCPP |
| **B** | `nvidia/cuda:12.1.0-*-ubuntu22.04` | Raw CUDA + custom Python | ESMFold (devel), OmegaFold (runtime) |
| **C** | `python:3.11-slim` | CPU services | ToxinPred3, SASA, AlgPred2, Tipred |
| **D** | `tensorflow/tensorflow:2.21.0-gpu` | TensorFlow GPU | AnOxPePred |
| **E** | `python:3.13-slim` | Newest Python | SoDoPE |
| **F** | `ghcr.io/mamba-org/micromamba:latest` | Conda environment / Python 2.7 | Aggrescan3D |
| **G** | `python:3.11-slim` + Docker socket | Docker-in-Docker wrapper | AlphaFold3, PEP-FOLD4, Waveflow |

**CUDA version matrix**:
- CUDA 12.4 + cuDNN 9: PyTorch base image (Pattern A)
- CUDA 12.1: structure prediction (Pattern B)
- Torch index: `https://download.pytorch.org/whl/cu121`

### 3.4 GPU service management

#### Health checks are not synchronized

A passing health check for a GPU service does not mean prediction will succeed. The model may only start loading onto the GPU after the container starts, so the health-check timeout (`start_period`) must be long enough.

Health-check pattern in `docker-compose.yml`:
```yaml
healthcheck:
  test: curl -f http://localhost:PORT/health || exit 1
  interval: 30s
  timeout: 10s       # lightweight services
  timeout: 30s       # heavy GPU services
  timeout: 60s       # structure prediction
  retries: 3         # lightweight services
  retries: 5         # heavy GPU services
  start_period: 60s  # GPU services (model loading time)
```

#### Direct bridge IP connection (bypassing docker-proxy)

Accessing containers via `127.0.0.1:PORT` (docker-proxy) intermittently hangs on long-running requests — the container processes the request normally, but the client never receives the response.

**Diagnosis method**:
```bash
# curl on the host machine may hang
curl http://127.0.0.1:8002/health

# But curl inside the container works
docker exec bepipred3 curl http://localhost:8002/health

# Direct bridge IP connection works
curl http://172.18.0.X:8002/health
```

**Fix**: obtain the bridge IP and connect directly:
```python
import subprocess, json
result = subprocess.run(
    ["docker", "inspect", "omegafold", "--format", '{{json .NetworkSettings.Networks}}'],
    capture_output=True, text=True
)
networks = json.loads(result.stdout)
bridge_ip = networks.get("bridge", {}).get("IPAddress")
# Set the environment variable: export OMEGAFOLD_HOST=<bridge_ip>
```

`detect_bridge_ip()` in `docker_utils.py` does this automatically.

#### GPU memory check

Confirm there is enough GPU memory before starting a GPU service:
```bash
nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits
```

GPU memory requirements per GPU service (rough):
- AnOxPePred: ~10GB (leaves a ~34GB CUDA context behind after exiting!)
- BepiPred3: ~6GB
- TemStaPro: ~11GB
- OmegaFold: ~11GB
- ESMFold: ~17GB
- pLM4CPPs: ~6GB
- Total available: 48GB

**GPU service concurrency principles**:
- Run only one GPU-intensive service at a time
- Semaphore > 1 never helps serial GPU inference — it only increases the probability of timeouts
- Use CPU prescreening (TemStaPro) to reduce GPU load: take the Top 30% and feed only those to the GPU

---

## 4. Service Lifecycle Management

### 4.1 Pre-start checklist

Before each pipeline step, confirm:

```
□ Is the Docker daemon running?  → docker info
□ Is there enough GPU memory for the required GPU services? → nvidia-smi
□ Are there port conflicts for the required CPU services? → ss -tnp | grep <PORT>
□ Does the Docker Compose file exist? → ls tools/docker-compose.yml
□ Have the GPU processes from the previous step been cleaned up? → ps aux | grep python
```

### 4.2 On-demand startup protocol

Use the unified entry point `ensure_services()` from `docker_utils.py`:

```python
from main.stages3.docker_utils import ensure_services
from main.stages3.service_map import get_step_services

# 1. Query which services the current step needs
info = get_step_services("step1")

# 2. Start them and wait until ready
health = ensure_services(
    info["services"],
    profiles=info["profiles"],
    timeout=120.0,
)

# 3. Check for unavailable services
unavailable = [s for s, h in health.items() if not h["available"]]
if unavailable:
    sys.exit(f"Services unavailable: {unavailable}")
```

**API quick reference**:

| Function | Purpose | Idempotent |
|------|------|------|
| `ensure_services(names, profiles, timeout, skip_docker)` | Main entry: start → health check → cache | ✅ 120s cache |
| `check_docker_daemon()` | Check whether Docker is running | ❌ |
| `detect_bridge_ip(container)` | Obtain the container bridge IP | ✅ cached |
| `clear_cache()` | Clear the cache when switching steps | — |
| `wait_for_services(services, timeout, poll_interval)` | Poll until /health responds | ❌ |

**Idempotency mechanism**: repeated `ensure_services` calls for the same service return the cached result directly; they do not start the service or run health checks again. Caches:
- `_health_cache`: service health status (valid within a step)
- `_bridge_cache`: container bridge IP (valid within the process)
- `_started_profiles`: profiles that have already been started (avoids repeated `docker compose up`)

**Clearing the cache when switching steps**:
```python
from main.stages3.docker_utils import clear_cache
clear_cache()  # Call this before switching to a new step
```

### 4.3 Runtime monitoring

```bash
# View service logs
docker compose logs -f anoxpepred

# View the status of all services
docker compose ps

# View GPU usage
watch -n 2 nvidia-smi

# View container resource usage
docker stats --no-stream
```

**Timeout strategy** (by service type):

| Service type | Timeout | Notes |
|---------|------|------|
| Lightweight scoring (anoxpepred, algpred2, etc.) | 30s | Most requests take < 5s |
| BepiPred3 | 600s | GPU serial, ~115s per batch (50 sequences) |
| OmegaFold | 14400s (4h) | 90-120s per structure, synchronous blocking |
| ESMFold | 600s | ~120s per structure |
| ToxinPred3 | 120s | socket timeout; asyncio cannot interrupt it |

### 4.4 Shutdown and cleanup

#### 4.4.1 Normal shutdown

```bash
# Stop the services used by the current step
docker compose stop anoxpepred algpred2

# Stop all services
docker compose down

# Stop and remove volumes (be careful — this deletes model caches)
docker compose down -v
```

#### 4.4.2 Releasing GPU memory (==Pitfall #4==)

**`docker stop` cannot release GPU memory.** If the GPU process belongs to the host machine's PID namespace, the CUDA context still occupies GPU memory after the container stops.

AnOxPePred is especially severe — even after the process exits, the PyTorch caching allocator retains every CUDA memory block it ever allocated (up to ~34GB).

**Correct GPU memory release procedure**:
```bash
# 1. Find the leftover Python process
ps aux | grep anoxpepred

# 2. Force kill it
kill -9 <PID>

# 3. Confirm the memory has been released
nvidia-smi
```

**Preventive measures**:
- Set `init: true` in `docker-compose.yml` (tini init process, prevents zombie processes)
- `stop_grace_period: 5s` (fast termination)
- Run `nvidia-smi` to confirm GPU memory before starting a new GPU service
- **Always check for leftover GPU processes between steps**

#### 4.4.3 Standard step-switching procedure

```
1. Stop the services of the current step: docker compose stop <services>
2. Check GPU memory: nvidia-smi (if leftovers remain → kill -9)
3. Clear the docker_utils cache: clear_cache()
4. Start the services of the new step: ensure_services(...)
5. Confirm the new services are healthy
```

---

## 5. Troubleshooting Guide

### 5.1 Docker build failure

**Symptom**: `docker compose build` fails, or the build passes but startup fails.

**Troubleshooting steps**:
1. View the build log: `docker compose build <service> 2>&1 | tail -50`
2. Distinguish build-stage errors from runtime-stage errors
3. Check whether the base image can be pulled (may be unreachable on Chinese networks)
4. Check whether COPY paths are correct (case, relative paths)
5. Batch-audit all Dockerfiles for common problems:

```bash
# Audit script — collect all problems at once
echo "=== dockerfile paths ==="
grep 'dockerfile:' docker-compose.yml

echo "=== COPY omissions ==="
for f in tools/*/Dockerfile; do
  if ! grep -q 'COPY.*utils\.py' "$f"; then echo "MISS utils.py: $f"; fi
  if ! grep -q 'COPY.*template' "$f"; then echo "MISS template: $f"; fi
done

echo "=== Base images ==="
grep '^FROM' tools/*/Dockerfile

echo "=== WORKDIR ==="
grep 'WORKDIR' tools/*/Dockerfile

echo "=== Case sensitivity issues ==="
ls -1 tools/
```

### 5.2 Docker Hub unreachable (Chinese network)

**Symptom**: `docker pull` times out, and `docker compose build` hangs on the `FROM` line.

**Solution A — configure a registry mirror**:
```json
// /etc/docker/daemon.json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```
```bash
sudo systemctl restart docker
```

**Note**: the Daocloud mirror has a whitelist; images not on the whitelist (such as `ghcr.io/mamba-org/micromamba`) are rejected. In that case, pull directly from the original source (such as GHCR).

**Solution B — switch to native execution**:
When Docker builds keep failing, you can fall back to a native conda/pip environment on the host machine:
```bash
# For example, the Aggrescan3D fallback
conda install -c lcbio aggrescan3d
export AGGRESCAN_CONDA_ENV=aggrescan3d
```
The switch is driven by environment variables without modifying code. But **native execution is only a temporary fallback**; the Docker setup still needs to be fixed.

### 5.3 Container healthy but requests hang (docker-proxy bug)

**Symptom**: the service health check passes, but long-running prediction requests intermittently hang — the client never receives a response, although the server has actually finished.

**Three-step diagnosis**:
```bash
# 1. curl on the host machine — may hang
timeout 10 curl http://127.0.0.1:8002/predict -X POST ...

# 2. curl inside the container — works
docker exec bepipred3 curl http://localhost:8002/predict -X POST ...

# 3. curl to the bridge IP — works (confirms it is a docker-proxy problem)
BRIDGE_IP=$(docker inspect bepipred3 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
curl http://${BRIDGE_IP}:8002/predict -X POST ...
```

**Root cause**: docker-proxy (the user-space TCP proxy of dockerd) has bugs when handling keep-alive connections — connection-pool state desynchronization, uncleared TCP connections after restarts, and epoll race conditions under high concurrency.

**Fix**: connect directly to the bridge IP, injected through the `{SERVICE}_HOST` environment variable.
`docker_utils.detect_bridge_ip()` can obtain the bridge IP automatically.

**Scope**: only affected when the host machine accesses containers. Communication between services inside Docker Compose uses DNS resolution and is not affected.

### 5.4 Insufficient GPU memory

**Symptom**: the service health check passes but prediction fails, or the model hangs silently halfway through loading (no OOM error, no logs).

**Troubleshooting**:
```bash
nvidia-smi
# Check: used GPU memory vs total GPU memory (48GB)
# Check: whether leftover python processes are occupying GPU memory
```

**On-demand startup strategy** (avoid starting several GPU services at once):

```
Scenario: Step 1 needs anoxpepred + algpred2
  → Start anoxpepred first (GPU, ~10GB)
  → 38GB of GPU memory remains, which is enough
  → Then start algpred2 (CPU, no GPU memory)

Scenario: Step 4 needs omegafold (~11GB)
  → Make sure the GPU services of previous steps are stopped and their memory released
  → Confirm that free GPU memory in nvidia-smi is > 20GB
  → Start omegafold
```

**JAX CUDA initialization timing** (a trap): JAX initializes CUDA when the container starts, not when the model loads. This means GPU memory may already be insufficient when the health check passes, without any error. Failure only appears at prediction time as `RuntimeError: No supported devices found` or `OutOfMemoryError`.

### 5.5 Service hangs

#### ToxinPred3 (sklearn single-threaded hang)

**Symptom**: the ToxinPred3 process sits at 100% CPU and the port does not respond. An `asyncio.wait_for` timeout cannot interrupt it (C extensions are not controlled by Python signals).

**Final solution** (after several iterations):
- Use synchronous `requests` instead of `httpx` (socket timeouts are handled by the kernel and can be interrupted)
- Batch size: 200 (reduced from 1000)
- Timeout: 120s
- Call the `/restart` endpoint after 5 consecutive batch timeouts
- Fully serialized (single connection, single request)

See `main/stages2/round02_toxinpred3_sync.py`.

#### OmegaFold (synchronous inference blocks the event loop)

**Symptom**: OmegaFold's `self.model(input_data)` is a synchronous PyTorch CUDA call (90-120s); calling it directly inside an `async def` blocks the uvicorn event loop. During that time `/health`, `/status/{job_id}`, and `/result/{job_id}` all hang.

**Client-side fix**: `asyncio.Semaphore(1)` to serialize requests.
**Recommended server-side fix** (not yet implemented): move inference into `run_in_executor(ThreadPoolExecutor(max_workers=1), ...)`.

### 5.6 Python namespace shadowing

**Symptom**: `ModuleNotFoundError: No module named 'tools.template'`, even though `tools/template/` really exists and has been COPYed.

**Diagnosis**:
```bash
# Run inside the container
docker exec -it <container> python -c "import tools; print(tools.__path__)"
# Output similar to: ['/app/tools/AnOxPePred/tools'] ← wrong path!
# It should be: ['/app/tools']
```

**Fix**: an internal code directory of a microservice must never be named `tools/`.

### 5.7 Build failures caused by Linux case sensitivity

**Symptom**: the build passes on macOS but fails on a Linux server. The error message is `COPY failed: file not found`.

**Troubleshooting**:
```bash
# Run on both macOS and Linux
ls -1 tools/<suspicious-directory>

# Check whether the paths referenced in docker-compose.yml match the real directory names
grep 'dockerfile:' docker-compose.yml
ls -1 tools/
```

### 5.8 Docker-outside-Docker path problem

**Symptom**: services that launch child containers through the Docker socket (AlphaFold3, PEP-FOLD4) cannot find mounted volumes — the paths inside the container do not exist on the host machine.

**Root cause**: the source path of `docker run --volume` is resolved by the **host machine's Docker daemon**, not by the API container.

**Fix**: use dual paths — the host machine path (for the docker socket) and the container path (for health checks):
```yaml
# docker-compose.yml
environment:
  AF3_MODEL_DIR: /root/models           # Container path (for health checks)
  AF3_MODEL_HOST_DIR: /home/lenovo/af_models  # Host path (for docker.sock)
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - /usr/bin/docker:/usr/bin/docker      # Mount the docker CLI instead of installing it in the container
```

---

## 6. Command Quick Reference

### Build

| Command | Description |
|------|------|
| `cd tools` | All Docker operations run under tools/ |
| `docker compose --profile cpu build` | Build all CPU services |
| `docker compose --profile gpu build` | Build all GPU services |
| `docker compose build anoxpepred` | Build a single service |
| `docker compose --no-ansi build 2>&1 \| tail -50` | View the last 50 lines of the build log |

### Start/stop

| Command | Description |
|------|------|
| `docker compose --profile gpu up -d` | Start all GPU services |
| `docker compose --profile cpu up -d` | Start all CPU services |
| `docker compose up -d anoxpepred algpred2` | Start the specified services |
| `docker compose stop anoxpepred` | Stop the specified service |
| `docker compose down` | Stop and remove all containers |
| `docker compose restart anoxpepred` | Restart a service |

### Monitoring

| Command | Description |
|------|------|
| `docker compose ps` | View service status |
| `docker compose logs -f anoxpepred` | View live logs |
| `nvidia-smi` | View GPU memory |
| `watch -n 2 nvidia-smi` | Monitor the GPU in real time |
| `docker stats --no-stream` | View container resource usage |
| `ss -tnp \| grep <PORT>` | View port usage |

### In-container debugging

| Command | Description |
|------|------|
| `docker exec -it anoxpepred bash` | Enter the container shell |
| `docker exec anoxpepred curl localhost:8001/health` | Health check inside the container |
| `docker inspect anoxpepred --format '{{json .NetworkSettings.Networks}}'` | View the network configuration |

### Troubleshooting

| Command | Description |
|------|------|
| `docker inspect anoxpepred \| jq '.[0].State'` | View detailed container state |
| `docker logs anoxpepred --tail 100` | View the last 100 log lines |
| `ps aux \| grep python` | Find leftover Python processes |
| `kill -9 <PID>` | Force-release GPU memory |
| `docker system df` | View disk usage |
| `docker builder prune` | Clean the build cache |

---

## Appendix: Gene Capsule Index

The content of this document comes from the following gene capsules in `.agents/learnings/`; see the originals for the full context:

| Topic | Capsule file |
|------|---------|
| Docker Compose atomic rollback | `docker/compose-atomic-build.md` |
| Batch failure audit | `docker/batch-failure-audit.md` |
| Dockerfile COPY omissions | `docker/dockerfile-copy-audit.md` |
| dockerfile path relative to context | `docker/dockerfile-path-compose.md` |
| latest tag version uncertainty | `docker/latest-tag-pinning.md` |
| Linux case sensitivity | `docker/linux-case-sensitivity.md` |
| Python namespace shadowing | `docker/python-namespace-shadowing.md` |
| slim missing C build dependencies | `docker/slim-image-build-deps.md` |
| Docker Hub China mirror | `docker/docker-hub-china-mirror.md` |
| Docker-outside-Docker paths | `docker/docker-outside-docker-paths.md` |
| Docker CLI installation inside containers | `docker/docker-cli-in-container.md` |
| Direct bridge IP connection | `gep-docker-container-bridge-ip.md` |
| Native fallback when Docker is unreachable | `gep-docker-native-hybrid.md` |
| PyTorch CUDA cache leftovers | `gep-pytorch-cuda-cache-gpu-memory-leak.md` |
| GPU memory contention | `gpu-memory-contention.md` |
| BepiPred3 GPU timeout tuning | `gep-bepipred3-gpu-timeout-tuning.md` |
| OmegaFold synchronous inference blocking | `gep-omegafold-sync-inference-blocking.md` |
| ToxinPred3 single-threaded hang | `gep-toxinpred3-concurrency-limit.md` |
| TemStaPro prescreening reduces the GPU bottleneck | `gep-temstapro-prescreen-gpu-bottleneck.md` |
| Structure prediction confidence cascade | `gep-pipeline-confidence-cascade.md` |
| Pipeline stage orchestration and checkpoints | `gep-pipeline-stage-orchestration.md` |
| Microservice network binding strategy | `microservice-host-binding.md` |
| Structure prediction Docker patterns | `structure-service-pattern.md` |
