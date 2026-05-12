# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

iGEM-silk is a computational platform for designing silk fibroin fusion proteins with functional peptides. It enumerates all possible insertion positions of antioxidant/anti-melanogenic peptides into a silk scaffold, then scores and ranks the resulting constructs using specialized microservices.

## Commands

```bash
# Run the full 7-step pipeline
python -m main
igem-silk                   # CLI command (same as above)

# Start all microservices (each in its own tools/<name>/.venv)
./tools/start_all.sh

# Stop / status
./tools/start_all.sh stop
./tools/start_all.sh status

# Start microservices via Docker (GPU + CPU profiles, from tools/)
cd tools && docker compose --profile gpu --profile cpu up -d

# Install deps
uv sync                      # root project
cd tools/<name> && uv sync   # single microservice

# Lint
uv run ruff check .
```

## Architecture

### Pipeline (`main/`)

The orchestration layer runs a 7-step pipeline defined in `main/pipeline.py`:

1. **Load** — scaffold (`data/silk.fasta`, ~346 aa), linkers (`data/linker.fasta`, 10 types), function peptides (`data/function.csv`, ~25K entries). Currently filters for `is_antioxidant == 1` only; other activity columns (anti-microbial, anti-glycation, collagen-stimulating, cell-penetrating) are available but unused.
2. **Prefilter peptides** — physicochemical filters (length 5–15, GRAVY < 0, net charge ±3)
3. **Microservice scoring** — concurrent HTTP calls to all available microservices, with cache at `output/cache_peptide_scores.json`. On re-runs with the same peptide set, the pipeline prompts to reuse cached scores (skipping expensive ML inference).
4. **Peptide selection** — hard filters (toxicity/allergen/hemolytic) + weighted scoring + top-N cutoff
5. **Super-enumeration** — `top_peptides × (scaffold_length+1 positions) × 11 linker options`, generating up to millions of constructs
6. **Prefilter constructs** — remove constructs whose insertion position falls in forbidden zones (poly-Ala β-sheet regions, Cys clusters, hydrophobic cores)
7. **Score & rank** — weighted average of microservice scores, output top 20 to terminal and all ranked to CSV

Key files:
- `main/pipeline.py` — **7-step pipeline orchestration** (`run()` function), step output management, caching logic
- `main/config.py` — **single control panel** for all parameters: microservice URLs, filter thresholds, scoring weights, forbidden-zone rules. Edit only this file to tune the pipeline.
- `main/data_loader.py` — FASTA and CSV parsing (scaffold, linkers, function peptides). Modify this when input formats change.
- `main/client.py` — async HTTP client (`httpx`) for concurrent microservice calls. Handles both FASTA-based (`predict_single`, `predict_batch`) and PDB-based (`predict_pdb_single`, `predict_pdb_batch`) scoring.
- `main/enumeration.py` — peptide property calculation (GRAVY, pI, charge), forbidden-zone scanning, construct enumeration, CSV/JSON output

The pipeline persists intermediate results to `output/` after each step (JSON summaries + large CSV files). A full run generates ~580 MB. The `output/.gitignore` contains `*` — outputs are never committed.

### Microservices (`tools/`)

Each tool is a standalone FastAPI process with its own `.venv`, exposing a unified API:

```
GET  /health        → model_loaded, status
POST /predict       → single-sequence prediction
POST /predict/batch → batch prediction (up to 1000 sequences)
```

All FASTA-based services subclass `FastaToolService` from `tools/template/fasta_service.py`, implementing only `load_model()` and `predict_impl()`. The template handles HTTP, concurrency (internal semaphore of 10), error handling, and health checks.

Two additional service templates exist:
- `tools/template/structure_service.py` — sequence → 3D structure (PDB). Subclass `StructureService`, implement `predict_structure()`. Concurrency limited to 3. Used by AlphaFold3 and PEP-FOLD4.
- `tools/template/pdb_service.py` — PDB structure → scoring. Subclass `PdbScoringService`, implement `score_pdb()`. Concurrency limited to 10. Used by SASA and Aggrescan3D.

Each service directory also contains a `Dockerfile` for containerized deployment, and a `pyproject.toml` with optional dependency groups (`ml`, `service`, `all`).

| Service | Port | Type | Role |
|---------|------|------|------|
| AnOxPePred | 8001 | score | Antioxidant peptide prediction (CNN, GPU-accelerated) |
| BepiPred-3.0 | 8002 | score | B-cell epitope prediction (ESM-2) — proxy for surface exposure |
| ToxinPred3 | 8003 | filter | Toxicity prediction (one-vote veto if ≥ 0.38) |
| HemoPI2 | 8004 | filter | Hemolyticity prediction (veto if ≥ 0.55) |
| MHCflurry | 8005 | score | MHC-I binding affinity (inverse indicator — higher = worse) |
| pLM4CPPs | 8006 | score | Cell-penetrating peptide prediction (ESM-2 + CNN) |
| TIPred | 8007 | score | Tyrosinase inhibitory peptide (anti-melanin core function) |
| AlgPred2 | 8008 | filter | Allergenicity prediction (veto if ≥ 0.3) |
| GraphCPP | 8009 | score | CPP prediction (GraphSAGE GNN) |
| TemStaPro | 8010 | score | Protein thermal stability prediction (ProtT5-XL + MLP ensemble) |
| SoDoPE | 8012 | score | Protein solubility prediction (SWI — solubility-weighted index, CPU) |
| AlphaFold3 | 8201 | structure | 3D structure prediction (Docker, Ubuntu+GPU only) |
| PEP-FOLD4 | 8202 | structure | De novo peptide structure prediction (Docker, 5–40 aa) |
| SASA | 8101 | pdb_score | Solvent accessible surface area analysis (FreeSASA) |
| Aggrescan3D | 8102 | pdb_score | Structural aggregation propensity (A3D score, Docker) |

### Key design decisions

- **Peptide-level scoring, not construct-level**: The ML models were trained on short peptides (5–50 aa), not full fusion proteins (350+ aa). Constructs inherit their peptide's scores; differentiation comes from insertion position (forbidden-zone filtering).
- **Hard filters are absolute**: toxic/allergenic/hemolytic peptides are eliminated before enumeration — no trade-offs allowed.
- **Scoring is weighted-average**: `Σ(weight × adjusted_score) / Σ(weight)`. Inverse indicators (MHCflurry) get `adjusted = 1.0 - raw`.

### Model file management

All model files live under `tools/<name>/models/` (`.gitignore`d except small files). Four sourcing strategies:

| Strategy | When | Notes |
|----------|------|-------|
| Git-tracked (< 5 MB) | Small files (CNN ckpt, GCN weights, scalers) | Checked into repo |
| First-run download (> 10 MB) | Large files (ESM-2 ~2.5 GB, ProtT5-XL ~3 GB) | `load_model()` auto-downloads to `models/` |
| pip package | Bundled with pip install | Models live in `.venv/` |
| None needed | Pure algorithm or synthetic training (FreeSASA, TIPred) | No model file |

**Shared model cache:** `tools/models/` is a cross-service cache for models used by multiple services. Currently `fair-esm/` (ESM-2 checkpoints via `torch.hub`) is shared — pLM4CPPs and BepiPred-3.0 both set `TORCH_HOME` to `tools/models/fair-esm/`. A migration script (`tools/migrate_models.sh`) moves existing per-service checkpoints into the shared directory.

Docker deployments volume-mount `models/` — models are never baked into images.

### Microservice design principles

When adding a new microservice to `tools/`:
1. **Original implementation first** — use the tool author's code, model, and approach verbatim. No shortcuts or AI-synthesized approximations.
2. **Environment portability** — auto-detect GPU and use it when available, fall back to CPU otherwise. Services that require GPU (AlphaFold3) should error clearly on CPU. CUDA-capable services get a `Dockerfile` for GPU deployment.
3. **Unified API** — subclass `FastaToolService`, `StructureService`, or `PdbScoringService` from `tools/template/`. Only implement `load_model()` and `predict_impl()`; the template handles HTTP, concurrency, and health checks.

## Entry point

`main/__init__.py` defines `main()` which calls `main.pipeline.run()` via `asyncio.run()`. `main/__main__.py` calls `main()` so `python -m main` works. Both are entry points into the single pipeline orchestration in `pipeline.py`.

## Supporting documentation

- `main/docs/PIPELINE.md` — deeper pipeline walkthrough
- `main/docs/TOOLS.md` — microservice design reference
- `tools/README.md` — microservice port table, model management, design principles

## Python environment

- **Root project** uses `uv` with `pyproject.toml`. Virtual environment at `./venv`.
- **Each microservice** has its own isolated `.venv` under `tools/<name>/.venv`.
- Never use `pip` or `requirements.txt` — use `uv add` / `uv sync`.
- Minimum Python 3.11.

## Conventions (from AGENTS.md)

- Project root is `./` (iGEM-silk/)
- Do not use subagents — do work directly, step by step.
