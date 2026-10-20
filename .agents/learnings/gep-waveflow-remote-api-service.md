---
name: Waveflow Remote API Proxy Microservice Pattern v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [tamarind, remote-api, microservice, structure-prediction, esmfold, api-proxy, waveflow]
validated: true
---

> **English** | [中文](gep-waveflow-remote-api-service.zh.md)

# Gene Capsule: Remote API Proxy Microservice Pattern

## Experience

**Problem type**: Wrapping a third-party cloud API (tamarind.bio) as a local microservice so that it uses the same API contract and invocation style as the other local microservices (ESMFold, OmegaFold, etc.).

**Core strategy**:

1. **Tool type specified in the URL path**: `POST /predict/{tool}` rather than via environment variables or the request body. A single service instance can proxy esmfold, omegafold, alphafold and other tools, with no need for multiple deployments.

2. **Do not use the template `create_app`**: The service logic of a remote API proxy (submit → poll → download) differs too much from the template that runs local models, so a custom FastAPI app should be used instead of inheriting `StructureService`'s `create_app`. Still reuse data models such as `StructureResult` to keep the interface consistent.

3. **API key management**: `TAMARIND_API_KEY` is managed centrally via `tools/.env`, and Docker Compose injects it with the `${VAR:-}` syntax under `environment:`. Local development requires an explicit `export`.

4. **Async HTTP client**: Use `httpx.AsyncClient` to manage the HTTP connection pool to tamarind, with reasonable timeouts (10s connect, 30s request).

5. **ZIP result handling**: tamarind's `/result` returns a presigned ZIP download URL (a string); it must be downloaded, extracted, and `model.pdb` pulled out. Use `io.BytesIO` + `zipfile.ZipFile` to process in memory without writing temporary files.

### Tamarind REST API Response Format Cheat Sheet

| Endpoint | Input | Output format | Notes |
|------|------|----------|------|
| `POST /submit-job` | `{ jobName, type, settings: { sequence } }` | `"<jobName> submitted to queue."` (string) | Not JSON! Need `resp.text.strip().strip('"')` |
| `GET /jobs?jobName=X` | Query parameter | `{"0": {"JobName":"...", "JobStatus":"Complete|Running|In Queue", ...}, "statuses": {...}}` | Number-indexed dictionary, not an array |
| `POST /result` | `{ jobName }` | `"https://presigned-url/result-xxx.zip"` (JSON string) | The outer quotes must be stripped to get the URL |
| `POST /result` (batch) | `{ jobName, pdbsOnly: true }` | Same as above | `pdbsOnly` applies only to batch jobs |
| `POST /submit-batch` | `{ tool, batchName, jobs: [{ jobName, settings }] }` | String | Batch submission |

### Key Parameters

- Base URL: `https://app.tamarind.bio/api/` (trailing slash, enforced in code)
- Auth header: `x-api-key: <key>`
- Polling interval: 15s (configurable via `TAMARIND_POLL_INTERVAL`)
- Timeout: 3600s (1 hour, configurable via `TAMARIND_TIMEOUT`)
- Result ZIP contains: `model.pdb`, `output.log`, `metrics.csv`, `metrics.parquet`, `ptm*.png`, `ptm*.pae.txt`

## Environment Fingerprint

- **Task domain**: Wrapping third-party cloud biology APIs as local microservices with a unified interface
- **Input characteristics**: FastAPI + httpx async HTTP client; no local model/GPU
- **Constraints**: 
  - The tamarind API response formats are non-standard (strings / unusual JSON structures) and require per-endpoint adaptation
  - A network connection and a valid API key are required
  - Subject to remote queueing and network latency (417aa ESMFold takes about 200s)
- **Not applicable**:
  - Services with local GPU inference (should use the `StructureService` template)
  - Production environments requiring low latency / offline operation
  - Scenarios without a tamarind API key

## Audit Record

- **Validation method**: The iGEM-silk Waveflow service actually called tamarind ESMFold to predict a 417aa fusion protein
- **Test cases**:
  1. Submit the short sequence `MGRGGSGGY` → submission confirmation string → polling completes → download ZIP → extract `model.pdb` → validate the PDB format ✔
  2. Submit the 417aa full-length construct (con_0009) → completed in 201 seconds → 226 KB PDB file ✔
  3. Start without an API key → `/health` returns `status: "loading"` and an error message ✔
- **Success rate**: 100% (passed in a single test)
- **Limitations**: The batch endpoint was not tested; non-ESMFold tool types were not tested; timeout/API error scenarios were not tested

## Usage

- **Trigger conditions**: A remote API needs to be wrapped as a local microservice, and that API follows the async submit + poll pattern
- **How to invoke**: 
  - Development: `cd tools/Waveflow && TAMARIND_API_KEY=xxx uv run python service.py`
  - Docker: set `TAMARIND_API_KEY` in `tools/.env`, then `docker compose --profile cpu up -d waveflow`
  - Request: `curl -X POST http://localhost:8205/predict/esmfold -d '{"sequence":"..."}'`
- **Caveats**:
  - Each tamarind endpoint has a different response format; it must be tested manually and confirmed before implementation
  - `/submit-job` returns a string rather than JSON, so `resp.json()` will raise an exception
  - `JobStatus` field values for `/jobs`: `Complete`, `Running`, `In Queue`, `Failed`, `Stopped`
  - The URL returned by `/result` is a JSON string (with quotes), requiring `resp.text.strip().strip('"')`
  - Look for `model.pdb` in the result ZIP, not `structure.pdb` or any other name
  - The `pdbsOnly` parameter applies only to batch jobs; passing it for a single job raises an error
  - In Docker Compose, variables are injected from `.env` via `environment` + `${VAR:-}`, but this only works for `docker compose up`; a local `uv run` requires a manual export
