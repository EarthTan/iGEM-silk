> **English** | [中文](principles.zh.md)

# Pipeline Engineering Principles

<!-- This document describes the design principles, engineering aesthetics, and best practices of the pipeline code under the main/ directory. -->

---

## (a) How to Call Microservices

### 1. The Three Service Templates

All microservices follow one of three interface templates, and `ServiceClient` provides a corresponding call method for each:

| Template | Input | Output | Call method |
|----------|-------|--------|-------------|
| FASTA service | `sequence` (str) | `score` (float) | `predict_single()` / `predict_batch()` |
| Structure service | `sequence` (str) | `pdb_content` (str) | `predict_structure_async()` (job polling) |
| PDB scoring service | `pdb_content` (str) + `sequence` (str) | `score` (float) | `predict_pdb_single()` / `predict_pdb_batch()` |

Each service belongs to exactly one template. Do not guess a service's interface inside business logic — check the `type` field in `services.json`.

### 2. Prefer Batch Calls

- Use `predict_batch()` by default, unless the service forces single-sequence sends
- Exception: ToxinPred3 (sklearn `ExtraTreesClassifier` is not thread-safe, so single sequences only)
- Batch size is a **performance-critical parameter** and must be balanced between throughput and timeout

### 3. Use Semaphore to Control Concurrency

Each service's concurrency is declared explicitly in code as `asyncio.Semaphore(N)`. The value of N depends on:

- **Service type**: GPU services must consider VRAM limits (TemStaPro → low concurrency; pLM4CPPs → high concurrency possible)
- **Thread safety**: in CPU services, the C extensions of sklearn/skrebayes may not be thread-safe → Semaphore(1-2)
- **Instance count**: with multi-container deployment, each container has its own Semaphore (safe across processes)

The default Semaphore values serve a **balance point between throughput × stability**, determined through actual stress testing.

### 4. Avoid 127.0.0.1 (Docker Bridge IP)

When accessing Docker containers, **never use `127.0.0.1:PORT`**. Forwarding through docker-proxy causes intermittent httpx keep-alive hangs.

The correct approach: get the bridge IP with `docker inspect`:

```python
def _fix_docker_network(service_name: str) -> str:
    import docker
    client = docker.from_env()
    container = client.containers.get(service_name)
    network = container.attrs["NetworkSettings"]["Networks"]
    bridge = list(network.values())[0]
    return bridge["IPAddress"]
```

Alternative: if the host can reach the container port directly and there is no keep-alive problem, 127.0.0.1 can be used (requires verification).

### 5. Health Check First

Before any scoring step begins, call `ensure_services()` to confirm the dependent services are ready. This avoids the disaster of "running for an hour and then discovering the service is down".

```python
health = ensure_services(required_services, profiles=["gpu"], timeout=180.0)
unavailable = [s for s, h in health.items() if not h["available"]]
if unavailable:
    sys.exit(1)  # never continue
```

### 6. asyncio.gather Must Use return_exceptions=True

Otherwise, when one coroutine raises an exception → all coroutines are cancelled. That is devastating in batch processing.

```python
# ❌ Wrong: one failure cancels everything
results = await asyncio.gather(*tasks)

# ✅ Correct: exceptions are returned as values
results = await asyncio.gather(*tasks, return_exceptions=True)
for r in results:
    if isinstance(r, Exception):
        continue  # handle leniently, do not block the overall flow
```

### 7. Service-Agnostic Calls

`ServiceClient` is transparent with respect to service names — `predict_batch("hemopi2", items)` and `predict_batch("sodope", items)` go through the same code. Service addresses and ports are managed only by `config.py`, and business logic need not care.

```python
# config.py is the single parameter control panel
SERVICES["hemopi2"]   = {"port": 8004}
SERVICES["sodope"]    = {"port": 8012}

# can be overridden at runtime via environment variables
# export HEMOPI2_HOST=192.168.1.50
```

---

## (b) Balancing Resources and Speed

### 1. CPU First, GPU Queued by Weight

GPU VRAM is the scarcest resource in the pipeline (49GB, but a single model can occupy 20GB+).

Rules for ordering services:

1. **Run CPU services first** — CPU services such as SoDoPE and TIPred do not compete for the GPU and produce results quickly
2. **GPU services from light to heavy** — pLM4CPPs (~2GB) → GraphCPP (~2GB) → BepiPred3 (~6GB) → TemStaPro (~20GB)
3. **Only one GPU service loads a model at a time** — avoid model-loading OOM caused by VRAM contention

### 2. Using Idle Resources (Pre-scoring)

When the pipeline is blocked by a CPU bottleneck (for example, ToxinPred3 running for 16h), the GPU sits completely idle. This is the time to launch **pre-scoring** — using the idle GPU to compute the scores of later stages in advance.

The core pattern:

```
CPU-bound service (serial)  ←-- pipeline waits
    ↓
GPU idle → pre-scoring script → roundN_scores table (idempotent writes)
    ↓
CPU bottleneck completes → main pipeline continues → sees that pre-scored data is complete → skips the scoring stage
```

The "waste" of pre-scoring (some candidates are ultimately eliminated and their pre-scored data is discarded) is far smaller than the loss of "GPU idling while waiting".

### 3. More Concurrency Is Not Always Better

Concurrency has two hard constraints:

- **VRAM ceiling**: a single GPU service loads one model at a time. Semaphore(N) causes N requests to queue up; this does not increase VRAM pressure (the model is already loaded), but too many piled-up requests cause timeouts. Rule of thumb for N: `timeout / per-request duration × 0.8`.
- **Thread safety**: sklearn's C extensions (`ExtraTreesClassifier`, `RandomForest`) hang under multithreading. Semaphore(1) or Semaphore(2) is the safe upper bound. Multiple containers = multiple processes = safe.

### 4. Multiple Instances Break the Server-Side Single-Thread Limit

For services that are not thread-safe (ToxinPred3), the throughput of a single process with Semaphore(1) is too low. The solution: deploy multiple Docker container instances, each with its own process, and have the client distribute candidate chunks (round-robin or sharding).

```python
# multiple instances = multiple processes = physically isolated sklearn = safe
TOXIN_INSTANCES = ["toxinpred3", "toxinpred3-2", "toxinpred3-3"]
for idx, inst in enumerate(TOXIN_INSTANCES):
    start = idx * per_instance
    # each instance handles an independent subset of candidates
    instance_batches.append((inst, all_candidates[start:end]))
```

Each instance still uses Semaphore(2) internally as a conservative control. Throughput then equals `N_instances × single-instance throughput`.

### 5. On-Demand Service Startup

Starting all 16 services wastes GPU VRAM (a PyTorch CUDA context occupies GBs). Each round starts only the services it needs:

- Round 1: anoxpepred + algpred2 (2 services)
- Round 2: toxinpred3 × 3 + hemopi2 + mhcflurry (5 services)
- Round 3: bepipred3 + temstapro + sodope + plm4cpps + graphcpp (5 services)

Docker Compose's `--profile` mechanism supports this natively. `s4_service_map.py` records the dependencies of each round.

---

## (c) Batch Persistence, Disaster Tolerance, and Robustness

### 1. Never Collect Everything in Memory

This is the pipeline's most central data-safety principle.

After each batch is scored, **write it to the database immediately**; never accumulate. Writes use `ON CONFLICT DO UPDATE` (idempotent), so the same row can be safely updated by different rounds.

```python
# ❌ Wrong: all scores collected in memory, written in one final shot
results = []
for chunk in chunks:
    scores = await score_chunk(chunk)
    results.extend(scores)
db.write_all(results)  # crashes after 16h of running → everything lost

# ✅ Correct: write immediately after each batch is scored
for chunk in chunks:
    scores = await score_chunk(chunk)
    db.insert_scores(scores)  # ON CONFLICT DO UPDATE, idempotent
```

### 2. Persist Fast Data First

When several services with very different durations run in parallel, the fast ones produce results first and land them first. Even if a slow service crashes, the fast services' results are not lost.

For example, the safety screening in Round 2:
1. HemoPI2 / MHCflurry (~minutes) → **write 1.4 million rows immediately**
2. ToxinPred3 (~16 hours) → write once every 200 sequences

As long as HemoPI2/MHCflurry have written their results, rerunning all of ToxinPred3 costs only 16h and does not lose the completed hemo/mhc data.

### 3. Idempotent Writes (ON CONFLICT DO UPDATE)

All `insert_*` methods use `INSERT ... ON CONFLICT (candidate_id) DO UPDATE SET ...`. This means:

- The same candidate can be written multiple times
- Different rounds writing different fields do not overwrite each other
- Repeated execution does not produce duplicate rows

This is the foundation for pre-scoring, checkpointed resumption, and crash recovery.

### 4. Checkpoint + Resume

Each stage writes a checkpoint recording `round`, `step`, `status`, and `processed_items`. At startup the script first checks:

```python
if get_checkpoint(round, step) == "done":
    log("skipped (it was completed last time)")
    continue  # or decide where to resume from based on processed_items
```

Checkpoints support two recovery granularities:
- Service-level recovery (skip services already completed)
- Candidate-level recovery (resume from the last processed candidate_id + 1)

### 5. Snapshot to Break the Single-Writer Lock

DuckDB allows only one write connection at a time. If Round 2 holds the write lock, the Round 3 pre-scoring script cannot read pipeline.db.

The solution: create a snapshot:

```python
import shutil
snapshot = pipeline_db.with_name(f"pipeline_{ts}.db")
shutil.copy2(pipeline_db, snapshot)
# read from the snapshot (separate file, no lock)
# write to precompute.db (separate file, no contention with Round 2)
```

Pre-scoring results are written to a **separate precompute.db**, and after Round 2 completes they are merged back into pipeline.db with `--merge`.

### 6. Minimizing the Loss Window

Mini-batch size determines the maximum amount of data lost on a crash. Reasonable choices:

| Service | Mini-batch | Max loss | Consideration |
|---------|------------|----------|---------------|
| ToxinPred3 | 200 sequences | ~3 minutes | ~1s per sequence; 200 sequences is exactly one gather batch |
| HemoPI2 | All at once | 0 (continue only after writing) | Extremely fast, no need to split into mini-batches |
| Deep scoring | 1000 sequences | ~2 minutes | Batch is a natural boundary |

Principle: mini-batch size = the maximum amount of work you are willing to recompute after a crash.

### 7. Tolerance for Exceptions

A single failed request **does not interrupt the overall flow**. Check the values returned by asyncio.gather for Exception instances; on failure, write NULL for the corresponding field and continue. After all scoring is done, NULL entries can be retried if needed.

```python
scored = await asyncio.gather(*tasks, return_exceptions=True)
for c, s in zip(mini, scored):
    if isinstance(s, Exception):
        continue  # write NULL, do not block
    # normal handling
```

### 8. Separate Databases

Different stages use separate DuckDB files to avoid lock contention:

| Database | Purpose | Who writes |
|----------|---------|------------|
| `pipeline.db` | Main pipeline state | Round 1-7 executing in sequence |
| `precompute.db` | Pre-scoring staging | Pre-scoring script (in parallel with Round 2) |
| (snapshot) | Read-only snapshot | Created by a cp command, read by pre-scoring |

When the main pipeline runs in sequence, `pipeline.db` is sufficient. Separate databases are needed only when pre-scoring must run in parallel during a CPU bottleneck.

---

## Priority of the Principles

When principles conflict, settle it by this priority:

1. **No data loss > speed** — better slow than lost. Batch writes > a faster single-write scheme that carries a risk of data loss
2. **Idempotency > special-case optimization** — making writes repeatable is safer than "high performance but requires careful handling of edge cases"
3. **Explicit configuration > implicit assumptions** — Semaphore values, batch sizes, and thresholds are declared explicitly at the top of the code
4. **Simple and correct > complex and efficient** — a sequential but correct flow > a parallel design that may go wrong

---

*This document is continuously updated as pipeline experience accumulates. Behind every principle is a production incident or hours of debugging paid as the price.*
