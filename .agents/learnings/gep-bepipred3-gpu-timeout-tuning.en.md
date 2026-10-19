---
name: BepiPred3 GPU Concurrency and Timeout Systematic Tuning v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [bepipred3, gpu, timeout, semaphore, concurrency, batch-processing]
validated: true
---

> English translation of [gep-bepipred3-gpu-timeout-tuning.md](gep-bepipred3-gpu-timeout-tuning.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: BepiPred3 GPU Concurrency and Timeout Systematic Tuning

## Experience

**Problem description**: When the BepiPred3 GPU service batch-processed 300 constructs (Round 4) and 15K sequences (Round 3), many requests failed due to timeouts. On the first run of 300 constructs only 50/300 succeeded (17% success rate); all the rest timed out in httpx.

**Symptoms**:
- httpx `ReadTimeout` exceptions, even with timeout=300s set
- Some requests finished computing on the server but the client never received a response
- Service logs show normal GPU utilization and inference in progress
- Inconsistent failure pattern: retrying the same construct sometimes succeeds and sometimes fails

**Root cause**: Three nested layers of timeout problems:

1. **Concurrency too high (Semaphore=5)**: The GPU service takes ~115s per 50-seq request batch, and Semaphore=5 allows 5 concurrent requests → queued requests cannot get an execution slot within 300s
2. **Timeout too short (300s)**: A single batch of 50 takes about 115s; with 5 concurrent requests the 5th request must wait 4×115=460s + 115s=575s, far exceeding the 300s timeout
3. **docker-proxy compounding effect**: Long-running requests through docker-proxy (127.0.0.1) suffer intermittent keep-alive hangs (see gep-docker-container-bridge-ip.md), further reducing effective throughput

**How the three independent problems compound**:
```
Semaphore=5 + 300s timeout + docker-proxy
    → 5 requests enter the GPU at once
    → the GPU processes them serially (single card); 4 are queued
    → from the 3rd queued request on, execution is already beyond 300s
    → the first 2 finish and return, but docker-proxy may hang
    → the 3rd-5th are certain to time out
    → by the time a request's turn comes the Semaphore has been released → new requests enter → timeouts continue
    → in the end only a few short sequences succeed
```

### Solution

**Three-dimensional systematic tuning**, adjusting three parameters together:

| Parameter | Original value | New value | Rationale |
|------|------|------|------|
| Semaphore | 5 | **1** | GPU inference is serial; concurrency >1 only piles up the queue |
| Timeout | 300s | **600s** | A 115s batch with 0s queue wait (Semaphore=1) needs a 2× safety margin |
| Batch Size | 100 | **50** | Smaller batches reduce per-request time and lower the timeout probability |

```python
# round04_fix_bepipred3.py — parameters after the fix
BATCH_SIZE = 50          # was 100
BEPIPRED_SEMAPHORE = 1   # was 5
BEPIPRED_TIMEOUT = 600   # was 300
```

**Key insight**: The GPU service performs serial inference on a single card; Semaphore >1 **never increases throughput**, it only raises the timeout probability for queued requests. Semaphore=1 + a long timeout is the optimal configuration.

### Diagnostic Method

| Step | Command/method | What to look for |
|------|-----------|------|
| 1. Check the service logs | `docker compose logs bepipred3` | GPU utilization, inference time |
| 2. Compute the success rate | Compare request count vs. successful responses | 17% is extremely low |
| 3. Test a single request | Time one curl request | Confirm ~115s/50-seq |
| 4. Analyze the timeout pattern | Are the failing requests always the queued ones | Confirm it is a queueing timeout, not an execution timeout |
| 5. Check the network layer | Switch to a direct bridge IP connection | Rule out docker-proxy interference |

### Final Results

- Round 3 (15K sequences): fully completed; the weights were written into the composite score
- Round 4 (300 constructs): 150/150 valid (after excluding ESMFold-only), 0 errors
- Success rate: **17% → 100%**

### Environment Fingerprint

- **Task domain**: GPU microservice batch inference, asyncio client
- **Input characteristics**: A single inference takes 60-120s; the GPU executes serially
- **Constraints**: Single GPU card, limited VRAM, cannot scale horizontally
- **Trigger pattern**: Client concurrency > the GPU's serial execution capacity + insufficient timeout
- **Not applicable**: Multi-threaded CPU services (Semaphore may be >1); distributed GPU clusters; services with inference time <10s

### Related Experience

- `gep-docker-container-bridge-ip.md` — docker-proxy long-connection hangs, the network layer of the same problem
- `gep-omegafold-sync-inference-blocking.md` — OmegaFold is likewise serial on the GPU and likewise uses Semaphore=1

### Audit Record

- **Validation method**: Production runs of stages2 Round 3 + Round 4
- **Test cases**:
  1. Semaphore=5, timeout=300s → 50/300 succeeded (17%)
  2. Semaphore=1, timeout=300s → about 210/300 succeeded (70%, still affected by docker-proxy)
  3. Semaphore=1, timeout=600s, bridge IP → 300/300 succeeded (100%)
- **Success rate**: 100%
- **Limitations**: Inference speed was not optimized at the server level. If a single batch takes >600s (longer sequences), the timeout must be increased further.
