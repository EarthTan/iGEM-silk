# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

iGEM-silk is a computational platform for designing silk fibroin fusion proteins with functional peptides. It enumerates all possible insertion positions of antioxidant/anti-melanogenic peptides into a silk scaffold, then scores and ranks the resulting constructs using 10 specialized microservices.

## Commands

```bash
# Run the full 7-step pipeline
python -m main

# Start all 10 microservices (each in its own tools/<name>/.venv)
./tools/start_all.sh

# Stop all microservices
./tools/start_all.sh stop

# Check microservice status
./tools/start_all.sh status

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## Architecture

### Pipeline (`main/`)

The orchestration layer runs a 7-step pipeline defined in `main/pipeline.py`:

1. **Load** — scaffold (`data/silk.fasta`), linkers (`data/linker.fasta`), function peptides (`data/function.csv`, ~25K entries)
2. **Prefilter peptides** — physicochemical filters (length 5–15, GRAVY < 0, net charge ±3)
3. **Microservice scoring** — concurrent HTTP calls to all available microservices, with cache at `output/cache_peptide_scores.json`
4. **Peptide selection** — hard filters (toxicity/allergen/hemolytic) + weighted scoring + top-N cutoff
5. **Super-enumeration** — `top_peptides × (scaffold_length+1 positions) × 11 linker options`, generating up to millions of constructs
6. **Prefilter constructs** — remove constructs whose insertion position falls in forbidden zones (poly-Ala β-sheet regions, Cys clusters, hydrophobic cores)
7. **Score & rank** — weighted average of microservice scores, output top 20 to terminal and all ranked to CSV

Key files:
- `main/config.py` — **single control panel** for all parameters: microservice URLs, filter thresholds, scoring weights, forbidden-zone rules. Edit only this file to tune the pipeline.
- `main/client.py` — async HTTP client (`httpx`) for concurrent microservice calls
- `main/enumeration.py` — peptide property calculation (GRAVY, pI, charge), forbidden-zone scanning, construct enumeration, CSV/JSON output

### Microservices (`tools/`)

Each tool is a standalone FastAPI process with its own `.venv`, exposing a unified API:

```
GET  /health        → model_loaded, status
POST /predict       → single-sequence prediction
POST /predict/batch → batch prediction (up to 1000 sequences)
```

All FASTA-based services subclass `FastaToolService` from `tools/template/fasta_service.py`, implementing only `load_model()` and `predict_impl()`. The template handles HTTP, concurrency (internal semaphore of 10), error handling, and health checks.

Two additional service templates exist but are not yet widely adopted:
- `tools/template/structure_service.py` — sequence → 3D structure (PDB)
- `tools/template/pdb_service.py` — PDB structure → scoring

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
| GraphCPP | 8009 | score | CPP prediction (GNN) |
| MLCPP | 8010 | score | CPP prediction (rule-based, weight = 0) |

### Key design decisions

- **Peptide-level scoring, not construct-level**: The ML models were trained on short peptides (5–50 aa), not full fusion proteins (350+ aa). Constructs inherit their peptide's scores; differentiation comes from insertion position (forbidden-zone filtering).
- **Hard filters are absolute**: toxic/allergenic/hemolytic peptides are eliminated before enumeration — no trade-offs allowed.
- **Scoring is weighted-average**: `Σ(weight × adjusted_score) / Σ(weight)`. Inverse indicators (MHCflurry) get `adjusted = 1.0 - raw`.

## Python environment

- **Root project** uses `uv` with `pyproject.toml`. Virtual environment at `./venv`.
- **Each microservice** has its own isolated `.venv` under `tools/<name>/.venv`.
- Never use `pip` or `requirements.txt` — use `uv add` / `uv sync`.
- Minimum Python 3.11.

## Conventions (from AGENTS.md)

- Project root is `./` (iGEM-silk/)
- Do not use subagents — do work directly, step by step.
