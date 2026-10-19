> English translation of [conventions.md](conventions.md). The Chinese original is kept unchanged as the source of truth.

# API Conventions Manual

The microservice APIs in this system are designed to be templated and contract-based throughout. All microservices follow one of three templates:
- **FASTA service** (sequence → score/classification)
- **PDB service** (PDB structure → score)
- **Structure service** (sequence → 3D structure)

Each template defines consistent endpoint paths, request/response models, error handling, and health check formats.

---

## 1. General Conventions

### 1.1 Transport Protocol

| Item | Convention |
|------|------------|
| Protocol | HTTP/1.1 |
| Content-Type | `application/json` |
| Encoding | UTF-8 |
| Port ranges | Scoring 8001-8012, safety filtering 8003-8008, structure prediction 8201-8205, PDB scoring 8101-8102 |
| Authentication | None (internal network, not externally exposed) |

### 1.2 Status Codes

| Status code | Meaning |
|-------------|---------|
| 200 | Success (including business errors such as `success: false`) |
| 202 | Async job accepted (async mode only) |
| 422 | Request body validation failed (missing field / wrong type) |
| 500 | Internal service error |

### 1.3 Common Endpoints

```http
GET /health   → HealthResponse
GET /info     → InfoResponse
```

#### HealthResponse

```json
{
  "status": "healthy",
  "tool_name": "anoxpepred",
  "version": "1.1.0",
  "model_loaded": true,
  "model": {
    "status": "ready",
    "model_mode": "cnn",
    "backend": "gpu"
  },
  "system": {
    "device": "gpu",
    "gpu_available": true,
    "gpu_name": "NVIDIA RTX 5880 Ada Generation",
    "gpu_memory": "47 GB"
  }
}
```

`status` values: `"healthy"` (available), `"loading"` (model loading, a transient state).

#### InfoResponse

```json
{
  "tool_name": "anoxpepred",
  "description": "Antioxidant peptide prediction",
  "version": "1.1.0",
  "capabilities": ["score", "classify"],
  "recommended_batch_size": 50,
  "model_type": "cnn",
  "backend": "gpu"
}
```

`recommended_batch_size` is the server-side recommended upper bound; clients should not exceed it.

---

## 2. FASTA Service Template

Applies to: AnOxPePred, BepiPred3, ToxinPred3, HemoPI2, MHCflurry, AlgPred2, pLM4CPPs, TIPred, GraphCPP, TemStaPro, SoDoPE.

### 2.1 Endpoints

```http
POST /predict          # single prediction
POST /predict/batch    # batch prediction
```

### 2.2 Request Format

#### Single: `POST /predict`

```json
{
  "sequence": "YVPLPNVPQG",
  "peptide_id": "pep_001"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sequence` | string | Yes | Single-letter amino acid sequence, 1-5000 aa |
| `peptide_id` | string | No | Identifier, defaults to `"unknown"` |

#### Batch: `POST /predict/batch`

```json
{
  "sequences": [
    {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"},
    {"sequence": "CYVPLPNVPQ", "peptide_id": "pep_002"}
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sequences` | array | Yes | 1-1000 sequences |

**⚠️ The batch request payload key is `sequences` (not `requests`)**. This is the key difference between the FASTA template and the PDB template.

### 2.3 Single Response

```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "peptide_id": "pep_001",
    "sequence": "YVPLPNVPQG",
    "score": 0.8732,
    "label": "antioxidant",
    "details": {
      "frs_score": 0.8732,
      "chel_score": 0.4418,
      "confidence": 0.9983,
      "is_antioxidant": true
    }
  },
  "error": null
}
```

| Top-level field | Type | Description |
|-----------------|------|-------------|
| `success` | bool | Whether the call succeeded. **Note**: even when `success: true`, `result` may still be null (the service has no error but cannot score) |
| `peptide_id` | string | Identifier passed in the request |
| `sequence` | string | Original request sequence |
| `result` | object|null | Scoring result. null on failure |
| `error` | string|null | Error message |

#### result object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `peptide_id` | string | No | Defaults to `"unknown"` |
| `sequence` | string | No | Echoes the original sequence |
| `score` | float | **Yes** | Primary score, 0-1 |
| `label` | string | **Yes** | Classification label; values vary by service |
| `details` | dict | Yes (may be empty) | Service-specific additional information |

### 2.4 Batch Response

```json
{
  "success": true,
  "results": [
    {
      "peptide_id": "pep_001",
      "sequence": "YVPLPNVPQG",
      "score": 0.8732,
      "label": "antioxidant",
      "details": {}
    },
    {
      "peptide_id": "pep_002",
      "sequence": "CYVPLPNVPQ",
      "score": 0.2341,
      "label": "non-antioxidant",
      "details": {}
    }
  ],
  "total": 2,
  "error": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Whether the call succeeded |
| `results` | array | Array of result objects. **Note**: unlike the single endpoint, batch results have no `result` nesting layer; `score`/`label` are at the top level |
| `total` | int | Number of successful scores. If `< input length`, some items failed |
| `error` | string|null | Global error message |

**⚠️ There is no `result` nesting in batch responses**. Read `results[0].score` directly, not `results[0].result.score`.

### 2.5 `label` Value Reference

| Service | Possible label values |
|---------|----------------------|
| AnOxPePred | `"antioxidant"`, `"non-antioxidant"` |
| ToxinPred3 | `"Toxin"`, `"Non-Toxin"` |
| HemoPI2 | `"hemolytic"`, `"non-hemolytic"` |
| MHCflurry | `"binder"`, `"non-binder"` |
| AlgPred2 | `"Allergen"`, `"Non-Allergen"` |
| BepiPred3 | `"epitope"`, `"non-epitope"` |
| TemStaPro | `"stable"`, `"unstable"` |
| SoDoPE | `"soluble"`, `"insoluble"` |
| pLM4CPPs | `"CPP"`, `"non-CPP"` |
| GraphCPP | `"CPP"`, `"non-CPP"` |
| TIPred | `"inhibitor"`, `"non-inhibitor"` |

### 2.6 Server-Side Default Configuration

```python
recommended_batch_size = 50  # recommended upper bound on batch size (server side)
semaphore = asyncio.Semaphore(10)  # server-side concurrency limit (overridable in subclasses)
```

---

## 3. PDB Service Template

Applies to: SASA, Aggrescan3D.

### 3.1 Endpoints

```http
POST /predict          # single PDB scoring
POST /predict/batch    # batch PDB scoring
```

### 3.2 Request Format

#### Single: `POST /predict`

```json
{
  "pdb_content": "ATOM      1  N   ASP A   0     -23.404   9.271  13.678  1.00 18.04           N  \nATOM      2  CA ...",
  "sequence": "YVPLPNVPQG",
  "chain_id": "A",
  "peptide_id": "con_001"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `pdb_content` | string | **Yes** | Full PDB-format content |
| `sequence` | string | No (but required by SASA) | Functional peptide sequence, used to locate the peptide in the PDB |
| `chain_id` | string | No | Target chain, defaults to `"A"` |
| `peptide_id` | string | No | Identifier, defaults to `"unknown"` |

**⚠️ SASA returns score=0 if `sequence` is not passed**. See item 2 in quirks.md.

#### Batch: `POST /predict/batch`

```json
{
  "requests": [
    {
      "pdb_content": "ATOM      1  N   ...",
      "sequence": "YVPLPNVPQG",
      "peptide_id": "con_001"
    },
    {
      "pdb_content": "ATOM      1  N   ...",
      "sequence": "DNWWPKPPH",
      "peptide_id": "con_002"
    }
  ]
}
```

**⚠️ The batch request payload key is `requests` (not `sequences`)**. This is the key difference between the PDB template and the FASTA template.

### 3.3 Batch Response Format (different from single!)

#### Single: `POST /predict`

```json
{
  "success": true,
  "peptide_id": "con_001",
  "result": {
    "peptide_id": "con_001",
    "score": 0.7638,
    "label": "exposed",
    "details": {
      "chain": "A",
      "peptide": {
        "mean_relative_sasa": 0.7638,
        "num_residues": 10,
        "num_exposed": 8
      }
    }
  },
  "error": null
}
```

#### Batch: `POST /predict/batch`

```json
{
  "success": true,
  "results": [
    {
      "peptide_id": "con_001",
      "score": 0.7638,
      "label": "exposed",
      "details": {...}
    }
  ],
  "total": 2,
  "error": null
}
```

| Comparison point | Single | Batch |
|------------------|--------|-------|
| Location of score | `result.score` | `results[].score` (no result nesting) |
| Field structure | success/peptide_id/result/error | success/results/total/error |

When parsing batch results, always use `r.get("score")`.

### 3.4 `details` Structure of PDB Services

#### SASA

```json
{
  "chain": "A",
  "probe_radius": 1.4,
  "exposure_threshold": 0.25,
  "peptide": {
    "sequence": "YVPLPNVPQG",
    "num_residues": 10,
    "num_exposed": 6,
    "total_sasa": 452.3,
    "mean_relative_sasa": 0.7638,
    "exposure_ratio": 0.6,
    "residue_ids": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "residues": [
      {"residue_id": 1, "residue_name": "TYR", "residue_code": "Y", "sasa": 45.2, "relative_sasa": 0.82, "is_exposed": true},
      ...
    ]
  },
  "all_residues": [...]
}
```

#### Aggrescan3D

```json
{
  "risk_score": 0.31,
  "statistics": {
    "num_residues": 372,
    "min_score": -1.24,
    "max_score": 0.89,
    "avg_score": 0.31,
    "positive_fraction": 0.28,
    "positive_mean": 0.52
  },
  "top_hotspots": [
    {"chain": "A", "residue_id": 145, "residue_name": "VAL", "score": 0.89}
  ],
  "residues": [
    {"protein": "silk", "chain": "A", "residue_id": 1, "residue_name": "ASP", "a3d_score": -0.45, "is_aggregation_prone": false},
    ...
  ],
  "output_pdb_content": "ATOM ...",
  "aggrescan3d": {
    "conda_env": "aggrescan3d",
    "distance_cutoff": 5.0
  }
}
```

---

## 4. Structure Service Template

Applies to: ESMFold, OmegaFold, AlphaFold3, PEP-FOLD4, Waveflow.

### 4.1 Endpoints

#### Synchronous mode (ESMFold, OmegaFold, PEP-FOLD4)

```http
POST /predict          # single structure prediction
POST /predict/batch    # batch structure prediction
```

#### Async job mode (AlphaFold3; optional for others)

```http
POST /predict/async          # submit job → returns job_id (202)
GET  /status/{job_id}        # query job status
GET  /result/{job_id}        # fetch job result
GET  /status                 # all running jobs
GET  /jobs                   # all historical jobs
DELETE /jobs/{job_id}        # delete job
```

#### Waveflow-specific

```http
POST /predict/{tool}         # tool = esmfold | omegafold | alphafold
POST /predict/batch/{tool}
POST /predict/async/{tool}
```

### 4.2 Request Format

#### Single: `POST /predict`

```json
{
  "sequence": "YVPLPNVPQG",
  "peptide_id": "pep_001"
}
```

Same PredictRequest as the FASTA template.

#### Batch: `POST /predict/batch`

```json
{
  "sequences": [
    {"sequence": "YVPLPNVPQG", "peptide_id": "pep_001"}
  ]
}
```

Same BatchPredictRequest as the FASTA template.

#### Async submission: `POST /predict/async`

```json
{
  "sequence": "YVPLPNVPQG",
  "peptide_id": "pep_001"
}
```

Response 202:

```json
{
  "job_id": "abc123def456",
  "status_url": "/status/abc123def456",
  "status": "pending"
}
```

### 4.3 Response Format

#### Single synchronous response

```json
{
  "success": true,
  "peptide_id": "pep_001",
  "sequence": "YVPLPNVPQG",
  "result": {
    "peptide_id": "pep_001",
    "sequence": "YVPLPNVPQG",
    "pdb_content": "ATOM      1  N   ...",
    "confidence": 0.8732,
    "details": {
      "mean_plddt": 0.8732,
      "sequence_length": 10,
      "model_version": "v1.0",
      "device": "cuda"
    }
  },
  "error": null
}
```

#### Batch synchronous response

```json
{
  "success": true,
  "results": [
    {
      "peptide_id": "pep_001",
      "sequence": "YVPLPNVPQG",
      "pdb_content": "ATOM ...",
      "confidence": 0.8732,
      "details": {}
    }
  ],
  "total": 1,
  "error": null
}
```

#### Async status query: `GET /status/{job_id}`

```json
{
  "job_id": "abc123def456",
  "status": "running",
  "progress": "3/5",
  "created_at": 1716012345.67,
  "finished_at": null
}
```

`status` values: `"pending"` → `"running"` → `"success"` | `"failed"`

#### Async result fetch: `GET /result/{job_id}`

```json
{
  "job_id": "abc123def456",
  "sequence": "YVPLPNVPQG",
  "status": "success",
  "pdb_content": "ATOM ...",
  "confidence": 0.8732,
  "details": {},
  "error": null
}
```

### 4.4 PDB File Saving Recommendations

- One PDB file per sequence, named `{peptide_id}.pdb`
- Store each prediction set in the `output4/pdb/{peptide_id}/` directory
- Keep the original B-factor column (OmegaFold fills it with confidence×100)

### 4.5 `details` Fields of Each Structure Service

| Service | details fields | Notes |
|---------|----------------|-------|
| OmegaFold | `mean_plddt`, `sequence_length`, `model_version`, `num_cycle`, `device` | pLDDT = confidence |
| ESMFold | `mean_plddt`, `ptm_score`, `sequence_length` | pTM is the global folding confidence |
| AlphaFold3 | `mean_plddt`, `ptm_score`, `iptm_score`, `full_pae` (matrix), `model_version` | The PAE matrix can be very large |
| PEP-FOLD4 | `sequence_length` | Limited to 5-40 aa |
| Waveflow | `tool_type`, `job_name`, `elapsed_seconds`, `sequence_length` | Remote API elapsed time |

---

## 5. Batch Call Guidance

### 5.1 Per-Service Recommended Configuration Quick Reference

| Service | Type | Batch size | Concurrency | Timeout (s) | GPU/CPU |
|---------|------|------------|-------------|-------------|---------|
| AnOxPePred | fasta | 1000 | 10 | 120 | GPU |
| AlgPred2 | fasta | 1000 | 10 | 120 | CPU |
| ToxinPred3 | fasta | **1** | **2** | 180 | CPU |
| HemoPI2 | fasta | 100 | 10 | 180 | GPU |
| MHCflurry | fasta | 100 | 10 | 180 | GPU |
| BepiPred3 | fasta | 1000 | 5 | 300 | GPU |
| TemStaPro | fasta | 1000 | 5 | 300 | GPU |
| SoDoPE | fasta | 1000 | 10 | 300 | CPU |
| pLM4CPPs | fasta | 100 | 5 | 300 | GPU |
| GraphCPP | fasta | 100 | 5 | 300 | GPU |
| SASA | pdb | 50 | 10 | 300 | CPU |
| Aggrescan3D | pdb | 50 | **2** | 300 | CPU |
| OmegaFold | structure | **1** | **1** | 14400 | GPU |
| ESMFold | structure | 5 | 3 | 600 | GPU |
| AlphaFold3 | structure | 1 | 1 | 14400 | GPU |
| PEP-FOLD4 | structure | 1 | 3 | 1800 | CPU |
| Waveflow | structure | 5 | 3 | 3600 | CPU(remote) |

### 5.2 Key Points of Concurrency Control

```
toxinpred3: Semaphore(2), batch_size=1   ← sklearn is not thread-safe
omegafold:  Semaphore(1), batch_size=1   ← blocks the event loop
aggrescan3d: Semaphore(2)                ← high Docker subprocess overhead
temstapro:  Semaphore(5)                 ← GPU OOM risk
```

Other FASTA services can use `Semaphore(10)` + `batch_size=1000`.

### 5.3 Client Code Pattern

```python
from main.client import ServiceClient

client = ServiceClient(timeout=120.0)

# FASTA scoring
result = await client.predict_batch("anoxpepred", items)
# items = [{"peptide_id": "1", "sequence": "YVPL..."}, ...]
# result["results"][0]["score"]

# PDB scoring
result = await client.predict_pdb_batch("sasa", items)
# items = [{"peptide_id": "1", "pdb_content": "ATOM...", "sequence": "YVPL..."}]
# result["results"][0]["score"]  ← note: score is at the top level

# structure prediction (synchronous)
result = await client.predict_structure_sync("omegafold", items)
# items = [{"peptide_id": "1", "sequence": "YVPL..."}]
# result["results"][0]["pdb_content"]

# structure prediction (asynchronous)
result = await client.predict_structure_async("alphafold3", sequence)
```

---

## 6. Error Handling Contract

### 6.1 Business Errors vs HTTP Errors

- **HTTP 4xx/5xx**: network-layer or framework-layer errors (malformed request body, internal service error)
- **HTTP 200 + `success: false`**: business-layer errors (model not loaded, sequence too long, PDB parsing failure)

All business-logic errors are expressed inside the JSON body through the `success` and `error` fields.

### 6.2 Partial Failure

Individual sequences in a batch request may fail. In that case:
- `success: true` (the overall request succeeded)
- `total < input length` (the number of partial failures)
- A failed item's `details` may contain an `error` field
- A failed item's `score` is `null`

```json
{
  "success": true,
  "results": [
    {"peptide_id": "1", "score": 0.87, "details": {}},
    {"peptide_id": "2", "score": null, "details": {"error": "Sequence too long: 6001 > 5000"}}
  ],
  "total": 1,
  "error": null
}
```

### 6.3 Health Check Degradation

`GET /health` may return the following `status` values:

| status | Meaning | Handling |
|--------|---------|----------|
| `"healthy"` | Service available, model loaded | Call normally |
| `"loading"` | Model is loading (first startup or after a restart) | Wait, then retry |
| `"degraded"` | Service partially available (e.g., model files missing, rule-based fallback in use) | AnOxPePred-specific; calls work but accuracy is reduced |

---

## 7. `label` + `score` Meaning Matrix per Service

| Service | Meaning of score | Range | Semantics of label |
|---------|------------------|-------|--------------------|
| AnOxPePred | Antioxidant probability | 0-1 | antioxidant / non-antioxidant |
| ToxinPred3 | Toxicity probability | 0-1 | Toxin / Non-Toxin |
| HemoPI2 | Hemolysis probability | 0-1 | hemolytic / non-hemolytic |
| MHCflurry | Binding probability | 0-1 | binder / non-binder |
| AlgPred2 | Allergenicity probability | 0-1 | Allergen / Non-Allergen |
| BepiPred3 | Epitope probability | 0-1 | epitope / non-epitope |
| TemStaPro | Stability score | 0-1 | stable / unstable |
| SoDoPE | Solubility probability | 0-1 | soluble / insoluble |
| pLM4CPPs | CPP probability | 0-1 | CPP / non-CPP |
| GraphCPP | CPP probability | 0-1 | CPP / non-CPP |
| TIPred | Inhibition probability | 0-1 | inhibitor / non-inhibitor |
| SASA | Mean relative SASA | 0-1 | exposed / partial / buried / no_target |
| Aggrescan3D | Aggregation risk | 0-1 | high/moderate/low_aggregation_risk |
| OmegaFold | None | None (`confidence` is pLDDT) | None (structure quality is expressed by pLDDT) |
| ESMFold | None | None (`confidence` is pLDDT) | None |

---

## 8. Quick Lookup

See `services.json` for the complete service configuration in machine-readable form (ports, batch, concurrency, thresholds, known details keys).
