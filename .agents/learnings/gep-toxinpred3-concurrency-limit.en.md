---
name: ToxinPred3 Single-Threaded Concurrency Limit and Hang Recovery Strategy v1.0
author: Claude Code
created: 2026-05-15
version: 1.0.0
tags: [toxinpred3, sklearn, concurrency, timeout, recovery, extra-trees]
validated: true
---

> English translation of [gep-toxinpred3-concurrency-limit.md](gep-toxinpred3-concurrency-limit.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: ToxinPred3 Single-Threaded Concurrency Limit and Hang Recovery Strategy

## Experience

**Problem description**: ToxinPred3 (sklearn ExtraTreesClassifier) periodically hangs (100% CPU, unresponsive) when processing large batches of peptide sequences. After a hang, all concurrent connections pile up, and eventually every batch fails.

**Environment**: The ToxinPred3 microservice (FastAPI + uvicorn), CPU inference, no GPU. The backend model is an sklearn ExtraTreesClassifier (AAC+DPC, 420-dimensional features). The service runs as an independent process under `tools/ToxinPred3/`.

### Root Cause Analysis

1. **sklearn ExtraTreesClassifier single-threaded limitation**: `predict()` of ExtraTreesClassifier calls a C extension underneath (`sklearn.ensemble._forest`), running single-threaded. When processing certain sequences it may enter an infinite loop or deadlock (getting stuck in tree traversal), leaving the process at 100% CPU and never returning
2. **Concurrent requests cause CLOSE_WAIT accumulation**: With `asyncio.Semaphore(N)` at concurrency ≥2, a hung request blocks the uvicorn worker and subsequent requests queue up. After the client (httpx) times out and disconnects, the server-side socket enters CLOSE_WAIT and accumulates, and eventually all new requests fail
3. **asyncio.wait_for is unreliable**: Python's `asyncio.wait_for(coro, timeout=120)` cannot reliably cancel while httpx is waiting for a socket response. The reason is that httpx's `await` points may not respond to `CancelledError` (depending on internal implementation state). The synchronous version `requests.post(..., timeout=120)` uses kernel-level socket timeouts and is far more reliable

### Solution

The final approach was **synchronous + small batches + continuous timeout detection + service restart**:

| Strategy | Parameter | Principle |
|------|------|------|
| Synchronous requests | `timeout=120` | Kernel socket timeout, more reliable than asyncio cancellation |
| Small batches | 200 items/batch (formerly 1000) | A hung batch loses at most 200 items |
| Consecutive timeout detection | 5 consecutive timeouts trigger a restart | Clears the hung worker |
| Serial execution | Single connection, single request | Avoids socket pile-up |
| Skip and continue | Mark as None after a timeout and continue to the next batch | Does not affect the overall flow |

### Key Parameters

| Parameter | Value | Description |
|------|-----|------|
| Batch size | 200 | Originally 1000; reducing it lowers per-batch risk |
| Timeout | 120s | Normally 16s/batch; 120s is sufficient yet can cut off a hang |
| Consecutive timeout threshold | 5 | Triggers the service `/restart` endpoint |
| Client type | `requests` (synchronous) | Replaces `httpx` (async); timeouts are more reliable |
| Overall throughput | ~12 seq/s | Limited by ExtraTrees being single-threaded |

### Evolution Record

1. **Concurrent Semaphore=10**: All 100/100 batches failed, CLOSE_WAIT accumulated
2. **Concurrent Semaphore=2**: The first half was OK; around 80K the service hung and caused widespread timeouts
3. **Serial httpx**: 7 batches OK, the 8th hung, and `asyncio.wait_for` 120s could not cut it off (unresponsive for 30 minutes)
4. **Synchronous requests + 200-item batches + 120s timeout**: All 500 batches completed, 100,000/100,000 valid, 0 timeouts

### Applicable Scenarios

Any microservice using a non-thread-safe sklearn model (ExtraTrees, RandomForest, etc.) that hangs intermittently during large-batch inference:

- Prefer synchronous requests + system-level timeouts (`requests` > `asyncio.wait_for`)
- Small batches (200–500) reduce per-call risk
- Consecutive failures trigger a hot service restart
- Serialization avoids socket pile-up

### Related Files

- `main/stages2/round02_toxinpred3_sync.py` — the final successful approach
- `main/stages2/round02_toxinpred3_robust.py` — the asyncio version (unreliable timeout, deprecated)
- `main/stages2/round02_toxinpred3_serial.py` — the serial httpx version (timeout still unreliable)
- `main/stages2/round02_recover_toxinpred3.py` — the initial concurrent version
- `tools/ToxinPred3/service.py` — the ToxinPred3 microservice entry point
