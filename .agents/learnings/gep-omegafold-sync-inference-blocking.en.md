---
name: OmegaFold Synchronous Inference Blocking the Event Loop and Concurrency Control v1.0
author: Claude Code
created: 2026-05-15
version: 1.0.0
tags: [omegafold, async, event-loop, blocking, semaphore, structure-service]
validated: true
---

> English translation of [gep-omegafold-sync-inference-blocking.md](gep-omegafold-sync-inference-blocking.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: OmegaFold Synchronous Inference Blocking the Event Loop and Concurrency Control

## Experience

**Problem description**: The OmegaFold microservice's `predict_structure()` method calls PyTorch `model(input_data)` directly inside an `async def` for synchronous inference (taking 90-120s). This blocks uvicorn's asyncio event loop, so the service cannot respond to any other request while handling a single request (/health, /status/{job_id}, and /result/{job_id} all hang).

**Symptoms**:
- With concurrency ≥2, the POST /predict/async of the second construct times out (httpx 30s timeout)
- curl requests to the health endpoint from the host machine hang, but `docker exec` requests inside the container work normally
- In the logs every OmegaFold entry is marked "N/A (30s)", because it already timed out at the POST stage

**Root cause** (templates/structure_service.py):
```python
# tools/template/structure_service.py — problematic code
async def predict_structure(self, sequence: str) -> StructureResult:
    # ... prepare data ...
    result = self.model(input_data, predict_with_confidence=True)  # synchronous blocking! 90-120s
    # ... process result ...
```
`self.model(...)` is PyTorch CUDA inference; calling it inside an `async def` blocks the entire event loop. uvicorn is a single-threaded event loop and cannot handle other requests while waiting.

### Solution

**Option 1: client-side Semaphore (adopted by this pipeline)**

```python
# main/stages2/round05_3d.py
OMEGAFOLD_CONCURRENCY = 1   # global serialization
omegafold_sem = asyncio.Semaphore(OMEGAFOLD_CONCURRENCY)

async def timed_predict(service: str, seq: str, cid: str, timeout: float) -> dict:
    if service == "omegafold" and omegafold_sem is not None:
        async with omegafold_sem:     # ensure only 1 OmegaFold request at a time
            result = await client.predict_structure_async(...)
    else:
        result = await client.predict_structure_async(...)
    return result
```

| Parameter | Value | Description |
|------|-----|------|
| OMEGAFOLD_CONCURRENCY | 1 | Global concurrency limit |
| Timeout | 14400s (4h) | OmegaFold takes ~6min per sequence, which is sufficient |
| Polling interval | 30s | Standard structure prediction polling |

**Option 2: server-side fix (recommended, but not implemented this time)**

Move the blocking inference into `asyncio.get_event_loop().run_in_executor()` or a `concurrent.futures.ThreadPoolExecutor` to release the event loop:

```python
# Recommended approach: use a thread pool in service.py
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=1)  # GPU inference should still be serialized

async def predict_structure(self, sequence: str) -> StructureResult:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor,
        lambda: self.model(input_data, predict_with_confidence=True)
    )
    # ... process result ...
```

### Environment Fingerprint

- **Task domain**: Structure prediction microservices, FastAPI/uvicorn services in async mode
- **Input characteristics**: Synchronous inference calls from deep learning frameworks such as PyTorch/TensorFlow
- **Constraints**: GPU inference is not cancelable and completes in 60-120s per call
- **Trigger pattern**: Asynchronous job pattern (POST /predict/async → poll GET /status/{job_id})
- **Not applicable**: Lightweight models with CPU inference <5s (little impact); services that already use `run_in_executor`

### Audit Record

- **Validation method**: Production run of 90 constructs; before adding the Semaphore the OmegaFold success rate was 0/2 (the first 2 already timed out), after adding it 90/90 succeeded
- **Test cases**:
  1. CONCURRENCY=2, no Semaphore → the second OmegaFold times out during the 30s POST stage → N/A
  2. CONCURRENCY=2, OmegaFold_CONCURRENCY=1 → all 90 completed, OmegaFold executed serially (~6min/item × 90 = ~9h, running in parallel with ESMFold so no extra time is added)
- **Success rate**: 90/90 (100%)
- **Limitations**: The client-side Semaphore only bypasses the problem; the server-side event loop is still blocked (it merely prevents concurrent requests from entering). Fixing it at the `service.py` level is recommended.
