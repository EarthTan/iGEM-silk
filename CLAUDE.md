# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

iGEM-silk is a computational platform for designing silk fibroin fusion proteins with functional peptides. The platform integrates 16 specialized microservices (ML predictors, structure tools, and a remote API proxy) to evaluate peptide candidates.

**Pipeline evolution**:
- `main/stages/` — First attempt (1843 peptides, 7 stages, all written but not all run). See `main/PLAN.md`.
- `main/stages2/` — **Production pipeline (completed)**. Rounds 0-7 executed, 1,055,116 → 90 candidates. Runs standalone via `python -m main.stages2.roundXX_*`. Output in `output/`.
- `main/stages3/` — **Next-generation design (planned)**. Billion-scale expansion using CD-HIT, DuckDB, variance-aware weighting. 5 planning documents written. Output will be `output3/`.

**Who this is for**: synthetic biology researchers at the iGEM competition.

## Production pipeline (stages2)

The completed production pipeline in `main/stages2/` processes 1M+ antioxidant peptides through 8 rounds:

| Round | Script | Purpose | Input→Output | Time |
|-------|--------|---------|-------------|------|
| 0 | `step00_integrate.py` | Data cleaning, 3-30aa filter, dedup, is_antioxidant=1 | 1,081,772→1,055,116 | ~30s |
| 1 | `round01_lightweight.py` | AnOxPePred(w=0.50)+AlgPred2(w=0.10), TOP_N=50000→100K | 1,055,116→100,000 | ~347s |
| 2 | `round02_scoring.py` | Add ToxinPred3(0.15)+HemoPI2(0.10)+MHCflurry(0.05) | 100,000→10,000 | ~75s |
| 3 | `round03_heavy.py` | Add BepiPred3(0.07)+TemStaPro(0.09), anoxpepred>0.5 filter | 10,000→80 | ~5min |
| 4 | `round04_enumerate.py` | 40 peptides×2 linkers×3 positions=240, SoDoPE+TemStaPro sort | 80→90 constructs | ~1s |
| 5 | `round05_3d.py` | ESMFold+OmegaFold 3D prediction, OMEGAFOLD_CONCURRENCY=1 | 90→90 PDBs | ~18min |
| 6 | `round06_pdb_eval.py` | SASA+Aggrescan3D evaluation, composite scoring | 90→90 scored | ~199s |
| 7 | `round07_final.py` | Final output package, SASA ranking, per-construct folders | 90→final report | ~1s |

**Key scoring weights used in stages2**:
- Round 1: AnOxPePred(0.50), AlgPred2(0.10)
- Round 2: AnOxPePred(0.50), AlgPred2(0.10), ToxinPred3(0.15), HemoPI2(0.10), MHCflurry(0.05)
- Round 3: AnOxPePred(0.50), BepiPred3(0.07), TemStaPro(0.09), AlgPred2(0.07), ToxinPred3(0.11), HemoPI2(0.07), MHCflurry(0.04)
- Round 4 composite: 0.65×peptide_score + 0.30×SoDoPE + 0.10×TemStaPro
- Round 6 composite: 0.50×construct_score + 0.15×pLDDT_norm + 0.20×SASA + 0.15×Aggrescan3D

## Critical technical lessons (from stages2 production)

These are hard-won. Violating them caused failures in stages2.

**Docker mandatory**: All microservices MUST run in Docker for production. Running `python service.py` on the host causes environment drift, missing models, and wasted debugging. Documented in `main/stages3/TECH_REQUIREMENTS.md`.

**按需启动原则（stages3）**: 每个 stage 只启动该阶段实际依赖的微服务，不提前启动不需要的服务。Docker Compose 的 `--profile` 机制天然支持这种模式。例如 Stage 1 只需 `--profile cpu`（anoxpepred + algpred2），Stage 4 才需 `--profile gpu`（omegafold）。不要一次性启动全部 16 个服务，避免 GPU 显存竞争和资源浪费。在启动任何 stage 前先执行 health check 确认依赖服务就绪。

**OmegaFold blocks the event loop**: OmegaFold's `self.model(input_data)` is a synchronous PyTorch CUDA call (90-120s) inside an `async def`. This blocks uvicorn's event loop. Client-side fix: `asyncio.Semaphore(1)` to serialize requests. Server-side fix pending: move inference to `run_in_executor`. See `.agents/learnings/gep-omegafold-sync-inference-blocking.md`.

**Docker bridge IP, not 127.0.0.1**: Accessing containers via `127.0.0.1:PORT` (docker-proxy) causes intermittent httpx keep-alive hangs. Use `docker inspect` to get bridge IP and connect directly. Implemented in round05_3d.py `_fix_omegafold_docker_network()`. See `.agents/learnings/gep-docker-container-bridge-ip.md`.

**asyncio.gather exception safety**: `asyncio.gather(*tasks)` without `return_exceptions=True` cancels ALL tasks when one fails. Always use `return_exceptions=True` + per-task try/except for batch processing. See `.agents/learnings/gep-asyncio-gather-exception-safety.md`.

**ToxinPred3 single-threaded**: sklearn ExtraTreesClassifier hangs under concurrent requests. Use `batch_size <= 10` and socket-level timeout (not `asyncio.wait_for` which can't interrupt C extensions). See `.agents/learnings/gep-toxinpred3-concurrency-limit.md`.

**SASA batch API format**: Batch endpoint returns `score` at the top level of each result item, NOT nested under `result.score`. Single API has `result.score`. Watch for this inconsistency.

## Commands

```bash
# Install deps
uv sync                      # root project
cd tools/<name> && uv sync   # single microservice

# Lint
uv run ruff check .

# Run tests (pytest configured in pyproject.toml)
uv run pytest

# Start all microservices (Docker, from tools/)
cd tools && docker compose --profile gpu --profile cpu up -d

# Start a single service locally (for development — NOT for production)
cd tools/<name> && uv run python service.py

# Run a production pipeline stage
uv run python -m main.stages2.round03_heavy       # stages2 round 3
uv run python -m main.stages2.round05_3d           # stages2 round 5

# Run the old first-pipeline stage
uv run python -m main.stages.stage01_filter        # first pipeline stage 1

# Test all microservices
cd tools && python test_all_services.py

# Override any microservice host/port at runtime
export ANOXPEPRED_HOST=192.168.1.100
export ANOXPEPRED_PORT=8001

# Single microservice health check
python -c "from main.client import ServiceClient; import asyncio; print(asyncio.run(ServiceClient().check_health()))"
```

## Architecture

### Pipeline directories

| Directory | Status | Description |
|-----------|--------|-------------|
| `main/stages/` | **First pipeline** | 7 stages written, 1843 peptide input. `PLAN.md` has the original funnel philosophy. |
| `main/stages2/` | **Production pipeline (DONE)** | 8 rounds (0-7), 1M peptide input. All rounds completed with real results in `output/`. |
| `main/stages3/` | **Next-gen pipeline (PLANNED)** | Billion-scale expansion. 5 planning documents: `PLAN.md`, `TECH_REQUIREMENTS.md`, `DATA_PREP.md`, `DB_SCHEMA.md`, `ARCHITECTURE.md`. |

### Core modules (shared across all pipelines)

| File | Purpose |
|------|---------|
| `main/config.py` | `SERVICES` dict (16 microservice URLs, 4 groups: score/filter/structure/pdb_score) + `service_url()` helper with env var override |
| `main/client.py` | Async httpx client. `predict_single()`, `predict_batch()`, `predict_pdb_single()`, `predict_pdb_batch()`, `evaluate_peptides()` for concurrent multi-service eval, `predict_structure_async()` for async job polling, `check_health()` |
| `main/data_loader.py` | FASTA and CSV parsing functions (`load_scaffold()`, `load_linkers()`, `load_function_peptides()`) |

### Microservices (`tools/`)

16 FastAPI services, each with its own `.venv` and Dockerfile. Three templates in `tools/template/`:

| Template | Base class | Pattern | Used by |
|----------|-----------|---------|---------|
| `fasta_service.py` | `FastaToolService` | sequence → score | AnOxPePred, BepiPred-3.0, ToxinPred3, HemoPI2, MHCflurry, pLM4CPPs, TIPred, AlgPred2, GraphCPP, TemStaPro, SoDoPE |
| `structure_service.py` | `StructureService` | sequence → PDB/mmCIF | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold |
| `pdb_service.py` | `PdbScoringService` | PDB → score | SASA, Aggrescan3D |

Supporting templates: `tools/template/logger.py` (rotating file logs to `tools/logs/`), `tools/template/job_manager.py` (async job persistence), `tools/utils.py` (GPU detection via `detect_gpu()`).

### Service groups and port assignments

| Group | Port range | Services |
|-------|-----------|----------|
| `score` | 8001–8012 | AnOxPePred, BepiPred-3.0, MHCflurry, pLM4CPPs, TIPred, GraphCPP, TemStaPro, SoDoPE |
| `filter` | 8003–8008 | ToxinPred3, HemoPI2, AlgPred2 |
| `structure` | 8201–8205 | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold, Waveflow |
| `pdb_score` | 8101–8102 | SASA, Aggrescan3D |

### Pipeline state management (output/ directory)

```
output/
├── STATUS.md              ← Always-current progress pointer
├── REVIEW.md              ← Comprehensive post-mortem of stages2 production run
├── round01_lightweight/   ← Per-round output from stages2
├── round02_scoring/
├── ...
├── round07_final/         ← Final deliverable: 90 constructs, rankings, README
└── stage01_filter/        ← First pipeline (stages/) output
```

Each round directory has: `README.md` (report), `run.log`, `final/` (passed/top candidates). The round07_final directory has the complete output package.

### New pipeline (stages3) design docs

Five planning documents in `main/stages3/`:

| Document | Covers |
|----------|--------|
| `PLAN.md` | Overall roadmap, variance-aware weighting philosophy, 6-stage funnel, timeline |
| `TECH_REQUIREMENTS.md` | Docker mandatory enforcement, 5 microservice bugs to fix, concurrency specs, network stability, storage |
| `DATA_PREP.md` | CD-HIT clustering strategy for 8.5B sequences, 3-30aa filter, parallel FASTA processing |
| `DB_SCHEMA.md` | DuckDB design: 15 tables, checkpoint/resume, distribution statistics for variance weights |
| `ARCHITECTURE.md` | Three-layer architecture (orchestration/execution/service), error isolation, memory management |

### Model file management

Models live in `tools/<name>/models/` (`.gitignore`d except small files). Shared cross-service cache at `tools/models/fair-esm/` (ESM-2 checkpoints via `torch.hub`) for pLM4CPPs, BepiPred-3.0, and ESMFold.

Five sourcing strategies: git-tracked (< 50MB), first-run auto-download (> 10MB), pip package, pure algorithm (no model), Docker built-in.

## Data directory

`data/` contains input files: `silk.fasta` (scaffold, ~346 aa), `linker.fasta` (10 linkers), `function.csv` (~25K entries), `function_3.csv` (subset).

## Learning resources

- `.agents/learnings/` — GEP capsules (troubleshooting knowledge base). Indexed in `MEMORY.md`.
- `main/stages3/TECH_REQUIREMENTS.md` — Technical mandates drawn from stages2 failures.
- `main/docs/threshold.md` — Hard filter thresholds (ToxinPred3 ≥0.38, AlgPred2 ≥0.30, HemoPI2 ≥0.55).
- `main/docs/penalty.md` — Scoring formula documentation.
- `docs/HUMAN.md` — Human-operated analysis methods (Binding ddG, GROMACS MD).
- `references/` — Academic papers.

## Python environment

- Root project uses `uv` with `pyproject.toml`. Virtual env at `./venv`.
- Each microservice has its own `.venv` under `tools/<name>/.venv`.
- Never use `pip` or `requirements.txt` — use `uv add` / `uv sync`.
- Minimum Python 3.11. All Python code should use `from __future__ import annotations`.

## Docker deployment

```bash
cd tools
docker compose --profile gpu up -d --build   # CUDA services
docker compose --profile cpu up -d --build   # CPU services
docker compose --profile gpu --profile cpu up -d  # all services
```

Known pitfalls (detailed in `.agents/learnings/docker/`): Docker Hub unreachable in China (use DaoCloud mirror), pin image versions, `python:slim` needs C build deps, namespace shadowing from `tools/` subdirectory, Compose atomic build rollbacks.
