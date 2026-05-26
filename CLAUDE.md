# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

iGEM-silk is a computational platform for designing silk fibroin fusion proteins with functional peptides. The platform integrates 16 specialized microservices (ML predictors, structure tools, and a remote API proxy) to evaluate peptide candidates.

**Pipeline evolution**:
- `main/stages/` — First attempt (1843 peptides, 7 stages, all written but not all run). See `main/PLAN.md`.
- `main/stages2/` — **Production pipeline (completed)**. Full 8-round v2 run completed, 1,081,772 → 90 candidates. Output in `output2/`. REVIEW.md has full post-mortem.
- `main/stages3/` — **Next-generation pipeline (partially completed)**. Billion-scale DuckDB-based pipeline. Stage 0 complete (19.9M candidates), Stage 1 code ready. Output in `output3/`.
- `main/stages4/` — **Latest pipeline (completed)**. 19.9M → 250 constructs (Top 150 + Bottom 100) through 8 rounds plus AlphaFold3 refinement. Output in `output4/`. Fixes stages2 design flaws: no cross-attribute weighted averaging, safety hard thresholds.

**Who this is for**: synthetic biology researchers at the iGEM competition.

**Critical companion file**: Read `AGENTS.md` for production safety rules before running git operations on this machine. It contains absolute prohibitions on `git clean`, `git checkout -- .`, and `git reset --hard` — violations have destroyed 6GB+ of models and irrecoverable output data.

## Production pipeline (stages2) — v2 completed

The `main/stages2/` pipeline (v2) processed 1M+ antioxidant peptides through 8 rounds. All rounds completed with real results in `output2/`. See `output2/REVIEW.md` for the full post-mortem.

| Round | Script | Purpose | Input→Output | Time |
|-------|--------|---------|-------------|------|
| 0 | `step00_integrate.py` | Data cleaning, 3-30aa filter, dedup | 1,081,772→1,055,116 | ~30s |
| 1 | `round01_lightweight.py` | AnOxPePred(0.50)+AlgPred2(0.10) only (no ToxinPred3) | 1,055,116→full scores | ~15min |
| 2 | `round02_scoring.py` | Sort by pure AnOxPePred top25K+bottom25K + ToxinPred3/HemoPI2/MHCflurry | 50K with dual-channel labels | ~63min |
| 3 | `round03_heavy.py` | BepiPred3+TemStaPro on 50K dual-channel | 50K→Top 80 + Bottom 10 peptides | ~65min |
| 4 | `round04_enumerate.py` | Dual-channel enumeration + construct-level re-score | peptides→150 constructs | ~13min |
| 5 | `round05_3d.py` | OmegaFold 3D prediction only | constructs→150 PDBs | ~210min |
| 6 | `round06_pdb_eval.py` | SASA+Aggrescan3D evaluation | PDB→scores | ~6min |
| 7 | `round07_final.py` | Final dual-channel output, two rankings | →90 Top + 60 Bottom reports | ~1min |

**Total**: ~6.5h, 1,081,772 → 150 candidates, 99.986%淘汰率.

**Key v2 design decisions**:
- Round 1 skips ToxinPred3 (1M sequences would take ~22h), deferred to Round 2 on 50K subset
- Round 2 sorts by **pure AnOxPePred score** (not weighted composite) for dual-channel split
- Round 3 runs on full 50K with channel labels preserved
- Round 5 uses **OmegaFold only** (ESMFold pLDDT < 0.30 on silk repeats was unreliable)
- Entire flow dual-channel (Top/Bottom) with independent final rankings

**Actual scoring weights used in v2 (from REVIEW.md)**:
- Round 1: AnOxPePred(0.50), AlgPred2(0.10)
- Round 2-3 composite: **AnOxPePred(0.45) + ToxinPred3(0.13) + AlgPred2(0.09) + HemoPI2(0.09) + MHCflurry(0.05) + BepiPred3(0.10) + TemStaPro(0.09)**
- Round 4 construct composite: 0.40×peptide_weighted + 0.25×SoDoPE + 0.20×construct_AnOxPePred + 0.10×construct_BepiPred3 + 0.05×TemStaPro
- Round 6 final: **SASA(0.40) + (1-Aggrescan3D)(0.40) + pLDDT_norm(0.20)** — construct_composite was removed because its spread was only 0.011 in Top 90, diluting 3D signal

### Additional scripts in stages2/

| Script | Purpose |
|--------|---------|
| `round02_toxinpred3_serial.py`, `round02_toxinpred3_sync.py`, `round02_toxinpred3_robust.py` | ToxinPred3 concurrency experiments (single-threaded sklearn workaround) |
| `round02_recover_toxinpred3.py` | Recovery script for interrupted ToxinPred3 runs |
| `round04_fix_bepipred3.py` | BepiPred3 GPU timeout fix (Semaphore=1, timeout=600s) |
| `docker_utils.py` | Docker service management shared across rounds |
| `common.py` | Shared utility functions (safe_gather, ServiceClient pooling, etc.) |

## stages3 pipeline (in development)

Next-generation pipeline at `main/stages3/`. Uses DuckDB for state, variance-aware weighting, and Docker-on-demand service startup. Output in `output3/`.

**Current status**: Stage 0 complete (19.9M candidates), Stage 1 code written (AnOxPePred+AlgPred2 on 19.9M). Full details in `main/stages3/DONE.md` and `main/stages3/ARCHITECTURE_AS_BUILT.md`.

| File | Purpose |
|------|---------|
| `db.py` | DuckDB interface — schema, batch INSERT (20k/s via VALUES, NOT executemany), checkpoint/resume, distribution stats |
| `docker_utils.py` | On-demand Docker startup — per-step service launch, bridge IP detection, health check polling, idempotent cache |
| `service_map.py` | Service dependency map per step (step0-step6), actual docker-compose profiles |
| `analytics.py` | Variance-aware weighting engine — winsorized stddev → data-driven weights, full audit trail |
| `stage00_preprocess.py` | Stage 0: FASTA stream → 3-30aa filter → AA filter → DuckDB. Ran on UniProt (225M) + MGnify (624M) |
| `stage01_lightweight.py` | Stage 1: batch read 100k from DB → concurrent AnOxPePred+AlgPred2 → write scores → AlgPred2 hard filter |
| `fasta_parser.py` | Streaming FASTA reader for 100GB+ files |
| `cdhit_wrapper.py` | CD-HIT CLI wrapper (tested, then skipped — short peptides are too diverse for clustering) |
| `sample_fasta.py` | Reservoir sampling from FASTA |

**Key findings from Stage 0**:
- CD-HIT skipped: at -c 0.90, only 0.2-5% clustering rate on short peptides
- DuckDB executemany was 200 rows/s; raw INSERT VALUES batches achieve 20k rows/s (100x)
- Total candidates: 19,890,021 (UniProt 0.33% pass, MGnify 3.07% pass)
- DB size: 2.6 GB for 19.9M rows (~7.6M rows/GB)

**Design docs** in `plan/`: PLAN.md (roadmap), ARCHITECTURE.md (three-layer), DB_SCHEMA.md (15 tables), DATA_PREP.md, TECH_REQUIREMENTS.md.

## stages4 pipeline (completed)

The `main/stages4/` pipeline is the latest iteration, fixing two critical design flaws from stages2: (1) safety attributes were dilutable in weighted averages rather than being hard vetoes, and (2) antioxidant signal contaminated all downstream rounds. Stages4 enforces **hierarchical filtering**: each round uses a single criterion, safety is hard-threshold (pass/fail, no scoring), and antioxidant scores are used only in Round 1 for channel split.

**Design docs**: `main/stages4/PLAN.md` — full design rationale, comparison with stages2.

| Round | Script | Purpose | Status |
|-------|--------|---------|--------|
| 0 | `s4_round00_preprocess.py` | Import from stages3 DuckDB | ✅ complete |
| 1 | `s4_round01_antioxidant_split.py` | AnOxPePred → Top 10% + Bottom 1%, AlgPred2 hard filter | ✅ complete |
| 2 | `s4_round02_safety_screen.py` | ToxinPred3/HemoPI2/MHCflurry independent hard thresholds | ✅ complete |
| 3p1 | `s4_round03_precompute.py` | Pre-compute BepiPred3+TemStaPro+SoDoPE+pLM4CPPs | ✅ complete |
| 3p2 | `s4_round03_deep_scoring.py` | SD-driven weighted scoring (unique weighted position) | ✅ complete |
| 3p3 | `s4_round03_phase2_graphcpp.py` | GraphCPP post-scoring on reduced set | ✅ complete |
| 4p1 | `s4_round04_enumerate.py` | Construct enumeration + SoDoPE/TemStaPro | ✅ complete |
| 4p2 | `s4_round04_phase2_bepipred3.py` | BepiPred3 on constructs | ✅ complete |
| 5 | `s4_round05_3d.py` | OmegaFold 3D prediction (253 constructs, ~6h) | ✅ complete |
| 6 | `s4_round06_pdb_eval.py` | SASA + Aggrescan3D evaluation | ✅ complete |
| 7 | `s4_round07_final.py` | Dual-channel ranking (250 → Top 150 + Bottom 100) | ✅ complete |
| 8 | `s4_round08_af3.py` | AlphaFold3 on Top 10 + Bottom 10 | 📝 written |

**Key design changes from stages2**:
- **Safety is a veto, not a score**: ToxinPred3/HemoPI2/MHCflurry have hard thresholds in Round 2. Fail any one → eliminated. No weighting, no compensation.
- **Antioxidant used once**: AnOxPePred only in Round 1 for channel split. Never again in downstream scoring.
- **SD-driven weights (Round 3 only)**: Base weight = winsorized stddev / total stddev. Manual coefficient α for domain knowledge tuning. Only place in the pipeline where weighted averaging occurs.
- **DuckDB state**: Uses its own `s4_db.py` (based on stages3's `db.py`) with schema tailored for stages4 rounds.

**Output**: `output4/` — 2.7GB `pipeline.db`, 253 PDBs, final ranking reports, construct-level JSON with full score provenance per round.

**Total runtime (estimated)**: ~8-10h for 19.9M → 250 constructs. Critical path: Round 3 GPU services (~2h), Round 4 enumeration (~1h), Round 5 OmegaFold (~6h).

## Critical technical lessons

These are hard-won from stages2 production.

**Docker mandatory**: All microservices MUST run in Docker for production. Running `python service.py` on the host causes environment drift, missing models, and wasted debugging. See `main/stages3/TECH_REQUIREMENTS.md`.

**按需启动原则（stages3）**: 每个 stage 只启动该阶段实际依赖的微服务，不提前启动不需要的服务。Docker Compose 的 `--profile` 机制天然支持这种模式。不要一次性启动全部 16 个服务，避免 GPU 显存竞争和资源浪费。在启动任何 stage 前先执行 health check 确认依赖服务就绪。

**OmegaFold blocks the event loop**: OmegaFold's `self.model(input_data)` is a synchronous PyTorch CUDA call (90-120s) inside an `async def`. This blocks uvicorn's event loop. Client-side fix: `asyncio.Semaphore(1)` to serialize requests. See `.agents/learnings/gep-omegafold-sync-inference-blocking.md`.

**Docker bridge IP, not 127.0.0.1**: Accessing containers via `127.0.0.1:PORT` (docker-proxy) causes intermittent httpx keep-alive hangs. Use `docker inspect` to get bridge IP and connect directly. Implemented in round05_3d.py `_fix_omegafold_docker_network()`. See `.agents/learnings/gep-docker-container-bridge-ip.md`.

**asyncio.gather exception safety**: `asyncio.gather(*tasks)` without `return_exceptions=True` cancels ALL tasks when one fails. Always use `return_exceptions=True` + per-task try/except for batch processing. See `.agents/learnings/gep-asyncio-gather-exception-safety.md`.

**ToxinPred3 single-threaded**: sklearn ExtraTreesClassifier hangs under concurrent requests. Use `batch_size <= 10` and socket-level timeout (not `asyncio.wait_for` which can't interrupt C extensions). See `.agents/learnings/gep-toxinpred3-concurrency-limit.md`.

**SASA batch API format**: Batch endpoint returns `score` at the top level of each result item, NOT nested under `result.score`. Single API has `result.score`. Watch for this inconsistency.

**BepiPred3 GPU timeout**: GPU service ~115s per 50-seq batch with Semaphore=5 caused queued requests to exceed 300s timeout. Fix: Semaphore=1, timeout=600s. See `.agents/learnings/gep-bepipred3-gpu-timeout-tuning.md`.

**ESMFold on silk repeats**: ESMFold pLDDT < 0.30 on silk fusion proteins — unreliable for downstream SASA/A3D. OmegaFold pLDDT ~0.41 is usable. See `.agents/learnings/gep-pipeline-confidence-cascade.md`.

**PyTorch CUDA cache persistence**: Process exit leaves 34GB CUDA context allocated. `docker stop` doesn't release GPU memory. Only `kill -9` or full container teardown works. Justification for on-demand GPU service startup. See `.agents/learnings/gep-pytorch-cuda-cache-gpu-memory-leak.md`.

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

# Run stages4 pipeline round
uv run python -m main.stages4.s4_round01_antioxidant_split
uv run python -m main.stages4.s4_round05_3d
uv run python -m main.stages4.s4_round08_af3          # AlphaFold3 refinement

# Open stages4 DuckDB shell (for inspection)
uv run python -c "import duckdb; duckdb.connect('output4/pipeline.db')"

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
| `main/stages2/` | **Production pipeline (DONE)** | 8 rounds (0-7), 1M peptide input. All rounds completed with results in `output2/`. `output2/REVIEW.md` has full analysis. |
| `main/stages3/` | **Next-gen pipeline (PAUSED)** | Stage 0 complete (19.9M candidates). Stage 1 code ready. 5 planning docs + as-built doc. Superseded by stages4. |
| `main/stages4/` | **Latest pipeline (DONE)** | 8 rounds (0-7) + AF3 round 8. 19.9M → 250 constructs. Results in `output4/`. Hierarchical filtering, safety hard thresholds, SD-driven weights. |

### Core modules (shared across all pipelines)

| File | Purpose |
|------|---------|
| `main/config.py` | `SERVICES` dict (16 microservice URLs, 4 groups: score/filter/structure/pdb_score) + `service_url()` helper with env var override |
| `main/client.py` | Async httpx client. `predict_single()`, `predict_batch()`, `predict_pdb_single()`, `predict_pdb_batch()`, `evaluate_peptides()` for concurrent multi-service eval, `predict_structure_async()` for async job polling, `check_health()` |
| `main/data_loader.py` | FASTA and CSV parsing functions (`load_scaffold()`, `load_linkers()`, `load_function_peptides()`) |
| `main/__main__.py` | Entry point (currently raises NotImplementedError — use `python -m main.stages2.roundXX_*` instead) |
| `main/stages4/s4_db.py` | stages4 DuckDB interface (44K, 30+ tables, checkpoint/resume, schema per round) |
| `main/stages4/s4_analytics.py` | Variance-aware weighting engine (winsorized stddev → data-driven weights) |

### Service templates (`tools/template/`)

When adding a new microservice, start from one of three templates:

| Template | Base class | Pattern | Used by |
|----------|-----------|---------|---------|
| `fasta_service.py` | `FastaToolService` | sequence → score | AnOxPePred, BepiPred-3.0, ToxinPred3, HemoPI2, MHCflurry, pLM4CPPs, TIPred, AlgPred2, GraphCPP, TemStaPro, SoDoPE |
| `structure_service.py` | `StructureService` | sequence → PDB/mmCIF | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold |
| `pdb_service.py` | `PdbScoringService` | PDB → score | SASA, Aggrescan3D |

Supporting templates: `tools/template/logger.py` (rotating file logs to `tools/logs/`), `tools/template/job_manager.py` (async job persistence), `tools/utils.py` (GPU detection via `detect_gpu()`).

A new microservice needs: a `tools/<name>/` directory with `pyproject.toml`, `service.py`, `Dockerfile`, `.dockerignore`, and a `.venv` (via `uv sync`). Then register it in `tools/docker-compose.yml` and `main/config.py`.

### Service ports and groups

| Group | Port range | Services |
|-------|-----------|----------|
| `score` | 8001–8012 | AnOxPePred, BepiPred-3.0, MHCflurry, pLM4CPPs, TIPred, GraphCPP, TemStaPro, SoDoPE |
| `filter` | 8003–8008 | ToxinPred3, HemoPI2, AlgPred2 |
| `structure` | 8201–8205 | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold, Waveflow |
| `pdb_score` | 8101–8102 | SASA, Aggrescan3D |

**Reality check**: Most "score" services are actually GPU profile in docker-compose.yml. Only toxinpred3/sodope/tipred/algpred2 are CPU. Plan service startup accordingly.

### Pipeline state management (output/ and output2/ directories)

```
output2/                          ← Completed v2 pipeline
├── STATUS.md                     ← Progress pointer
├── REVIEW.md                     ← Full post-mortem and analysis
├── step00_integrate/
├── round01_lightweight/
├── round02_scoring/
├── round03_heavy/
├── round04_enumerate/
├── round05_3d/
├── round06_pdb_eval/
└── round07_final/                ← v2 final output (90 Top + 60 Bottom)

output/                           ← Completed v1 pipeline (archived)
├── STATUS.md
├── REVIEW.md
├── round01_lightweight/
└── round07_final/                ← v1 final output

Each round directory has: README.md (report), run.log, final/ (passed/top candidates).
```

### Output directories

`output3/` — stages3 pipeline output. Currently: `pipeline.db` (2.6GB DuckDB with 19.9M candidates), `reports/`, `pdb/`, `logs/`, `final/`.

`output4/` — stages4 pipeline output. `pipeline.db` (2.7GB DuckDB), 253 PDB files (`pdb/`), reports per round (`reports/`), final constructs with full provenance (`final/constructs/`), Top 10/Bottom 10 CSVs (`final/`).

### Model file management

Models live in `tools/<name>/models/` (`.gitignore`d except small files). Shared cross-service cache at `tools/models/fair-esm/` (ESM-2 checkpoints via `torch.hub`) for pLM4CPPs, BepiPred-3.0, and ESMFold.

Five sourcing strategies: git-tracked (< 50MB), first-run auto-download (> 10MB), pip package, pure algorithm (no model), Docker built-in.

## Data directory

`data/` contains input files: `silk.fasta` (scaffold, ~346 aa), `linker.fasta` (10 linkers), `function.csv` (~25K entries), `function_3.csv` (subset).

Note: stages4 uses 10 linkers (`Flex_GGGGSx1`, `Flex_GGGGSx2` at N/C/Both positions) rather than stages2 design. Scaffold is the same 346aa silk fibroin with His-tag removed (364aa → 346aa in stages4 per `lix_silkworm_LiX_01`).

## Knowledge base

- **`AGENTS.md`** — Critical production safety rules. Read before any git operations. Absolute prohibitions on `git clean`, `git checkout -- .`, `git reset --hard` (real incident: 6GB+ models destroyed).
- **`.agents/learnings/MEMORY.md`** — Indexed GEP capsules (troubleshooting knowledge base). 30+ entries covering Docker, GPU contention, asyncio patterns, pipeline orchestration, etc.
- **`.agents/learnings/docker/`** — Docker-specific pitfalls (China mirror, slim image build deps, compose atomicity, namespace shadowing, COPY auditing, Dockerfile paths, version pinning).
- **`main/docs/threshold.md`** — Hard filter thresholds (ToxinPred3 ≥0.38, AlgPred2 ≥0.30, HemoPI2 ≥0.55).
- **`main/docs/penalty.md`** — Scoring formula documentation.
- **`docs/HUMAN.md`** — Human-operated analysis methods (Binding ddG, GROMACS MD).
- **`references/`** — Academic papers.

## Memory system

This project has a persistent memory system at `/home/lenovo/.claude/projects/-home-lenovo-Projects-iGEM-silk/memory/`. Claude Code automatically learns from each session — preferences, user role, project context, feedback. To save or recall information across sessions, write to this directory. Index is in `MEMORY.md` within that directory.

## Python environment

- Active branch is `deploy` (not `main`) — all pipeline development happens on `deploy`.
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
