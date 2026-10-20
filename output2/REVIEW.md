> **English** | [中文](REVIEW.zh.md)

# Stages2 Pipeline Review — iGEM-silk Antioxidant Peptide Fusion Protein Design

**Generated**: 2026-05-18
**Status**: entire pipeline complete
**Output directory**: `output2/`

---

## 1. What Was Done

Completed an end-to-end rerun of all 8 rounds of the stages2 pipeline (Step 0 to Round 7), screening from 1.08 million candidate peptides down to a final 90 Top candidate constructs + 60 Bottom controls. The output includes the complete result package: 3D structures (OmegaFold PDB), surface evaluation (SASA + Aggrescan3D), full-pipeline score aggregation, and independent dual-channel rankings.

### Pipeline Overview

| Stage | Time | Data volume change |
|------|------|-----------|
| Step 0: data integration | ~30s | 1,081,772 → **1,055,116** |
| Round 1: lightweight scoring (AnOxPePred+AlgPred2) | ~15min | 1,055,116 → all scored |
| Round 2: split + safety scoring (5 services) | ~63min | 1,055,116 → **50,000** (top25K+bottom25K) |
| Round 3: heavy-service scoring (7 services) | ~65min | 50,000 → Top 80 + Bottom 60 |
| Round 4: enumeration + constructs (5 services) | ~13min | → **150 constructs** |
| Round 5: 3D structure (OmegaFold) | ~210min | 150 → 150 OmegaFold PDBs |
| Round 6: PDB evaluation (SASA+A3D) | ~6min | 150 PDBs → 150 scored |
| Round 7: final output | ~1min | → 90 Top + 60 Bottom rankings |
| **Total** | **~6.5h** | **1,081,772 → 150 candidates** |

### Final Top 5

| Rank | Construct | Peptide | round6 | SASA | Agg | pLDDT |
|------|-----------|---------|--------|------|-----|-------|
| #1 | con_0215 | ERELPYYPGAHPMHPPK | 0.7794 | 0.8143 | 0.3515 | 0.4522 |
| #2 | con_0199 | GTHWHPEHF | 0.7684 | 0.7996 | 0.3291 | 0.4460 |
| #3 | con_0226 | EPTMYGEILSPNYPQAYPSEV | 0.7345 | 0.7697 | 0.3488 | 0.4398 |
| #4 | con_0201 | GTHWHPEHF (Both) | 0.7224 | 0.7633 | 0.3564 | 0.4369 |
| #5 | con_0095 | PAFELHYPHMVER | 0.7142 | 0.7212 | 0.3318 | 0.4364 |

---

## 2. The Reasoning Behind It

### Why rerun stages2?

The original stages2 (`output/`) had design flaws: inconsistent file names, checkpoint/resume behavior, and concurrency control across scripts, plus underestimated resource cost for some services (such as ToxinPred3). Rather than patch the original scripts, we created a fresh `output2/` directory and reran everything completely, while introducing `common.py` for shared utility functions.

### Why dual-channel?

We not only wanted to find "the peptides with the best antioxidant capacity", but also needed to test those **peptides with poor antioxidant capacity that still pass the other safety metrics** as negative controls. We therefore designed Top/Bottom dual channels running in parallel through the entire pipeline, with the two sides ranked independently.

### Why not run ToxinPred3 in Round 1?

The original plan was to run ToxinPred3 on 1.05 million sequences, but sklearn ExtraTrees is a single-threaded CPU-intensive task estimated at ~22h. We changed it to run in Round 2 on a 50K subset, which needs only ~48min — reasonable.

### Why did Round 2 split by pure AnOxPePred rather than a weighted score?

Earlier pipelines split by a weighted composite score, but different services have different scales and discriminative power, and blending early masks the quality of antioxidant capacity itself. We switched to splitting by **pure AnOxPePred (a direct measurement of antioxidant activity)**, then ran the safety services only on the selected 25K+25K.

### Why use only OmegaFold in Round 5, not ESMFold?

Test data showed that ESMFold's pLDDT on silk fusion proteins (repetitive sequences) is generally <0.30 — too low in confidence to be of any reference value for downstream SASA/A3D evaluation. OmegaFold's mean pLDDT was 0.41, and it handles repetitive sequences better. In the end we changed from running both services in parallel to OmegaFold only, saving ~50% of GPU time.

### Why remove the construct_composite weight in Round 6?

See the weight settings in Section 3.

---

## 3. Weight Settings

### Round 1 weights (scoring only, no split)

| Service | Weight | Reason |
|------|------|------|
| AnOxPePred | 0.50 | directly measures antioxidant activity, core metric |
| AlgPred2 | 0.10 | allergenicity screening, low weight |

ToxinPred3 was deferred to Round 2.

### Round 2-3 composite score

| Service | Weight | Reason |
|------|------|------|
| AnOxPePred | 0.45 | core antioxidant metric, highest weight |
| ToxinPred3 | 0.13 | toxicity filtering, high-risk veto item |
| AlgPred2 | 0.09 | allergenicity screening |
| HemoPI2 | 0.09 | hemolysis |
| MHCflurry | 0.05 | immunogenicity |
| BepiPred3 | 0.10 | B-cell epitope |
| TemStaPro | 0.09 | thermal stability |

### Round 4 Construct composite score

| Service | Weight | Reason |
|------|------|------|
| Peptide weighted | 0.40 | peptide-level composite score (contains information from 7 services) |
| SoDoPE | 0.25 | physicochemical properties |
| construct_AnOxPePred | 0.20 | antioxidant in the full-length context |
| construct_BepiPred3 | 0.10 | full-length B-cell epitope |
| TemStaPro | 0.05 | thermal stability |

### Round 6 composite score (final scoring formula)

| Service | Weight | Reason |
|------|------|------|
| SASA | 0.40 | degree to which the peptide is exposed on the protein surface; higher is better |
| (1 - Aggrescan3D) | 0.40 | aggregation risk inverted; a lower-is-better metric becomes higher-is-better |
| pLDDT_norm | 0.20 | normalized structural confidence, used as quality control |

**Note**: construct_composite used to carry a weight of 0.50, but within the Top 90 these values were highly concentrated (P25-P75 spread only 0.011), so with that weight it essentially determined the ranking and diluted SASA and Aggrescan3D into meaninglessness. **We therefore removed construct_composite, letting the 3D-level evaluation truly determine the final ranking.**

---

## 4. Top N Selection

| Stage | Count selected | Basis |
|------|---------|------|
| Round 2 split | Top 25,000 + Bottom 25,000 | 25K is enough to cover the diversity of high-scoring peptides while keeping downstream service runtime acceptable |
| Round 3 Top channel | the first 80 constructs | 80 covers combinations across peptide sequences and positions; too few would lose diversity |
| Round 3 Bottom channel | 10 peptides × 2 linkers | enough as negative controls; no need for many |
| Round 4 enumeration | 30 peptides × 3 positions (Top) + 10 peptides × 2 linkers × 3 positions (Bottom) | the combination of 3 positions (N/C/Both) × 2 linkers per peptide is sufficient |
| **Final output** | **Top 90 + Bottom 60** | full output; recommend selecting Top 5-10 for wet-lab validation |

---

## 5. Data Volume Trends

```
1,081,772  ┐
           │ Step 0 (cleaning and deduplication)
1,055,116  ┘
           │ Round 1 (full scoring)
1,055,116  ┘
           │ Round 2 (dual-channel split)
    50,000 ┘  ┌─ Top 25,000 (best antioxidant capacity)
              └─ Bottom 25,000 (worst antioxidant capacity)
           │ Round 3 (heavy-service scoring + TemStaPro top 30% pre-screen)
    ~150   ┘  ┌─ Top 80 peptides → enumeration → 90 constructs
              └─ Bottom 10 peptides → enumeration → 60 constructs
           │ Round 5 (3D)
     150   ┘
           │ Round 6-7 (evaluation + ranking)
     150   ┘  ┌─ Top 90 constructs
              └─ Bottom 60 constructs
```

Screening funnel: **1,081,772 → 150**, elimination rate **99.986%**.

### Key Data Characteristics

| Dimension | Mean | Range |
|------|------|------|
| Top channel construct_composite | 0.5285 | 0.5097–0.5482 (spread only 0.039) |
| SASA score | 0.702 | 0.501–0.831 |
| Aggrescan3D risk | 0.348 | 0.289–0.398 |
| OmegaFold pLDDT | 0.4105 | 0.3666–0.4547 |
| Round6 final score | 0.642 | 0.523–0.779 |

---

## 6. Changes in Information Flow

### Key v1 → v2 changes

| Change | v1 | v2 |
|------|----|----|
| Output directory | `output/` | `output2/` |
| Split criterion | weighted composite score | **pure AnOxPePred** |
| ToxinPred3 timing | Round 1 (1.05 million) | **Round 2 (50 thousand)** |
| Round 3 input | 10K (single channel) | **50K (dual channel)** |
| Round 4 BepiPred3 | all 300 constructs | **serial, concurrency 1** to fix timeouts |
| Round 5 services | ESMFold + OmegaFold | **OmegaFold only** |
| Round 6 weights | construct(0.50)+pLDDT(0.15)+SASA(0.20)+A3D(0.15) | **SASA(0.40)+A3D(0.40)+pLDDT(0.20)** |
| Utility functions | copy-pasted inside scripts | managed centrally in `common.py` |
| Exception handling | some missing `return_exceptions` | two-layer isolation (`safe_gather`) |
| Checkpoint/resume | none | `checkpoint.json` mechanism |
| Service concurrency | fixed `CONCURRENT_CHUNKS=10` | adjusted per service characteristics |

### The major course correction in Round 5

The initial design ran ESMFold + OmegaFold in parallel, but actual runs revealed:
1. ESMFold's pLDDT on silk fusion proteins was extremely low (<0.30) and unreliable
2. ESMFold consumed 17GB of GPU memory, competing with OmegaFold for resources
3. After removing ESMFold, pure OmegaFold with concurrency 1 was actually more stable (OmegaFold's synchronous inference blocks the event loop and cannot truly run in parallel)

---

## 7. User Feedback

### Key decision points

| Feedback | Impact |
|------|------|
| "BepiPred is too slow; run the fast one first and send the top 30% to BepiPred" | introduced the TemStaPro pre-screen, reducing BepiPred3's 50K input to 15K |
| "ESMFold is not very useful; I think we can run OmegaFold only" | Round 5 changed from two services to pure OmegaFold, saving ~50% GPU time |
| "See whether the construct scores can separate the candidates; if not, just ignore them" | removed construct_composite's 0.50 weight and switched to pure SASA+A3D ranking |
| "Mandatory use of Docker" | all services containerized, solving the environment drift of native execution |

### Core concerns of the user

1. **Efficiency first**: repeatedly asked to optimize execution order (TemStaPro pre-screen, dropping ESMFold)
2. **Data-driven decisions**: asked to look at data distributions before setting weights, rather than preset weighting
3. **Dual-channel compliance**: always attentive to both the Top and Bottom output sets

---

## 8. Technical Difficulties

### Concurrency and timeouts

| Problem | Root cause | Solution |
|------|------|------|
| BepiPred3 queue timeouts | the GPU service takes ~115s per request for a 50-seq batch; Semaphore=5 let queued requests exceed the 300s timeout | changed to Semaphore=1, timeout 600s |
| ToxinPred3 hangs | sklearn ExtraTrees is single-threaded; asyncio.wait_for cannot interrupt C extensions | batch_size ≤ 10 + socket timeout |
| OmegaFold blocks the event loop | synchronous PyTorch CUDA inference inside async def blocks uvicorn | client-side Semaphore=1 serialization |
| asyncio.gather cancels everything | one task's exception makes gather cancel the other tasks | `return_exceptions=True` + independent try/except per task |

### Intermittent Docker proxy hangs

**Problem**: when httpx accessed containers through docker-proxy (127.0.0.1:PORT), long-running requests intermittently hung. The server was processing the request, but the client never received the response.

**Diagnosis**: `ss -tnp | grep 8002` showed the connection established but no data transfer. curl inside the container worked fine; 127.0.0.1 on the host hung.

**Solution**: use `docker inspect` to get the container's bridge IP (172.18.0.x) and connect directly, bypassing docker-proxy. Injected via the `{SERVICE}_HOST` environment variable.

### GPU memory contention

Running multiple GPU services simultaneously (ESMFold 17GB + BepiPred3 6GB + OmegaFold 11GB) exceeded the 48GB memory limit. Solutions:
- on-demand startup: only start the services needed by the current stage
- AnOxPePred's PyTorch CUDA cache held 34GB of GPU memory and had to be stopped to release it
- ESMFold's `.cuda()` hangs silently (rather than throwing) when memory is insufficient

---

## 9. Docker Issue Fixes

### Docker Hub unreachable in China

| Problem | Impact | Solution |
|------|------|---------|
| `registry-1.docker.io` timeouts | all Docker builds failed | configured the Daocloud mirror accelerator (`docker.m.daocloud.io`) |
| `continuumio/miniconda2` 403 forbidden | Aggrescan3D could not be built | switched to `ghcr.io/mamba-org/micromamba` (GitHub Container Registry, reachable in China) |
| `python:2.7-slim` repository archived | Debian Buster apt sources returned 404 | used a `micromamba`-based image (manages the Python environment automatically) |
| `mambaorg/micromamba` not on the allowlist | the Daocloud mirror refused it | pulled directly from `ghcr.io/mamba-org/micromamba` |

### Final Docker service list

A total of 12 microservice Docker images were built and run:

| Service | Port | Type | Notes |
|------|------|------|------|
| anoxpepred | 8001 | CPU | antioxidant prediction |
| bepipred3 | 8002 | GPU | B-cell epitope prediction |
| toxinpred3 | 8003 | CPU | toxicity prediction |
| hemopi2 | 8004 | CPU | hemolysis prediction |
| algpred2 | 8005 | CPU | allergenicity prediction |
| mhcflurry | 8006 | CPU | MHC binding prediction |
| temstapro | 8007 | CPU | thermal stability prediction |
| sodope | 8008 | CPU | physicochemical properties |
| omegafold | 8204 | GPU | 3D structure prediction |
| esmfold | 8203 | GPU | 3D structure prediction (not used in the final results) |
| sasa | 8101 | CPU | solvent-accessible surface area |
| aggrescan3d | 8102 | CPU | aggregation propensity |

### Key lessons

1. **Docker builds must be run from the tools/ directory** (`cd tools && docker compose ...`), otherwise the compose configuration cannot be found
2. **GPU services must be started on demand**; starting all 4 GPU services at once overflows GPU memory
3. **Direct Docker bridge IP connections** are more reliable than localhost port mapping, especially for long-running requests
4. **Mirror accelerators have limits**: the Daocloud mirror has an allowlist, and images not on it must be pulled from GHCR or another source
5. **Python 2.7 conda packages** are the biggest obstacle to compatibility in modern Docker environments; `micromamba` is the lightest-weight solution

---

*Generated by Claude Code — iGEM-silk pipeline review*
