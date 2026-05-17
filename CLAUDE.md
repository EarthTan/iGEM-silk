# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

iGEM-silk is a computational platform for designing silk fibroin fusion proteins with functional peptides. The platform integrates 16 specialized microservices (ML predictors, structure tools, and a remote API proxy) to evaluate peptide candidates.

**Pipeline evolution**:
- `main/stages/` — First attempt (1843 peptides, 7 stages, all written but not all run). See `main/PLAN.md`.
- `main/stages2/` — **Production pipeline (completed)**. Rounds 0-7 executed, 1,055,116 → 90 candidates. Runs standalone via `python -m main.stages2.roundXX_*`. Output in `output/`.
- `main/stages3/` — **Next-generation pipeline (in development)**. Billion-scale expansion using CD-HIT, DuckDB, variance-aware weighting. Now contains actual code: `stage00_preprocess.py`, `stage01_lightweight.py`, `cdhit_wrapper.py`, `db.py`, `docker_utils.py`, `analytics.py`. Output goes to `output3/`.

**Who this is for**: synthetic biology researchers at the iGEM competition.

**Critical companion file**: Read `AGENTS.md` for production safety rules before running git operations on this machine. It contains absolute prohibitions on `git clean`, `git checkout -- .`, and `git reset --hard` — violations have destroyed 6GB+ of models and irrecoverable output data.

## Production pipeline (stages2)

The `main/stages2/` pipeline (v2, in progress) processes 1M+ antioxidant peptides through 8 rounds:

| Round | Script | Purpose | Input→Output | Time |
|-------|--------|---------|-------------|------|
| 0 | `step00_integrate.py` | Data cleaning, 3-30aa filter, dedup | 1,081,772→1,055,116 | ~30s |
| 1 | `round01_lightweight.py` | **AnOxPePred(0.50)+AlgPred2(0.10) only** (无 ToxinPred3) | 1,055,116→全量评分 | ~15min |
| 2 | `round02_scoring.py` | **按纯 anoxpepred 分选 top25K+bottom25K** + ToxinPred3/HemoPI2/MHCflurry | 50K 含双通道标签 | ~63min |
| 3 | `round03_heavy.py` | BepiPred3+TemStaPro on **50K 双通道** | 50K→top N + bottom M | — |
| 4 | `round04_enumerate.py` | 双通道枚举 + construct 级 re-score | 肽→constructs | — |
| 5 | `round05_3d.py` | ESMFold+OmegaFold 3D prediction | constructs→PDBs | — |
| 6 | `round06_pdb_eval.py` | SASA+Aggrescan3D evaluation | PDB→scores | — |
| 7 | `round07_final.py` | Final dual-channel output, two rankings | →top+bottom reports | — |

**Key differences from v1 (original stages2)**:
- Round 1: 不跑 ToxinPred3（105 万条太慢），只跑 AnOxPePred+AlgPred2
- Round 2: **按纯 anoxpepred 分选** top25K+bottom25K，补跑 ToxinPred3+安全服务
- Round 3: 输入从 10K 扩展为 **50K 双通道**（top25K+bottom25K）
- All downstream rounds: channel 标签贯穿，双通道各自输出

**Key scoring weights used in stages2 (v2)**:
- Round 1: AnOxPePred(0.50), AlgPred2(0.10) — 仅评分，不分选
- Round 2 onward composite: **AnOxPePred(0.50) + ToxinPred3(0.15) + AlgPred2(0.10) + HemoPI2(0.10) + MHCflurry(0.05)**
- Round 4 composite: 0.40×peptide_score + 0.25×SoDoPE + 0.20×construct_AnOxPePred + 0.10×construct_BepiPred + 0.05×TemStaPro
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

# Add a dependency
uv add <package>             # root project
cd tools/<name> && uv add <package>  # single microservice

# Lint & format
uv run ruff check .          # lint
uv run ruff format . --check  # check formatting
uv run ruff format .          # auto-format

# Run tests (pytest configured in pyproject.toml)
uv run pytest
uv run pytest tests/test_file.py -v  # single test file

# Type check
uv run mypy .

# Start all microservices (Docker, from tools/)
cd tools && docker compose --profile gpu --profile cpu up -d

# Rebuild and start a single service
docker compose build <service_name> && docker compose up -d <service_name>

# View service logs
docker compose logs -f <service_name>

# Start a single service locally (for development — NOT for production)
cd tools/<name> && uv run python service.py

# Run a production pipeline stage
uv run python -m main.stages2.round03_heavy       # stages2 round 3
uv run python -m main.stages2.round05_3d           # stages2 round 5

# Run stages3 pipeline stage
uv run python -m main.stages3.stage00_preprocess
uv run python -m main.stages3.stage01_lightweight

# Run the old first-pipeline stage
uv run python -m main.stages.stage01_filter        # first pipeline stage 1

# Test all microservices
cd tools && python test_all_services.py

# Override any microservice host/port at runtime
export ANOXPEPRED_HOST=192.168.1.100
export ANOXPEPRED_PORT=8001

# Single microservice health check
python -c "from main.client import ServiceClient; import asyncio; print(asyncio.run(ServiceClient().check_health()))"

# Check service health via HTTP directly
curl http://127.0.0.1:8001/health
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
| `main/__main__.py` | Entry point (currently raises NotImplementedError — use `python -m main.stages2.roundXX_*` instead) |

### Service templates (`tools/template/`)

When adding a new microservice, start from one of three templates:

| Template | Base class | Pattern | Used by |
|----------|-----------|---------|---------|
| `fasta_service.py` | `FastaToolService` | sequence → score | AnOxPePred, BepiPred-3.0, ToxinPred3, HemoPI2, MHCflurry, pLM4CPPs, TIPred, AlgPred2, GraphCPP, TemStaPro, SoDoPE |
| `structure_service.py` | `StructureService` | sequence → PDB/mmCIF | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold |
| `pdb_service.py` | `PdbScoringService` | PDB → score | SASA, Aggrescan3D |

Supporting templates: `tools/template/logger.py` (rotating file logs to `tools/logs/`), `tools/template/job_manager.py` (async job persistence), `tools/utils.py` (GPU detection via `detect_gpu()`).

A new microservice needs: a `tools/<name>/` directory with `pyproject.toml`, `service.py`, `Dockerfile`, `.dockerignore`, and a `.venv` (via `uv sync`). Then register it in `tools/docker-compose.yml` and `main/config.py`.

### Pipeline state management

| Group | Port range | Services |
|-------|-----------|----------|
| `score` | 8001–8012 | AnOxPePred, BepiPred-3.0, MHCflurry, pLM4CPPs, TIPred, GraphCPP, TemStaPro, SoDoPE |
| `filter` | 8003–8008 | ToxinPred3, HemoPI2, AlgPred2 |
| `structure` | 8201–8205 | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold, Waveflow |
| `pdb_score` | 8101–8102 | SASA, Aggrescan3D |

### Pipeline state management (output/ and output2/ directories)

```
output2/                          ← Active v2 pipeline (in progress)
├── STATUS.md                     ← Current progress pointer
├── round01_lightweight/
├── round02_scoring/
└── ...                           ← v2 pipeline output

output/                           ← Completed v1 pipeline (archived)
├── STATUS.md
├── REVIEW.md                     ← Post-mortem of stages2 v1
├── round01_lightweight/
├── ...
└── round07_final/                ← v1 final output

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

## Knowledge base

- **`AGENTS.md`** — Critical production safety rules. Read before any git operations. Absolute prohibitions on `git clean`, `git checkout -- .`, `git reset --hard` (real incident: 6GB+ models destroyed).
- **`.agents/learnings/MEMORY.md`** — Indexed GEP capsules (troubleshooting knowledge base). Key entries: Docker bridge IP issues, OmegaFold blocking, asyncio.gather safety, ToxinPred3 concurrency, ESMFold build, GPU contention.
- **`.agents/learnings/docker/`** — Docker-specific pitfalls (China mirror, slim image build deps, compose atomicity, namespace shadowing).
- **`main/docs/threshold.md`** — Hard filter thresholds (ToxinPred3 ≥0.38, AlgPred2 ≥0.30, HemoPI2 ≥0.55).
- **`main/docs/penalty.md`** — Scoring formula documentation.
- **`docs/HUMAN.md`** — Human-operated analysis methods (Binding ddG, GROMACS MD).
- **`references/`** — Academic papers.

## Memory system

This project has a persistent memory system at `/home/lenovo/.claude/projects/-home-lenovo-Projects-iGEM-silk/memory/`. Claude Code automatically learns from each session — preferences, user role, project context, feedback. To save or recall information across sessions, write to this directory. Index is in `MEMORY.md` within that directory.

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
