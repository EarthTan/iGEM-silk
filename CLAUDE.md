# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

iGEM-silk is a computational platform for designing silk fibroin fusion proteins with functional peptides. The platform integrates 16 specialized microservices (ML predictors, structure tools, and a remote API proxy) to evaluate peptide candidates.

**Current state**: The pipeline is being built incrementally. Stage 1 (hard-filter) and Stage 2 (scoring + ranking) are implemented as standalone scripts under `main/stages/`. The old `main/pipeline.py` stub still raises `NotImplementedError` — the actual pipeline stages run independently. The redesigned funnel approach is documented in `main/PLAN.md`.

**Who this is for**: synthetic biology researchers at the iGEM competition. The platform evaluates tens of thousands of peptide candidates fused to silk fibroin.

## Commands

```bash
# Install deps
uv sync                      # root project
cd tools/<name> && uv sync   # single microservice (includes ML/service deps)

# Lint (run from project root)
uv run ruff check .

# Run tests (none exist yet — pytest is configured in pyproject.toml)
uv run pytest

# Start all microservices (Docker, from tools/)
cd tools && docker compose --profile gpu --profile cpu up -d
# Profiles: --profile gpu (CUDA services), --profile cpu (CPU-only services)
# Mounts shared model cache (tools/models/) into containers
# Logs: tools/logs/<name>.log (or: docker compose logs -f)

# Start a single service locally (no Docker — for development)
cd tools/<name> && uv run python service.py

# Run a pipeline stage independently
uv run python -m main.stages.stage01_filter   # stage 1
uv run python -m main.stages.stage02_score    # stage 2

# Run the full pipeline (CURRENTLY BROKEN — raises NotImplementedError)
python -m main                # or: uv run igem-silk

# Test all microservices (health checks + prediction tests)
cd tools && python test_all_services.py

# Override any microservice host/port at runtime (no code changes needed)
export ANOXPEPRED_HOST=192.168.1.100
export ANOXPEPRED_PORT=8001

# Single microservice test (from project root)
python -c "from main.client import ServiceClient; import asyncio; print(asyncio.run(ServiceClient().check_health()))"
```

## Architecture

### Pipeline (`main/`) — being redesigned as independent stage scripts

The old 7-step pipeline has been torn down. The new design is a 6-stage funnel implemented as standalone scripts in `main/stages/`:

| Stage | Script | Status | Purpose | Est. time (1843 peptides) |
|-------|--------|--------|---------|--------------------------|
| 1 | `stage01_filter.py` | **Done** | Hard-filter: ToxinPred3 → AlgPred2 → HemoPI2 | ~2 min |
| 2 | `stage02_score.py` | **Done** | Score + rank via 5 services, take top N | ~49 s |
| 3 | — | Pending | Refined scoring, adaptive cutoff (30–80 peptides) | ~3–5 min |
| 4 | — | Pending | Enumerate constructs × 6 linkers × 3 positions, compress | Instant |
| 5 | — | Pending | 3D structure prediction (ESMFold primary, AF3 fallback) | ~24–36 min |
| 6 | — | Pending | PDB evaluation (SASA, Aggrescan3D, SoDoPE) + final report | ~1–12 h |

**Key design principle**: Each stage is a self-contained Python script, independently runnable, that reads the previous stage's output from `output/` and writes its own. No monolithic orchestrator. Each script has a docstring header documenting I/O paths and usage.

**Remaining files:**

| File | Status | Purpose |
|------|--------|---------|
| `main/pipeline.py` | **stub** | Raises `NotImplementedError`. Entry point for `python -m main` — not the actual pipeline. |
| `main/config.py` | **stripped** | Only `SERVICES` dict (15 microservice URLs + group tags) and `service_url()` helper. All old thresholds/weights/forbidden-zone rules removed. |
| `main/client.py` | **intact** | Async HTTP client (`httpx`) for concurrent microservice calls. Supports FASTA-based (`predict_single`, `predict_batch`) and PDB-based (`predict_pdb_single`, `predict_pdb_batch`) scoring, plus `evaluate_peptides()` for full-service concurrent evaluation, and `check_health()`. Includes async job polling (`predict_structure_async`) for long-running structure prediction tasks. |
| `main/data_loader.py` | **intact** | FASTA and CSV parsing: `load_scaffold()`, `load_linkers()`, `load_function_peptides()`. Inputs from `data/` (silk.fasta, linker.fasta, function.csv ~25K entries, plus function_3.csv subset). |
| `main/__init__.py` | **intact** | Entry point — calls `main.pipeline.run()` via `asyncio.run()`. |

### Pipeline state management (output/ directory)

The `output/` directory serves as persistent state, critical for resuming work across sessions (Claude's context is limited):

```
output/
├── STATUS.md              ← Always-current progress pointer
├── status/                ← Timestamped snapshots of STATUS.md
├── stage01_filter/        ← Per-stage output directories
│   ├── README.md          ← Report: what was done, why, results
│   ├── run.log            ← Raw execution log
│   ├── final/passed.csv   ← Peptides that passed this stage
│   └── round1_toxinpred3/ ← Per-round detail (passed.csv, failed.csv, results.json)
├── stage02_score/
│   ├── README.md          ← Report with ranking tables
│   ├── final/top80.csv    ← Top N peptides
│   └── scores/            ← Raw service responses
└── ...
```

Flow: `STATUS.md → latest stage README.md → passed.csv → next stage script`.

### Microservices (`tools/`)

Each tool is a standalone FastAPI process with its own `.venv`, exposing a unified API:

```
GET  /health        → model_loaded, status
POST /predict       → single prediction
POST /predict/batch → batch prediction (up to 1000 sequences)
```

Three service templates in `tools/template/`:

| Template | Base class | Pattern | Concurrency | Used by |
|----------|-----------|---------|-------------|---------|
| `fasta_service.py` | `FastaToolService` | sequence → score | semaphore 10 | AnOxPePred, BepiPred-3.0, ToxinPred3, HemoPI2, MHCflurry, pLM4CPPs, TIPred, AlgPred2, GraphCPP, TemStaPro, SoDoPE |
| `structure_service.py` | `StructureService` | sequence → PDB/mmCIF | semaphore 3 | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold |
| `pdb_service.py` | `PdbScoringService` | PDB → score | semaphore 10 | SASA, Aggrescan3D |

To add a new microservice: subclass the appropriate template, implement `load_model()` and the prediction method (`predict_impl()` / `predict_structure()` / `score_pdb()`). The template handles HTTP, concurrency, and health checks. The templates have extensive Chinese documentation inline.

**Supporting template files:**
- `tools/template/logger.py` — unified `get_logger(name)` with rotating file handler to `tools/logs/<name>.log`
- `tools/template/job_manager.py` — `JobManager` for async structure prediction jobs (in-memory or JSON-file-persisted, 24h TTL)
- `tools/utils.py` — `detect_gpu()` and `detect_system()` for cross-service GPU detection (CUDA > MPS > CPU)

### Service groups and port assignments

| Group | Port range | Services | Pipeline role |
|-------|-----------|----------|---------------|
| `score` | 8001–8012 | AnOxPePred, BepiPred-3.0, MHCflurry, pLM4CPPs, TIPred, GraphCPP, TemStaPro, SoDoPE | Peptide-level scoring/ranking |
| `filter` | 8003–8008 | ToxinPred3, HemoPI2, AlgPred2 | Hard-filter (absolute elimination) |
| `structure` | 8201–8204 | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold | 3D structure generation (PDB/mmCIF) |
| `pdb_score` | 8101–8102 | SASA, Aggrescan3D | PDB-based residue-level scoring |

Remote service override: set `{NAME}_HOST` (and optionally `{NAME}_PORT`) env vars (see `main/config.py:service_url()`).

### Pipeline scoring weights (from current practice)

| Service | Weight | Direction | Notes |
|---------|--------|-----------|-------|
| AnOxPePred | 0.50 | Higher = better | Primary antioxidant predictor |
| BepiPred-3.0 | 0.20 | Higher = better | B-cell epitope |
| pLM4CPPs | 0.15 | Higher = better | Cell-penetrating |
| MHCflurry | 0.10 | Lower = better | MHC-I binding (reverse weight) |
| GraphCPP | 0.05 | Higher = better | CPP via GNN |

Hard filters (absolute elimination): ToxinPred3 (≥0.38), AlgPred2 (≥0.30), HemoPI2 (≥0.55).

### Key design decisions

- **Peptide-level scoring, not construct-level**: ML models trained on short peptides (5–50 aa). Constructs inherit their peptide's scores.
- **Hard filters are absolute**: toxic/allergenic/hemolytic peptides eliminated — no trade-offs.
- **Original implementation first**: Use tool author's code, model, and approach verbatim. No AI-synthesized approximations.
- **Environment portability**: Auto-detect GPU, fall back to CPU. GPU-only services (AlphaFold3, ESMFold) error clearly on CPU.
- **Pipeline is yet to be completed**: Stages 1–2 implemented as standalone scripts. Stages 3–6 not yet written.
- **Output convention**: Results in `output/` with stage subdirectories. Each stage writes a README.md report.
- **No subagents**: Work directly, step by step (from AGENTS.md).
- **Tests**: GPU-heavy services (bepipred3, plm4cpps, hemopi2, alphafold3, esmfold, omegafold) tested serially to avoid GPU memory contention. Others run concurrently. See `tools/test_all_services.py`.

### Model file management

All model files live under `tools/<name>/models/` (`.gitignore`d except small files). Five sourcing strategies:

| Strategy | When | Notes |
|----------|------|-------|
| Git-tracked (< 50 MB) | Small files (CNN ckpt, GCN weights, scalers, ESM-2 t6) | Checked into repo |
| First-run download (> 10 MB) | Large files (ESM-2 ~2.5 GB, ProtT5-XL ~3 GB) | `load_model()` auto-downloads to `models/` |
| pip package | Bundled with pip install | Models live in `.venv/` |
| None needed | Pure algorithm (FreeSASA, TIPred) | No model file |
| Docker built-in | Inside Docker image (PEP-FOLD4, Aggrescan3D, AlphaFold3) | Not exposed to host |

**Shared model cache:** `tools/models/fair-esm/` is a cross-service cache (ESM-2 checkpoints via `torch.hub`). Shared by pLM4CPPs, BepiPred-3.0, and ESMFold. Migration script: `tools/migrate_models.sh`. Docker deployments volume-mount this directory.

## Entry point

`main/__init__.py` defines `main()` which calls `main.pipeline.run()` via `asyncio.run()`. `main/__main__.py` calls `main()` so `python -m main` works. Both currently raise `NotImplementedError`. The real pipeline runs via `python -m main.stages.stageXX_*`.

## Data directory

`data/` contains all input files:

| File | Contents |
|------|----------|
| `silk.fasta` | Silk fibroin scaffold sequence (1 entry, ~346 aa) |
| `linker.fasta` | Linker sequence library (10 entries: flexible, rigid, helical, Gly-rich, Pro-rich, PAS, Silk-like) |
| `function.csv` | Full functional peptide database (~25K entries with antioxidant/antimicrobial/etc. labels) |
| `function_3.csv` | Subset of functional peptides (smaller curated set) |
| `function_3_ref.csv` | Reference data accompanying function_3 |

## Docker deployment

All microservices have Dockerfiles. Build with profiles:
```bash
cd tools
docker compose --profile gpu up -d --build   # CUDA services only
docker compose --profile cpu up -d --build   # CPU services only
docker compose --profile gpu --profile cpu up -d  # all services
```

**Known Docker pitfalls** (documented in `.agents/learnings/docker/`):
- China network: Docker Hub unreachable — use DaoCloud mirror
- Pin specific image versions, avoid `:latest`
- `python:slim` needs `gcc`/`python3-dev`/`pkg-config` for C extensions
- `tools/` subdirectory can shadow project-level namespace packages
- One failing service causes Compose to roll back all — build in batches
- Directory name casing matters on Linux (macOS→Linux builds)

## Supporting documentation

- `main/PLAN.md` — complete funnel design philosophy with cost analysis, GPU memory planning, and 6-stage pipeline specification
- `main/docs/threshold.md` — hard filter thresholds for ToxinPred3, HemoPI2, AlgPred2; TemStaPro interpretation guide
- `tools/README.md` — microservice port table, model management, design principles
- `docs/HUMAN.md` — human-operated tools and analysis methods (Binding ddG scanning, GROMACS MD simulation)
- `references/` — academic papers and reference materials

### Learning resources (for developers)

- `.agents/learnings/` — troubleshooting knowledge base covering Docker builds, GPU memory contention, structure service patterns, git worktree workflow, ESMFold dependency management. Check when encountering build/deployment issues.
- `.agents/learnings/MEMORY.md` — index of all learning documents
- `.agents/skills/GEP-creator/` — reusable skill for creating new microservices

## Python environment

- **Root project** uses `uv` with `pyproject.toml`. Virtual environment at `./venv`.
- **Each microservice** has its own isolated `.venv` under `tools/<name>/.venv`.
- Never use `pip` or `requirements.txt` — use `uv add` / `uv sync`.
- Minimum Python 3.11.
- Run `uv sync` from the root AND from each tool directory.

## Conventions (from AGENTS.md)

- Project root is `./` (iGEM-silk/).
- Do not use subagents — do work directly, step by step.
- All Python code should use `from __future__ import annotations`.
