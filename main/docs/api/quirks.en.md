> English translation of [quirks.md](quirks.md). The Chinese original is kept unchanged as the source of truth.

# Known API Pitfalls & How to Handle Them

Every service behavior that deviates from the template standard, plus the bugs encountered during pipeline development.

---

## 1. SASA: batch response score is at the top level, not in `result.score`

**Symptom**: The SASA single endpoint returns `{"success": true, "result": {"score": 0.76, ...}}`, but the Batch endpoint returns `{"success": true, "results": [{"peptide_id": "con_001", "score": 0.76, ...}]}`. The `score` in batch results is at the top level, **not** `results[].result.score`.

**Scope of impact**: All code that calls `predict_pdb_batch("sasa", ...)`.

**Handling**: When parsing batch results, read the value via `r.get("score")`, not `r["result"]["score"]`.

**Verification**: `predict_pdb_batch` in `main/client.py` returns the raw JSON, and the caller adapts it.

---

## 2. SASA: missing `sequence` parameter returns score=0

**Symptom**: SASA needs to know the functional peptide's sequence in order to locate the specific region in the PDB. When `sequence` is not passed, it returns `score=0.0`, `label="no_target"`.

**Cause**: In `score_pdb()`, the SASA service first uses FreeSASA to compute per-residue SASA for the whole structure, then uses `sequence` to locate the peptide region in the residue list parsed by Biopython, and finally reports only the mean relative SASA of the peptide region. Without `sequence` it cannot locate the region and defaults to returning 0.

**Handling**: When calling SASA, the request must include the `sequence` field:
```json
{
  "pdb_content": "ATOM      1  N   ...",
  "sequence": "YVPLPNVPQG",
  "peptide_id": "con_001"
}
```

**Verification**: Call SASA `/predict/batch` with `sequence` included and confirm `score > 0`.

---

## 3. OmegaFold: blocks the event loop, Semaphore(1) is mandatory

**Symptom**: OmegaFold's `self.model(input_data)` is a synchronous PyTorch CUDA call, which blocks uvicorn's event loop inside `async def`. Concurrency above 1 causes request queue timeouts or service crashes.

**Handling**: Clients must serialize requests with `asyncio.Semaphore(1)`, and set `timeout=14400` per request (4 hours, although only 90-120s is actually needed).

**Impact**: OmegaFold is the throughput bottleneck of the whole pipeline (~120s/construct, forced serialization).

---

## 4. ToxinPred3: sklearn is not thread-safe

**Symptom**: ToxinPred3 uses sklearn's ExtraTreesClassifier, whose C extension hangs under concurrent requests. High concurrency causes socket connections to pile up and the service stops responding.

**Handling**:
- Restrict client concurrency to Semaphore(2)
- Send only a single sequence at a time (batch_size=1)
- Use socket-level timeouts (httpx timeout=180s)
- Fallback: after 5 consecutive timeouts, call `POST /restart` to restart the service

**Verification**: The service itself declares `recommended_batch_size = 50`, but actual pipeline experience shows that batch_size=1 + Sem(2) is the most stable.

---

## 5. Waveflow: path contains the tool name `/predict/{tool}`

**Symptom**: Waveflow's routing pattern differs from other structure services:
- `POST /predict/esmfold` (not `/predict`)
- `POST /predict/batch/omegafold`
- `POST /predict/async/alphafold3`
- `GET /status/{job_id}` / `GET /result/{job_id}` — these follow the standard async pattern

It is also compatible with `POST /predict` (using the `WAVEFLOW_DEFAULT_TOOL` environment variable, default `esmfold`).

**Handling**: Pay attention to the URL path format when calling Waveflow directly. When calling via `ServiceClient.predict_structure_async()`, specify the service name `waveflow` and the client will assemble the path automatically.

---

## 6. TemStaPro: GPU OOM risk

**Symptom**: TemStaPro has a two-stage architecture — first ProtT5-XL encoding (~11GB GPU), then parallel inference by 30 MLP classifiers. An internal `Semaphore(10)` limits it to 10 groups × 30 MLPs = 300 classifiers running at once, but an overly large batch can still cause GPU OOM.

**Handling**:
- Restrict client concurrency to Semaphore(2-5)
- Set the timeout to 300-600s
- If OOM occurs, restart the container and lower concurrency

---

## 7. Aggrescan3D: starts a Docker subprocess per request

**Symptom**: Aggrescan3D runs inside a Python 2.7 micromamba container, and each prediction launches a separate process via subprocess. The first call has a slow cold start (~10s), and excessive concurrency exhausts system resources.

**Handling**:
- An internal `Semaphore(2)` limits the number of subprocesses running at once
- Client `timeout=900s` (configurable via the `A3D_TIMEOUT` environment variable)
- Send 50 per batch to reduce cold-start overhead through batching

---

## 8. SASA single vs Batch response structure inconsistency

| Endpoint | Response structure |
|----------|--------------------|
| `POST /predict` | `{"success": true, "peptide_id": "...", "result": {"score": 0.76, "label": "exposed", "details": {...}}}` |
| `POST /predict/batch` | `{"success": true, "results": [{"peptide_id": "...", "score": 0.76, "label": "exposed", "details": {...}}]}` |

Note that batch results have no `result` nesting layer. This is the design of the PDB service template; the FASTA service template uses `result` nesting on both endpoints.

---

## 9. BetaFold / ESMFold: pLDDT is low on silk fusion proteins

**Symptom**: ESMFold gives pLDDT < 0.30 for silk repeat sequences, so it cannot be used for downstream SASA/A3D analysis. OmegaFold's pLDDT ~0.41 is usable.

**Cause**: ESM-2's training data lacks structures resembling silk repeat sequences.

**Handling**: Prefer OmegaFold for silk fusion proteins. Use ESMFold only as a substitute.

---

## 10. Docker Bridge IP, not 127.0.0.1

**Symptom**: When accessing containers via `127.0.0.1:PORT` (docker-proxy), long HTTP requests may hit httpx keep-alive hangs. This is a known docker-proxy issue.

**Handling**: Use `docker inspect` to get the container's bridge IP and connect directly. Already implemented in `detect_bridge_ip()` in `s4_docker_utils.py`.

---

## 11. asyncio.gather exception safety

**Symptom**: `asyncio.gather(*tasks)` without `return_exceptions=True` cancels all other tasks when any one task fails.

**Handling**: Always use `return_exceptions=True` in batch processing and check exceptions task by task.
