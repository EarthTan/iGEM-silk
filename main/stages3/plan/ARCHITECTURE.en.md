> English translation of [ARCHITECTURE.md](ARCHITECTURE.md). The Chinese original is kept unchanged as the source of truth.

# Stages3 Pipeline Architecture

> Version: v1.0 — 2026-05-15
> Execution environment: single Linux machine | 128G RAM | RTX 3090 24G | SSD
> Data scale: tens of millions to hundreds of millions of sequences

---

## 1. Overall Architecture

### The Three Layers of the Architecture

The stages3 architecture is divided into three layers, with a clear separation of responsibilities at each layer:

```
┌────────────────────────────────────────────────────────────────────────────┐
│                            Orchestration Layer                             │
│                        Pipeline Orchestration Layer                        │
│  Each Stage runs independently, handing off data via the database          │
│  Checkpoints control the flow; progress tracking drives recovery           │
├────────────────────────────────────────────────────────────────────────────┤
│                              Execution Layer                               │
│                              Execution Layer                               │
│  Concurrency: batch-request microservices → collect results → write to DB  │
│  Driven by the asyncio event loop; httpx handles async HTTP communication  │
│  Error isolation: a single failure does not affect the rest                │
├────────────────────────────────────────────────────────────────────────────┤
│                               Service Layer                                │
│                             Microservice Layer                             │
│  16 Docker microservices behind a unified API                              │
│  Orchestrated by Docker Compose; health checks ensure availability         │
│  GPU services run serially; CPU services can run in parallel               │
└────────────────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities in Detail

The **orchestration layer** is responsible for "what to do":
- Deciding which stage to run now
- Restoring progress from the checkpoint table
- Advancing the flow to the next stage
- Generating progress reports and statistics

The **execution layer** is responsible for "how to do it":
- Reading the list of candidates to process
- Concurrently dispatching microservice requests
- Handling timeouts, retries, and exceptions
- Writing results to the database
- Updating checkpoints

The **service layer** is responsible for "providing services":
- Accepting requests and returning predictions
- Maintaining service health
- Managing model loading and GPU resources

### Differences from stages2

| Dimension | stages2 | stages3 |
|------|---------|---------|
| Data handoff | CSV files | DuckDB database |
| Progress recovery | Manual inspection of output files | Automatic recovery from checkpoint table |
| Concurrency control | Manually managed inside scripts | Unified scheduling by the execution layer |
| Weighting strategy | Fixed weights | Variance-aware dynamic weights |
| Error tolerance | Two-level isolation (fixed) | Standardized isolation pattern |
| Microservice deployment | Sometimes Docker, sometimes host machine | Docker mandatory |

---

## 2. Execution Flow

### Topology of the Six Stages

Dependencies between stages are linear—each stage depends on the output of the previous stage. Within each stage, however, there is ample opportunity for parallelism.

```
Stage 0 (preprocessing)
  │ output: candidates table
  ▼
Stage 1 (lightweight primary screening)
  │ output: stage1_scores + stage1_passed
  ▼
Stage 2 (full scoring)
  │ output: stage2_scores + score_distribution + weight_config
  ▼
Stage 3 (construct enumeration)
  │ output: constructs + construct_scores
  ▼
Stage 4 (3D structure)
  │ output: structure_jobs + PDB files
  ▼
Stage 5 (PDB evaluation)
  │ output: pdb_eval
  ▼
Stage 6 (final ranking)
  │ output: final_ranking + reports
```

### Batch Pattern Within a Stage

Each stage follows the same internal batch pattern:

```
loop:
  1. Read a batch of pending candidates from the database (e.g., 100k)
  2. Concurrently call the relevant microservices (batch or single endpoint)
  3. Collect results, record failures
  4. Write results into the corresponding table in the database
  5. Update the checkpoint (record the range of processed candidate_ids)
  6. If more candidates remain, return to step 1
  7. If no candidates remain, enter the aggregation analysis phase
```

### Aggregation Analysis Phase

After each scoring stage there is an aggregation analysis step:

```
After Stage 1-2-5-6 complete:
  1. Read all valid scores from the corresponding score tables
  2. Compute distribution statistics per service (mean, standard deviation, percentiles)
  3. Compute the winsorized standard deviation (trim the top and bottom 1%)
  4. Write to the score_distribution table
  5. Compute variance-aware weights and write them to the weight_config table
  6. Apply the weights to produce the ranking
```

---

## 3. Single-Machine Parallelism Strategy

### Bottleneck Analysis

For a pipeline running tens of millions to hundreds of millions of sequences, the bottleneck differs by stage:

| Stage | Bottleneck type | Cause of the bottleneck | Mitigation |
|------|---------|---------|---------|
| Stage 0 | I/O + CPU | 220G FASTA scan + CD-HIT clustering | Multi-threaded reading + block-level parallelism |
| Stage 1 | Network I/O | HTTP requests to microservices | Concurrent requests + batch API |
| Stage 2 | Network I/O | 7 services × millions of candidates | Same as above + larger batch size |
| Stage 3 | CPU | Sequence assembly + 2 services | Lightweight, few candidates |
| Stage 4 | GPU | Serial inference on a single GPU | Cannot parallelize; accept the wait |
| Stage 5 | Network I/O | PDB file transfer + 2 services | batch API |

### Parallelism Strategy for Network I/O

The core parallelism strategy of stages3 targets network I/O—most of the time is spent waiting for HTTP responses from microservices.

**Choosing the microservice call style**:

Our stages2 experience shows that batch API and single API each fit different service types:

| Service | Recommended approach | Notes |
|------|---------|------|
| AnOxPePred (lightweight) | batch API | < 100ms per sequence; batching reduces HTTP overhead |
| BepiPred-3.0 (GPU) | batch API | GPU inference is more efficient in batches |
| pLM4CPPs (GPU, large model) | single API | Large models are expensive to load; serial is more stable |
| ToxinPred3 (sklearn) | single API | Thread-safety issues; must be serialized |
| Other CPU services | batch API | Pure CPU computation; batching is more efficient |

**Concurrency control**:

All microservice requests share a single httpx.AsyncClient connection pool, capped at 50 connections.

The core scheduling logic of the execution layer:
- Read a batch of N pending candidates (N depends on the service type)
- Fire all requests concurrently with asyncio
- For lightweight services, N = 50-100 (high concurrency)
- For GPU services, N = 10-20 (limit concurrency to avoid overloading the server)
- Collect results, handle exceptions, write to the database

**Key design**: instead of a separate stage loop for each service, **one batch of candidates queries all relevant services at the same time**. For example, in Stage 2 a batch of 100 candidates queries 7 services concurrently, waits for the slowest one to finish, then writes to the database.

### CPU-Bound Parallelism

For CPU-intensive tasks such as CD-HIT:
- CD-HIT natively supports multithreading (the `-T` flag)
- Where possible, first bucket candidates by length and run a separate CD-HIT instance per bucket

For FASTA parsing:
- Use Python's mmap to memory-map very large files
- Read in blocks with multiple threads (1G per block)
- Each thread parses its own block independently, with special handling for sequences that span block boundaries

---

## 4. Error Isolation and Recovery

### Error Classification

| Error type | Example | Handling |
|---------|------|---------|
| Transient errors | Network timeout, service temporarily unresponsive | Automatic retry (up to 3 times, with increasing intervals) |
| Permanent errors | Model loading failure, service down | Skip the candidate, record the cause |
| System-level errors | Disk full, out of memory, GPU OOM | Pause the pipeline and wait for manual intervention |
| Data errors | Malformed sequence, invalid characters | Skip the candidate, record it in the error log |

### Error Isolation in Batch Processing

stages2 experience has already proven: in batch processing, **a single failure must never affect the other tasks**.

The standardized isolation pattern (described in words):

Within the request flow for each batch of candidates:
1. All requests are fired concurrently
2. Every request must return, whether it succeeds or fails (a timeout also counts as a return)
3. Requests that return an exception do not participate in score computation but are recorded in the error log
4. Successful results are written to the database as usual
5. Only after the whole batch finishes does the next batch begin

This pattern was validated in round05 of stages2—even when OmegaFold prediction failed for some constructs in the process, the remaining 89 were unaffected.

### Interruption Recovery

stages3's interruption recovery is stronger than stages2's:

**Scenario 1: the script is interrupted midway through Stage 2**

On recovery:
1. The checkpoint table shows Stage 2's status as "running"
2. Query the stage2_scores table to find the largest candidate_id already processed
3. Continue from the next candidate_id
4. Existing candidate records are not processed again (upsert semantics)

**Scenario 2: a microservice is unavailable for a long time**

Handling:
1. After the retry count is exceeded, set that service's score column to NULL
2. In score_distribution, NULL columns do not participate in standard deviation computation
3. The corresponding service's weight is 0, automatically excluded from the composite score
4. The pipeline keeps running and does not block

**Scenario 3: GPU out of memory**

Handling:
1. Catch the CUDA OOM exception
2. Clear the GPU cache (torch.cuda.empty_cache())
3. Wait 30 seconds for the GPU to release memory
4. Retry once
5. If it is still OOM, skip the current task

---

## 5. Memory Management

### Memory Budget

| Purpose | Budget | Notes |
|------|------|------|
| Operating system and other processes | 16G | System overhead |
| Docker microservices | 16G | Several services concurrently, ~1-2G each |
| DuckDB in-memory mode | 32G | Set a memory limit to prevent OOM |
| CD-HIT clustering | 32G | Index 30 million short sequences |
| Pipeline scripts | 16G | Python runtime + data cache |
| **Total** | **~112G** | Leaves ~16G headroom |

### DuckDB Memory Control

DuckDB uses in-memory mode by default, but a memory limit can be set. To set it: `SET memory_limit = '32GB'`. When the limit is exceeded, it spills to disk automatically instead of crashing.

### Large File Handling

For FASTA files of 200G+, do not use readlines() or other load-everything-at-once approaches. Instead:
- mmap memory mapping: the file is mapped into the virtual address space, and the OS manages the page cache automatically
- Streaming iterator: read line by line, discard each line once processed

### Database Write Frequency

One trap of writing tens of millions of rows is transaction log bloat. Solutions:
- Commit once after each batch finishes (~100k rows per batch)
- Do not use row-by-row INSERT; use batch INSERT

---

## 6. Logging and Monitoring

### Three-Level Logging System

| Level | Output | Content |
|------|------|------|
| Console (info) | Terminal | Stage progress, completion percentage, issues found |
| File (debug) | `output3/logs/<stage>.log` | Details, per-record exception entries, HTTP request logs |
| Checkpoint | Database checkpoint table | Structured progress data |

### Key Monitoring Metrics

After each stage run, a monitoring report is generated automatically:

| Metric | Source | Meaning |
|------|------|------|
| Throughput (rows/s) | Timer | Estimate time to completion |
| Success rate (%) | Successful requests / total requests | Service health |
| Score distributions | score_distribution table | Assessment of discriminative power |
| Error distribution | Exception log | Problem localization |
| Weight changes | weight_config table | Feature importance |

---

## 7. Docker Integration

### Standard Startup Sequence

The standard startup sequence before a pipeline run (a precondition for the stage scripts):

```
Step 1: Check whether the Docker daemon is running
Step 2: Check whether docker-compose.yml exists
Step 3: Check whether the Docker images for all services are built
Step 4: Start Docker Compose (if not running)
Step 5: Poll the health endpoint of every service until all are ready
Step 6: If any service is still not ready after 60 seconds, print the failure and exit
Step 7: Record DOCKER_RUNNING=true in memory; subsequent scripts check this flag
```

### Service Discovery

stages2 uses `main/config.py:service_url()` to obtain service addresses. stages3 extends this mechanism:

The default URL is the Docker bridge IP (auto-detected) + the internal Docker port. Detection flow:

```
Service address resolution logic:
  1. Try Docker bridge IP detection (obtained via docker inspect)
  2. On success, use the bridge IP
  3. On failure (non-Docker environment), fall back to 127.0.0.1
  4. If the {NAME}_HOST environment variable is set, it overrides all of the above
```

This logic runs once when the client connection is initialized and is then cached.

---

## 8. Where Variance-Aware Weighting Fits In

Variance-aware weighting is the "intelligent" part of the entire stages3 architecture. Its place in the architecture:

```
┌────────────────────────────────────────────────────────────────┐
│            Execution Layer (plain batch processing)            │
│   Large-batch scoring → raw scores written to stage2_scores    │
└────────────────────────────────┬───────────────────────────────┘
                                 ▼
┌────────────────────────────────────────────────────────────────┐
│            Aggregation Analyzer (Analytics Engine)             │
│              Read score_distribution → compute σ               │
│           → normalize weights → write weight_config            │
│   → apply weights to produce ranking → write stage2_ranking    │
└────────────────────────────────────────────────────────────────┘
```

The aggregation analyzer is a separate component (not embedded in the batch loop); it runs after each scoring stage completes. The benefits of this approach:

1. **Separation of concerns**: batch processing only obtains raw scores and does not care how they are used
2. **Re-entrancy**: weights and rankings can be recomputed at any point in time (e.g., after adjusting the winsorization parameters)
3. **Auditability**: the weight_config table records the result of every weight computation and can be traced

---

## 9. Evolution Roadmap from stages2 to stages3

### Incremental Refactoring, Not a Rewrite

stages3 does not start from scratch. Most of the stages2 scripts can be reused:

| stages2 script | Change in stages3 |
|-------------|----------------|
| step00_integrate.py | Replaced by data preprocessing (CD-HIT + length filter + DB write) |
| round01_lightweight.py | Keep the scoring logic; switch to DB reads and writes |
| round02_scoring.py | Keep the scoring logic; add variance weight computation |
| round03_heavy.py | Can be merged into the new Stage 2 |
| round04_enumerate.py | Largely reusable; switch the output to DB |
| round05_3d.py | Largely reusable |
| round06_pdb_eval.py | Largely reusable |
| round07_final.py | Keep the output logic |

The most essential refactoring work:
1. Data handoff: from CSV to DuckDB
2. Add the aggregation analyzer component
3. Add the checkpoint system
4. Unify the Docker startup sequence
5. Server-side fixes for technical issues

### Development Order

1. Installation validation: CD-HIT + DuckDB
2. Infrastructure: db.py interface module, config.py extensions, checkpoint system
3. Data preprocessing: FASTA parser, CD-HIT wrapper, length filtering
4. Scoring stages: migrate the round01 → round02 logic to the new architecture and integrate variance weighting
5. Subsequent stages: migrate the round04 → round07 logic
6. Report generation: database-backed statistical reports and final output
