> **English** | [中文](ARCHITECTURE_AS_BUILT.zh.md)

# Stages3 Architecture Document (As-Built)

> Version: v1.0 — 2026-05-16
> This document records the actual implementation of stages3, for side-by-side comparison with the planning documents in `plan/`.

---

## 1. Directory structure

```
main/stages3/
├── __init__.py              # package initialization
├── DONE.md                  # progress log (updated continuously)
├── ARCHITECTURE_AS_BUILT.md # ← this document (actual architecture)
│
├── plan/                    # ← planning documents (original design intent)
│   ├── PLAN.md              # overall roadmap
│   ├── ARCHITECTURE.md      # three-layer architecture design
│   ├── DB_SCHEMA.md         # database design
│   ├── DATA_PREP.md         # data preprocessing plan
│   └── TECH_REQUIREMENTS.md # mandatory technical specification
│
├── db.py                    # DuckDB interface
├── docker_utils.py          # on-demand Docker startup
├── service_map.py           # service dependency map
├── analytics.py             # variance-aware weighting engine
│
├── fasta_parser.py          # streaming reader for very large FASTA files
├── cdhit_wrapper.py         # CD-HIT wrapper (tested, actually skipped)
├── sample_fasta.py          # FASTA reservoir sampling
└── stage00_preprocess.py    # Step 0: data preprocessing

output3/
├── pipeline.db              # DuckDB database
├── STATUS.md                # environment status
├── reports/                 # per-stage reports
├── pdb/                     # Step 4 PDB files
├── logs/                    # run logs
└── final/                   # final output
```

---

## 2. Module responsibilities

### db.py — DuckDB interface

The single entry point for database operations; no stage script constructs SQL directly.

| Method | Purpose |
|------|------|
| `init_schema()` | Create all 14 tables (idempotent) |
| `insert_candidates()` | Batch insert candidate peptides (10k/batch, automatic IDs) |
| `insert_stage1_scores()` | Write Step 1 scores |
| `mark_stage1_passed()` | Record Step 1 passers |
| `compute_distribution()` | Compute single-column distribution statistics |
| `set_checkpoint()` / `get_checkpoint()` | Checkpoint read/write |
| `get_last_processed_id()` | Resume-from-checkpoint query |
| `row_count()` | Row count statistics |

**Key performance decision**: use a single `INSERT INTO ... VALUES (...), (...)` statement rather than `executemany`. DuckDB's executemany manages only 200 rows/s, while VALUES batch processing reaches 20k rows/s (a 100x improvement).

### docker_utils.py — on-demand Docker startup

Before each step runs, start only the microservices that step depends on.

| Function | Purpose |
|------|------|
| `ensure_services(names, profiles)` | Main entry: start → health check → cache |
| `check_docker_daemon()` | Check whether the Docker daemon is running |
| `start_services(profiles, services)` | `docker compose up -d` for the specified services |
| `detect_bridge_ip(container)` | Detect the container's bridge IP |
| `wait_for_services()` | Poll `/health` until ready |
| `clear_cache()` | Clear the cache when switching steps |

**Idempotency**: repeated `ensure_services` calls for the same service return the cached result directly.

### service_map.py — service dependency map

```
step0: []                               # purely local
step1: [anoxpepred, algpred2]           # antioxidant + allergen
step2: [anoxpepred, bepipred3, ...]     # full 9-service scoring
step3: [sodope, temstapro]              # solubility + stability
step4: [omegafold]                      # 3D structure
step5: [sasa, aggrescan3d]              # PDB evaluation
step6: []                               # purely local (final ranking)
```

⚠️ **The actual profile distribution differs from the plan**: (see `plan/PLAN.md` vs. `tools/docker-compose.yml` in detail)
- The plan assumed most scoring services are CPU; in reality only `toxinpred3`/`sodope`/`tipred`/`algpred2` are CPU
- `anoxpepred`/`bepipred3`/`plm4cpps`/`graphcpp`/`temstapro`/`mhcflurry`/`hemopi2` are all GPU profile
- As a result most steps need to start both the `gpu` and `cpu` profiles at the same time

### analytics.py — variance-aware weighting engine

The core innovation of stages3. See section 5 below for details.

---

## 3. Step 0 implementation details

### Flow

```
raw FASTA (102G + 120G)
    │  streaming scan (fasta_iter_lines, 290k entries/s)
    ▼
3-30aa length filter
    │
    ▼
standard amino-acid filter (20 standard AAs)
    │
    ▼
batch write to DuckDB (10k entries/batch, 20k entries/s)
    │
    ▼
generate statistics report → reports/stage0_report.md
```

### CD-HIT parameter experiments

A parameter sweep was run on short-peptide samples from both databases; the conclusion: **skip CD-HIT**.

| Parameter | MGnify clustering rate | UniProt clustering rate |
|------|-------------|---------------|
| -c 0.90 | 0.2% | ~5% |
| -c 0.95 | 0.0% | ~3% |
| -c 1.00 | 0.0% | ~3% |

Short peptides (3-30 aa) are naturally extremely diverse; even at 90% similarity they hardly ever form clusters. The benefit CD-HIT brings does not justify its complexity.

### Actual pass rates

| Data source | Estimated pass rate | Actual pass rate | Notes |
|--------|-----------|-----------|------|
| UniProt (225M) | 1-3% | **0.25%** | Mostly full-length proteins, very few short peptides |
| MGnify (624M) | 10-20% | **2.7%** | Metagenomes contain more short sequences than UniProt, but still limited |
| **Total** | **30M-100M** | **~17.5M** | Far below the estimate |

---

## 4. On-demand startup principle (differences from plan/)

### Plan vs. implementation

| Dimension | Design in the plan | Actual implementation |
|------|------------|---------|
| Docker startup | Start everything at once | Start per step, on demand |
| Service grouping | Assume score = cpu, structure = gpu | In reality most score services are also under gpu |
| Bridge IP | Must be detected manually | Detected automatically by `docker_utils.py` |
| Health check | One unified check after startup | Independent check per step, idempotent cache |

### Startup protocol

Standard entry point of each step script:

```python
from main.stages3.docker_utils import ensure_services
from main.stages3.service_map import get_step_services

info = get_step_services("step1")
health = ensure_services(info["services"], info["profiles"])
unavailable = [s for s, h in health.items() if not h["available"]]
if unavailable:
    sys.exit(f"Service unavailable: {unavailable}")
```

---

## 5. Variance-aware weighting

### Algorithm

```
1. Read every score of every candidate
2. Compute the winsorized standard deviation for each score (clip the extreme 1%)
3. Weight w_i = σ_i_winsorized / Σσ_j_winsorized
4. Composite score = Σ(w_i × score_i_normalized)
5. Rank by composite score
```

### Validation results (simulated data)

| Service | Standard deviation | Winsorized σ | Weight |
|------|-------|-------------|------|
| anoxpepred | 0.25 | 0.249 | **0.557** |
| sodope | 0.15 | 0.149 | **0.333** |
| bepipred3 | 0.05 | 0.049 | **0.110** |

Services with good discriminative power automatically receive higher weight. The weight ratio ≈ the standard deviation ratio.

### Comparison with stages2

| Aspect | stages2 (fixed weights) | stages3 (variance-aware) |
|------|------------------|------------------|
| Weight source | Manually assigned | Data-driven |
| Discriminative power handling | Fixed weight for every service | Automatic noise reduction |
| Extreme value handling | None | Winsorization |
| Auditability | Manually recorded in CSV | `weight_config` table |

---

## 6. Database schema (actual implementation)

### Table list (14 tables)

| Table | Purpose | Estimated rows |
|----|------|---------|
| `candidates` | Candidate peptide pool | 17.5M |
| `stage1_scores` | Step 1 scores | 17.5M |
| `stage1_passed` | Step 1 passers | ~5M |
| `stage2_scores` | Step 2 full scoring | ~0.5M |
| `stage2_ranking` | Step 2 ranking | ~0.5M |
| `constructs` | Construct enumeration | ~50K |
| `construct_scores` | Construct scoring | ~50K |
| `structure_jobs` | Structure prediction jobs | ~500 |
| `structure_results` | Structure prediction results | ~500 |
| `pdb_eval` | PDB evaluation | ~500 |
| `final_ranking` | Final ranking | ~100 |
| `score_distribution` | Distribution statistics | ~20 |
| `weight_config` | Weight configuration | ~5 |
| `checkpoint` | Checkpoints | ~20 |

### Differences from the DB_SCHEMA.md plan

| Item | Plan | Actual |
|------|------|------|
| Unique index | `(source, source_id) UNIQUE` | Changed to a regular index (write performance consideration) |
| Auto-increment ID | DEFAULT nextval | Kept, for large-scale writes |
| Memory limit | 32GB | Kept |

---

## 7. Summary of deviations from the planning documents

| Planned item | Actual state | Reason |
|---------|---------|------|
| CD-HIT clustering | **Skipped** | Short peptides are too diverse; clustering is ineffective |
| Stage 0 split into 4 steps | **Merged into 2 steps** | length filter → AA filter → write directly |
| ~30M-100M candidates | **~17.5M** | Actual pass rates far below the estimates |
| Most services are CPU | **Most are GPU** | The actual configuration in docker-compose.yml |
| 5 technical-debt items | **Pending** | Fix them when encountered at runtime; they do not block development |

---

## 8. Command quick reference

```bash
# Step 0: data preprocessing
uv run python -m main.stages3.stage00_preprocess

# Step 0 (sampling mode)
uv run python -m main.stages3.stage00_preprocess --sample 10000

# UniProt only
uv run python -m main.stages3.stage00_preprocess --uniprot-only

# MGnify only
uv run python -m main.stages3.stage00_preprocess --mgy-only

# Test Docker service startup
uv run python -m main.stages3.docker_utils anoxpepred algpred2
```
