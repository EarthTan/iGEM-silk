# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

iGEM-silk is a computational platform for designing silk fibroin fusion proteins with functional peptides. The platform integrates 15 specialized microservices (ML predictors and structure tools) to evaluate peptide candidates.

**Current state**: The pipeline is being redesigned. `main/pipeline.py` is a stub. `main/enumeration.py` has been deleted. `main/config.py` has been stripped to only microservice URLs. The new design philosophy is documented in `main/README.md` — a funnel approach that runs cheap filters early and reserves expensive 3D structure prediction for the final ~50 candidates.

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

# Run the pipeline (CURRENTLY BROKEN — raises NotImplementedError)
python -m main                # or: uv run igem-silk

# Test all microservices (health checks + prediction tests)
cd tools && python test_all_services.py

# Override any microservice host/port at runtime (no code changes needed)
export ANOXPEPRED_HOST=192.168.1.100
export ANOXPEPRED_PORT=8001
```

## Architecture

### Pipeline (`main/`) — being redesigned

The old 7-step pipeline has been torn down. What remains:

| File | Status | Purpose |
|------|--------|---------|
| `main/pipeline.py` | **stub** | Raises `NotImplementedError`. New pipeline to be implemented here. |
| `main/config.py` | **stripped** | Only `SERVICES` dict (15 microservice URLs + group tags) and `service_url()` helper. All old thresholds/weights/forbidden-zone rules removed. |
| `main/client.py` | **intact** | Async HTTP client (`httpx`) for concurrent microservice calls. Supports FASTA-based (`predict_single`, `predict_batch`) and PDB-based (`predict_pdb_single`, `predict_pdb_batch`) scoring, plus `evaluate_peptides()` for full-service concurrent evaluation, and `check_health()`. |
| `main/data_loader.py` | **intact** | FASTA and CSV parsing: `load_scaffold()`, `load_linkers()`, `load_function_peptides()`. Inputs from `data/` (silk.fasta, linker.fasta, function.csv ~25K entries). |
| `main/enumeration.py` | **deleted** | Old peptide property calculation, forbidden-zone scanning, construct enumeration. |
| `main/__init__.py` | **intact** | Entry point — calls `main.pipeline.run()` via `asyncio.run()`. |

The new pipeline design (see `main/README.md`) follows a funnel pattern:
1. FASTA-based peptide scoring/filtering → narrow to ~50 candidates
2. Enumerate constructs + 3D structure generation (AlphaFold/PEP-FOLD4)
3. PDB-based final evaluation (SASA, Aggrescan3D)

Design principles from the README:
- Cheap, high-throughput filters first; expensive 3D structure prediction last
- Multiple rounds of filtering/ranking can interleave (not strictly linear)
- Target: ≤50 constructs entering 3D structure generation
- Caching is critical — cache everything (microservice results, PDB structures, enumeration outputs)
- Use `.env` or `config.py` for what data to load, not hardcoded filters

### Microservices (`tools/`)

Each tool is a standalone FastAPI process with its own `.venv`, exposing a unified API:

```
GET  /health        → model_loaded, status
POST /predict       → single prediction
POST /predict/batch → batch prediction (up to 1000 sequences)
```

Three service templates exist in `tools/template/` (along with shared utilities):

| Template | Pattern | Concurrency | Used by |
|----------|---------|-------------|---------|
| `fasta_service.py` → `FastaToolService` | sequence → score | semaphore 10 | AnOxPePred, BepiPred-3.0, ToxinPred3, HemoPI2, MHCflurry, pLM4CPPs, TIPred, AlgPred2, GraphCPP, TemStaPro, SoDoPE |
| `structure_service.py` → `StructureService` | sequence → PDB/mmCIF | semaphore 3 | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold |
| `pdb_service.py` → `PdbScoringService` | PDB → score | semaphore 10 | SASA, Aggrescan3D |

To add a new microservice: subclass the appropriate template, implement `load_model()` and the prediction method (`predict_impl()` / `predict_structure()` / `score_pdb()`). The template handles HTTP, concurrency, and health checks.

Each service directory also contains a `Dockerfile` and a `pyproject.toml` with optional dependency groups (`ml`, `service`, `all`).

**Supporting template files:**
- `tools/template/logger.py` — unified `get_logger(name)` with rotating file handler (10 MB, 5 backups) in `tools/logs/<name>.log` plus console output
- `tools/template/job_manager.py` — `JobManager` for async structure prediction jobs (used via `create_app(..., enable_async=True)`); supports in-memory or JSON-file-persisted job tracking with 24h TTL cleanup
- `tools/utils.py` — `detect_gpu()` and `detect_system()` for cross-service GPU detection (CUDA > MPS > CPU), called by each service's `load_model()`

Full service catalog and I/O details: `main/docs/TOOLS-usage.md`
Speed/resource reference: `main/docs/TOOLS-speed.md`

### Service groups and port assignments

Microservices are grouped by pipeline role (defined in `main/config.py`):

| Group | Port range | Services | Pipeline role |
|-------|-----------|----------|---------------|
| `score` | 8001–8012 | AnOxPePred, BepiPred-3.0, MHCflurry, pLM4CPPs, TIPred, GraphCPP, TemStaPro, SoDoPE | Peptide-level scoring/ranking |
| `filter` | 8003–8008 | ToxinPred3, HemoPI2, AlgPred2 | Hard-filter (toxic/hemolytic/allergenic — absolute elimination) |
| `structure` | 8201–8204 | AlphaFold3, PEP-FOLD4, ESMFold, OmegaFold | 3D structure generation (PDB/mmCIF) |
| `pdb_score` | 8101–8102 | SASA, Aggrescan3D | PDB-based residue-level scoring |

Remote service override: set `{NAME}_HOST` (and optionally `{NAME}_PORT`) env vars to point any service at a different machine (see `main/config.py:service_url()`).

See `tools/README.md` for the full per-service port table (including input ranges, model sources, and hardware requirements).

### Key design decisions (carried forward from old pipeline)

- **Peptide-level scoring, not construct-level**: ML models were trained on short peptides (5–50 aa), not full fusion proteins (350+ aa). Constructs inherit their peptide's scores.
- **Hard filters are absolute**: toxic/allergenic/hemolytic peptides are eliminated — no trade-offs allowed.
- **Original implementation first**: When adding a microservice, use the tool author's code, model, and approach verbatim. No AI-synthesized approximations.
- **Environment portability**: Auto-detect GPU, fall back to CPU. GPU-only services (AlphaFold3) error clearly on CPU.
- **Pipeline is yet to be implemented**: `main/pipeline.py` raises `NotImplementedError`. No tests exist yet (pytest + pytest-asyncio are configured in `pyproject.toml` but no test directory created). The new pipeline should follow the funnel design in `main/README.md`.
- **Output convention**: Results go in `output/` (root level, currently empty). Pipeline stages should write intermediate/final outputs here.

### Model file management

All model files live under `tools/<name>/models/` (`.gitignore`d except small files). Four sourcing strategies:

| Strategy | When | Notes |
|----------|------|-------|
| Git-tracked (< 50 MB) | Small files (CNN ckpt, GCN weights, scalers, ESM-2 t6) | Checked into repo |
| First-run download (> 10 MB) | Large files (ESM-2 ~2.5 GB, ProtT5-XL ~3 GB) | `load_model()` auto-downloads to `models/` |
| pip package | Bundled with pip install | Models live in `.venv/` |
| None needed | Pure algorithm or synthetic training (FreeSASA, TIPred) | No model file |

**Shared model cache:** `tools/models/` is a cross-service cache. Currently `fair-esm/` (ESM-2 checkpoints via `torch.hub`) is shared — pLM4CPPs and BepiPred-3.0 both set `TORCH_HOME` to `tools/models/fair-esm/`. Migration script: `tools/migrate_models.sh`.

Docker deployments volume-mount `models/` — models are never baked into images.

## Entry point

`main/__init__.py` defines `main()` which calls `main.pipeline.run()` via `asyncio.run()`. `main/__main__.py` calls `main()` so `python -m main` works. Both currently raise `NotImplementedError` since the pipeline is being redesigned.

## Supporting documentation

- `main/README.md` — new pipeline design philosophy and requirements (Chinese + summary)
- `main/docs/TOOLS-usage.md` — every microservice's I/O format, parameters, thresholds, calling methods
- `main/docs/TOOLS-speed.md` — speed, memory, concurrency, and resource reference for all microservices
- `main/docs/threshold.md` — (not yet written)
- `tools/README.md` — microservice port table, model management, design principles
- `docs/HUMAN.md` — human-operated tools and analysis methods (outside the automated pipeline)

## Python environment

- **Root project** uses `uv` with `pyproject.toml`. Virtual environment at `./venv`.
- **Each microservice** has its own isolated `.venv` under `tools/<name>/.venv`.
- Never use `pip` or `requirements.txt` — use `uv add` / `uv sync`.
- Minimum Python 3.11.

## Conventions (from AGENTS.md)

- Project root is `./` (iGEM-silk/)
- Do not use subagents — do work directly, step by step.
