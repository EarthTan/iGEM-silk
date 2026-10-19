> English translation of [DONE.md](DONE.md). The Chinese original is kept unchanged as the source of truth.

# Stages3 Pipeline — Completion Record

> Last updated: 2026-05-17

## Environment setup (2026-05-16)

| Item | Status | Notes |
|------|------|------|
| CD-HIT | ✅ v4.8.1 | `/usr/bin/cd-hit` |
| DuckDB | ✅ v1.5.2 | `uv add duckdb` |
| output3/ | ✅ directory structure | `pdb/`, `logs/`, `reports/`, `final/`, `pipeline.db` |
| Database | ✅ 14 tables | Full schema in `db.py`, including `candidates` + `checkpoint` |
| STATUS.md | ✅ environment snapshot | `output3/STATUS.md` |
| CLAUDE.md | ✅ updated | Appended the "on-demand startup principle" |

## New files

| File | Description |
|------|------|
| `main/stages3/__init__.py` | Package initialization |
| `main/stages3/db.py` | DuckDB interface (schema, batch writes, distribution statistics, checkpoints) |
| `main/stages3/sample_fasta.py` | FASTA reservoir sampling tool |
| `main/stages3/fasta_parser.py` | Streaming reader for very large FASTA files |
| `main/stages3/cdhit_wrapper.py` | CD-HIT command-line wrapper |
| `main/stages3/stage00_preprocess.py` | Stage 0 preprocessing main script |
| `main/stages3/service_map.py` | Service dependency map (step naming) |
| `main/stages3/docker_utils.py` | On-demand Docker startup |
| `main/stages3/analytics.py` | Variance-aware weighting engine |
| `main/stages3/ARCHITECTURE_AS_BUILT.md` | Actual architecture document |
| `output3/STATUS.md` | Environment status record |

## Stage 0 development (2026-05-16)

### CD-HIT parameter experiments

Extracted 100k short peptides (3-30aa) from each of the two FASTA sources and tested clustering with `-c 0.90/0.95/0.98/1.00`.

**Conclusion: short peptides are naturally extremely diverse, so CD-HIT is basically ineffective.**
- MGnify: 3.67M scanned → 100k short peptides (2.72%); at any threshold almost 100% single-sequence clusters
- UniProt: 39M scanned → 100k short peptides (0.25%); -c 0.90 merges only 5% of sequences

**Decision: skip CD-HIT and switch to exact deduplication (dedup of 100% identical sequences), which DuckDB's indexes guarantee naturally.**

### DuckDB performance optimization

Found that `executemany` writes only 200 rows/s (41 hours for 17M rows), so switched to a single INSERT + VALUES batch (20k rows/s), a 100x speedup.

### Sampling test results

```
uv run python -m main.stages3.stage00_preprocess --sample 10000
```

| Data source | Scanned | Written | Elapsed |
|--------|------|------|------|
| UniProt | 5.3M rows | 10,000 rows | 20s |
| MGnify | 370k rows | 10,000 rows | 2s |

- Pass rates: UniProt ≈0.25%, MGnify ≈2.7%
- Random DB read: 10k rows / 0.01s
- Automatic report generation: `output3/reports/stage0_report.md`

## Infrastructure setup (2026-05-16)

### service_map.py
- Uses "step" naming (step0-step6), not "stage"
- Based on the actual profile configuration in `tools/docker-compose.yml`
- Discovered a major difference between the planning assumptions and reality: most scoring services are actually GPU profile

### docker_utils.py
- `ensure_services()` is the main entry point and is idempotent (repeated calls return the cache)
- Automatically checks the Docker daemon → starts on demand → polls /health until ready
- Automatically detects the bridge IP (preparing for later network optimization)
- Supports the `skip_docker=True` argument for development and debugging

### analytics.py
- Variance-aware weighting engine: read scores → compute distribution → winsorization → normalized weights → apply ranking
- Validated: services with good discriminative power automatically receive higher weight (verified with a 5x gap)
- Fully recorded in the `score_distribution` + `weight_config` tables, so the whole chain is auditable

### ARCHITECTURE_AS_BUILT.md
- Records the actually implemented architecture, for side-by-side comparison with the planning documents in `plan/`
- Covers: directory structure, module responsibilities, database schema, on-demand startup protocol, weighting algorithm
- Clearly marks every deviation from the planning documents and its reason

## Stage 0 full run (2026-05-17)

| Item | Status | Notes |
|------|------|------|
| UniProt processing | ✅ complete | 225.6M scanned → 733,573 written (0.33%) |
| MGnify processing | ✅ complete | 623.8M scanned → 19,156,448 written (3.07%) |
| Candidate pool total | ✅ **19,890,021** | 849M sequences scanned in total |
| Total elapsed | ✅ 98.7 min | 5,924s |
| DB file | ✅ 2.6 GB | `output3/pipeline.db` |
| Automatic report | ✅ | `output3/reports/stage0_report.md` |
| Step 0 README | ✅ | `output3/step0/README.md` |
| DONE.md | ✅ updated | This file |

### Key findings

- **Actual pass rates**: UniProt 0.33%, MGnify 3.07% (highly consistent with the sampling test)
- **Total candidates**: 19.9M (below the planned 30M-100M, but far above stages2's 1M)
- **Scan speed**: 290k seq/s before batch writes; dropped to 120k seq/s once the DB grew to 1GB
- **DB size**: 19.9M rows / 2.6GB, about 7.6M rows/GB

## Step 1 development (2026-05-17)

### New/modified files

| File | Description |
|------|------|
| `main/stages3/stage01_lightweight.py` | Step 1 main script |
| `main/stages3/db.py` | `insert_stage1_scores` changed to VALUES batch processing (replacing the slow executemany) |

### Design summary

Step 1 runs two lightweight scoring services over the 19.9M candidate peptides:
- **AnOxPePred** (gpu profile, port 8001): antioxidant activity prediction, the core screening signal
- **AlgPred2** (cpu profile, port 8008): allergen prediction, hard threshold ≥0.30 eliminates

### Technical decisions

1. **Batched streaming processing**: read 100k rows from DuckDB at a time, avoiding loading all 19.9M into memory
2. **Two services in parallel**: the two services are called concurrently via `asyncio.gather`, without blocking each other
3. **Semaphore(5) per service**: controls the concurrent load on the GPU service and prevents GPU memory OOM
4. **Resume from checkpoint**: supported through `MAX(candidate_id)` on the `stage1_scores` table and the `checkpoint` table
5. **AlgPred2 hard filter**: `score ≥ 0.30` eliminates; score IS NULL passes (tolerance for service failure)
6. **DB write optimization**: drops `executemany` in favor of VALUES batch processing (expected 100x speedup)
