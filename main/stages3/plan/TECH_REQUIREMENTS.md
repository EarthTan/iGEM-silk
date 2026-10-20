> **English** | [中文](TECH_REQUIREMENTS.zh.md)

# Stages3 Mandatory Technical Specification

> Version: v1.0 — 2026-05-15
> Basis: every technical problem exposed during stages2 execution
> Mandatory: all rules in this document are mandatory requirements; pipeline code review checks them one by one

---

## 1. Mandatory Docker Usage Rules

### Background

During stages2 execution there were repeated cases of "running a microservice directly on the host machine when Docker should have been used". Every time it ran on the host machine it caused:
- Re-installing the Python environment and dependencies (uv sync + resolving version conflicts)
- Inconsistent model file paths (container path vs host path)
- Contamination of the conda environment and the system Python
- Wasting a lot of time on environment issues while debugging

### Mandatory rules

**Rule 1**: In production runs, all microservices must be started through Docker Compose; running `python service.py` directly on the host machine is not allowed.

**Rule 2**: During development you may debug a single microservice on the host machine, but once debugging is finished it must be re-validated with Docker once.

**Rule 3**: Every time you start a new round (or resume from a checkpoint), first run:
```bash
cd tools && docker compose --profile gpu --profile cpu up -d
```
After confirming that every service passes its health check, start the pipeline script.

**Rule 4**: The Dockerfile of every microservice must be built on the templates in `tools/template/`; do not write a Dockerfile from scratch.

### Enforcement mechanism (at the pipeline code level)

Add a Docker health check at the entry point of the pipeline script:

- Before starting any stage, call the health check on all dependent microservices
- If any service is unreachable, check whether it is running inside Docker (by checking /proc/1/cgroup or environment variables)
- If the service is not running inside Docker, print a warning and exit instead of automatically falling back to host mode

### Model cache management

The bind-mount path that shares the model cache in Docker deployments is already defined in docker-compose.yml:

```yaml
volumes:
  - ../models:/root/models  # shared model cache
```

Host model files are kept uniformly under `tools/models/` and mounted automatically inside Docker containers. Do not download models again inside the container.

---

## 2. Technical Problems That Must Be Fixed at the Microservice Layer

The following problems were found in stages2 but only worked around on the client side; they were not fixed on the service side. In stages3 they must be fixed thoroughly at the microservice layer.

### Problem 1: OmegaFold synchronous inference blocks the event loop

**Symptom**: OmegaFold's `predict_structure()` calls `self.model(input_data)` directly inside an `async def` — a PyTorch CUDA synchronous inference that takes 90-120 seconds. This blocks uvicorn's event loop, so while the service is handling one request it cannot respond to any other request at all (health check, status query, and everything else hang).

**Current status**: The client serializes with Semaphore(1), which gets around the concurrent-request problem. But the service's event loop is still blocked.

**Fix requirement**: Move the inference call into `run_in_executor(ThreadPoolExecutor)` to free the event loop:

```
In service.py:
  1. Create a ThreadPoolExecutor(max_workers=1), because GPU inference still needs serialization
  2. In predict_structure(): await loop.run_in_executor(executor, lambda: self.model(...))
  3. Other routes (/health, /status/{job_id}) remain responsive during inference
```

**Impact**: Even though the concurrency limit is 1 today, after the fix the service is prepared for future multi-request scenarios and for better health check availability.

### Problem 2: Docker bridge IP direct connection (network-layer stability)

**Symptom**: When accessing container services through `127.0.0.1:PORT` (docker-proxy), httpx's keep-alive long connections hang intermittently. Especially after a container restart, docker-proxy does not clean up the old TCP connections. At the same moment, `docker exec` + curl inside the container works perfectly.

**Current status**: The client obtains the bridge IP with `docker inspect` and connects directly to the container network, bypassing docker-proxy.

**Fix requirement**: Implement automatic bridge IP resolution in the client library `main/client.py`:

```
1. When ServiceClient is initialized, provide an optional auto_bridge mode
2. If enabled, automatically detect the bridge IP for each known Docker service
3. After detecting the bridge IP, replace 127.0.0.1 in the URL with the bridge IP
4. If detection fails (non-Docker environment or network anomaly), fall back to the original URL
5. Cache the bridge IP in memory, and check before each connection whether a refresh is needed
```

Note: this fix is at the client layer rather than the service layer, because the problem lies in the Docker network layer, not in the service code.

### Problem 3: ToxinPred3 model loading thread-safety issue

**Symptom**: ToxinPred3 is based on sklearn's ExtraTreesClassifier, whose predict method hangs under multithreaded concurrency. The `asyncio.wait_for` timeout mechanism does not help, because the hang happens at the C extension level and asyncio cannot interrupt it.

**Current status**: The client uses small batches (batch_size=10) + consecutive timeout detection + a restart strategy.

**Fix requirement**: Add a global inference lock at the ToxinPred3 service layer:

```
In service.py:
  1. Create a threading.Lock() after model initialization
  2. predict_impl() acquires the lock on entry and releases it on exit
  3. This does not affect throughput (the processing time of a single request is unaffected by the lock)
  4. But it prevents multiple requests from entering sklearn's C extension layer at the same time
```

### Problem 4: asyncio.gather exception propagation causes cascading crashes

**Symptom**: The default behavior of `asyncio.gather(*tasks)` is that as soon as one task throws an uncaught exception, all other running or waiting tasks are cancelled immediately. When batch processing hundreds of constructs, an exception in a single task cancels all tasks and the whole run is interrupted.

**Current status**: The client uses two-layer isolation (outer `return_exceptions=True` + inner try/except).

**Fix requirement**: Establish a standardized batch task execution pattern in the client library or stage scripts:

```
Standard pattern:
  1. Define safe_task_wrapper() as a unified wrapper with complete exception handling and logging
  2. Always use return_exceptions=True during batch execution
  3. Check results uniformly after execution, collecting exception information without interrupting the flow
  4. Include exception counts in the run report instead of blocking the run
```

### Problem 5: Inconsistent PDB batch API response format

**Symptom**: In the JSON structure returned by the batch endpoints of SASA and Aggrescan3D, the position of the score field within a single result is inconsistent with the single-item API. The batch response puts it at the top level, while the single-item response puts it in result.score.

**Fix requirement**: Unify the batch and single-item response formats:

```
Single-item response: {"result": {"score": 0.5, ...}, ...}
Batch response: {"results": [{"score": 0.5, ...}, ...]}
```

That is: the structure of each entry in the batch results is consistent with the structure of the `result` field of the single-item result.

---

## 3. Concurrency and Resource Management Rules

### GPU memory management

**Symptom**: Multiple GPU microservices (ESMFold, OmegaFold, BepiPred-3.0, pLM4CPPs, etc.) share 24G of GPU memory. Loading several models at the same time causes CUDA OOM.

**Rules**:
1. Service layer: each microservice executes `torch.cuda.empty_cache()` immediately after `load_model()` and sets `torch.backends.cudnn.benchmark = True`
2. Orchestration layer: the docker-compose profiles are already grouped by GPU/CPU, ensuring GPU-intensive services are not started at the same time
3. Runtime: control GPU visibility through the `CUDA_VISIBLE_DEVICES` environment variable (although its effect is limited with a single GPU)
4. Use `detect_gpu()` in `tools/utils.py` for unified GPU detection

### Concurrency control

| Service type | Recommended concurrency | Notes |
|---------|-----------|------|
| FastaToolService subclasses | 10 | Lightweight sequence prediction, CPU-intensive |
| StructureService subclasses | 1 | GPU inference, serial execution |
| PdbScoringService subclasses | 10 | Lightweight PDB analysis |
| ToxinPred3 (special) | 1 | sklearn thread-safety constraint |

### Timeout strategy

| Service | Timeout | Notes |
|------|------|------|
| Lightweight sequence services | 30s | Single prediction |
| Batch sequence services | 120s | Batch prediction |
| Structure prediction (ESMFold) | 600s | Single structure prediction |
| Structure prediction (OmegaFold) | 14400s | OmegaFold is slower |
| PDB evaluation | 60s | Lightweight computation |

---

## 4. Network Stability Rules

### Avoiding Docker-proxy

Accessing container services through `127.0.0.1:PORT` has been proven unreliable in this environment (see Problem 2).

**Rules**:
1. All URLs obtained through `main/config.py:service_url()` should support bridge IP override
2. Perform a network detection once at pipeline startup to determine how all services in the cluster are reachable
3. Log the network topology: `[NET] SASA: 172.17.0.5:8101 (bridge)`
4. If bridge IP detection fails, fall back to 127.0.0.1 and warn

### Failure retry strategy

All HTTP calls should follow:
1. First failure → wait 1s, retry
2. Second failure → wait 5s, retry
3. Third failure → log the error and skip (do not block the overall flow)
4. For long tasks such as structure prediction the retry strategy differs: retry at the task level with task-level timeouts, rather than retrying the HTTP request

---

## 5. Storage and I/O Rules

### Database-first principle

In stages3 all intermediate results must be written to the database; CSV files are no longer relied upon to pass data between stages:

| Storage object | Storage method | Retention policy |
|---------|---------|---------|
| Candidate peptide sequences + metadata | DuckDB `candidates` table | Whole lifecycle |
| Per-stage scores | DuckDB per-stage tables | Whole lifecycle |
| Final ranking | DuckDB `final_ranking` table | Whole lifecycle |
| PDB files | Filesystem `output3/pdb/` | Whole lifecycle |
| Log files | Filesystem `output3/logs/` | Archived by round |
| Reports | Filesystem `output3/reports/` | Retained permanently |

### Checkpoint rules

Every stage must support resuming from the point of interruption:
1. Record `checkpoint_start` to the database when the stage starts
2. Record `checkpoint_done` to the database when the stage ends
3. On a resumed run, query `checkpoint_done` and skip completed stages
4. For large batch processing (such as the millions of scores in Stage 2), finer-grained intermediate checkpoints should be supported

---

## 6. CI / Code Quality Rules

### Final checklist

Check each item before submitting a PR:

- [ ] Are all microservices running in Docker?
- [ ] Do all Docker health checks pass?
- [ ] Are there any blocking calls not handled with `run_in_executor`?
- [ ] Do batch tasks use `return_exceptions=True`?
- [ ] Is the database connection independent per thread?
- [ ] Are the timeout settings reasonable?
- [ ] Do the logs record the key steps and errors?

---

## Appendix: Summary of stages2 Technical Problems

| # | Problem | Impact | Fix status | See Problem # |
|---|------|------|---------|---------|
| 1 | OmegaFold sync blocking | Event loop blocked, health check unavailable | Client workaround, service side pending fix | 1 |
| 2 | Docker proxy connection instability | httpx long connections hang intermittently | Client workaround, automation pending | 2 |
| 3 | ToxinPred3 sklearn thread safety | Hangs under high concurrency | Client workaround, service side pending fix | 3 |
| 4 | asyncio.gather cascading crash | A single task exception cancels everything | Fixed on the client (two-layer isolation) | 4 |
| 5 | Batch API response format inconsistency | Parsing errors, 0/90 succeeded | Fixed, format still to be unified | 5 |
| 6 | Docker Compose build atomicity | One failure rolls back everything | Batched builds required | — |
| 7 | Running microservices directly on the host | Inconsistent environment, time-consuming debugging | Mandatory rules in this document | — |
