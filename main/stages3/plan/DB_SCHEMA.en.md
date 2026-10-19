> English translation of [DB_SCHEMA.md](DB_SCHEMA.md). The Chinese original is kept unchanged as the source of truth.

# Stages3 Database Design

> Version: v1.0 — 2026-05-15
> Database: DuckDB (embedded columnar database)
> File: `output3/pipeline.db`

---

## 1. Why DuckDB

After evaluating several options, DuckDB is the most suitable choice for stages3:

| Feature | DuckDB | SQLite | PostgreSQL |
|------|--------|--------|------------|
| Deployment | Embedded, no server process | Embedded, no server process | Requires a server process |
| File format | Single file | Single file | Requires a data directory |
| Parallel queries | ✅ Automatic multithreading | ❌ Single-threaded | ✅ But requires configuration |
| Columnar storage | ✅ Fast analytical queries | ❌ Row-oriented storage | ❌ Row-oriented storage |
| In-memory mode | ✅ Fully in-memory or on disk | ❌ Disk only | ❌ Disk only |
| JSON support | ✅ Native | ⚠️ Extension | ✅ |
| Installation | pip install duckdb | Built in | Requires apt install |

**Conclusion**: DuckDB is an embedded database designed specifically for data analytics. For stages3's use case—writing tens of millions of rows, running aggregation analysis (AVG, STDDEV, PERCENTILE), exporting to CSV—DuckDB is 10-100× faster than SQLite while keeping the simplicity of a single file and zero deployment.

Although SQLite is a row-oriented database that ships with Python, its design goal (transactional OLTP) is a complete mismatch for our use case (analytical OLAP). An aggregation query over tens of millions of rows takes minutes on SQLite but only seconds on DuckDB.

---

## 2. Table Overview

The entire pipeline uses a single DuckDB file containing the following tables:

```
pipeline.db
├── candidates          ← Stage 0 output: preprocessed candidate peptide pool
├── stage1_scores       ← Stage 1 output: lightweight primary screening scores
├── stage1_passed       ← Stage 1 passers (view or materialized table)
├── stage2_scores       ← Stage 2 output: full scoring results
├── stage2_ranking      ← Stage 2 ranking
├── constructs          ← Stage 3 output: construct enumeration
├── construct_scores    ← Stage 3 scores: SoDoPE + TemStaPro
├── structure_jobs      ← Stage 4 state: structure prediction job tracking
├── structure_results   ← Stage 4 output: structure prediction results
├── pdb_eval            ← Stage 5 output: SASA + Aggrescan3D
├── final_ranking       ← Stage 6 output: final ranking
├── score_distribution  ← Global: distribution statistics for all scores
├── weight_config       ← Global: assignment records for variance-aware weights
└── checkpoint          ← Global: checkpoint / resume state
```

---

## 3. Detailed Table Designs

### candidates (candidate peptide pool)

This is the core base table of the entire pipeline; every other table references its `candidate_id`.

| Column | Type | Description |
|----|------|------|
| candidate_id | BIGINT | Auto-increment primary key |
| source | VARCHAR | "uniprot" or "mgy" |
| source_id | VARCHAR | Original FASTA ID |
| header | VARCHAR | Full FASTA header (for provenance) |
| sequence | VARCHAR | Amino acid sequence |
| length | SMALLINT | Length |
| is_standard_aa | BOOLEAN | Whether it contains only the 20 standard amino acids |
| cluster_id | VARCHAR | CD-HIT cluster ID |
| cluster_rep | BOOLEAN | Whether it is the representative sequence of a CD-HIT cluster |

**Index**: unique index on (source, source_id) to prevent duplicate imports.
**Partitioning strategy**: partition by source (uniprot / mgy), so that different data sources can be processed separately.

### stage1_scores (lightweight primary screening scores)

| Column | Type | Description |
|----|------|------|
| candidate_id | BIGINT | References candidates |
| anoxpepred_score | FLOAT | AnOxPePred prediction |
| anoxpepred_success | BOOLEAN | Whether the call succeeded |
| algpred2_score | FLOAT | AlgPred2 prediction |
| algpred2_success | BOOLEAN | Whether the call succeeded |
| scored_at | TIMESTAMP | Scoring time |

**Purpose**: record the raw Stage 1 scores. Even if a candidate peptide is eliminated by AlgPred2, its AnOxPePred score is retained for post-hoc analysis.

### stage1_passed (Stage 1 passers)

| Column | Type | Description |
|----|------|------|
| candidate_id | BIGINT | Primary key, references candidates |
| anoxpepred_score | FLOAT | Retained for use in Stage 2 |
| passed_reason | VARCHAR | "passed" or the elimination reason |

**Filter condition**: AlgPred2 < 0.30 (non-allergen). AnOxPePred has no hard threshold and is instead handled by relative ranking in Stage 2.

### stage2_scores (full scoring results)

| Column | Type | Description |
|----|------|------|
| candidate_id | BIGINT | References candidates |
| anoxpepred_score | FLOAT | |
| bepipred3_score | FLOAT | |
| plm4cpps_score | FLOAT | |
| graphcpp_score | FLOAT | |
| temstapro_score | FLOAT | |
| sodope_score | FLOAT | |
| mhcflurry_score | FLOAT | |
| toxinpred3_score | FLOAT | Used for absolute exclusion |
| hemopi2_score | FLOAT | Used for absolute exclusion |
| ..._success | BOOLEAN | Success flag for each service (each column has a corresponding *_success column) |
| scored_at | TIMESTAMP | |

This table will have a large number of columns (~20), which is reasonable—DuckDB's columnar storage handles such wide tables very well.

### score_distribution (score distribution statistics)

This table is not data required for running the pipeline; it is the core input for **variance-aware weighting**.

| Column | Type | Description |
|----|------|------|
| id | BIGINT | Auto-increment primary key |
| stage_name | VARCHAR | "stage1" or "stage2" or "final" |
| service_name | VARCHAR | Service name, e.g. "anoxpepred" |
| count | BIGINT | Number of valid samples |
| mean | FLOAT | Mean |
| stddev | FLOAT | **Standard deviation (core metric)** |
| min | FLOAT | Minimum |
| p01 | FLOAT | 1st percentile (extremes removed) |
| p05 | FLOAT | 5th percentile |
| p25 | FLOAT | Lower quartile |
| p50 | FLOAT | Median |
| p75 | FLOAT | Upper quartile |
| p95 | FLOAT | 95th percentile |
| p99 | FLOAT | 99th percentile |
| max | FLOAT | Maximum |
| winsorized_stddev | FLOAT | **Standard deviation after trimming (more robust)** |
| computed_weight | FLOAT | Weight assigned based on variance |
| computed_at | TIMESTAMP | |

**Computation of winsorized_stddev**: the standard deviation computed after removing the top and bottom 1% extreme values. This avoids individual outliers inflating or deflating a service's perceived discriminative power.

### weight_config (weight configuration records)

Records the weight assignment process for each stage, ensuring **reproducibility** and **auditability**.

| Column | Type | Description |
|----|------|------|
| id | BIGINT | Auto-increment primary key |
| stage_name | VARCHAR | "stage2" or "stage6" |
| total_candidates | BIGINT | Number of candidates participating in the weight computation |
| weight_formula | VARCHAR | Formula used: "stddev_normalized" or "winsorized_stddev_normalized" |
| weights | JSON | Full JSON of the weights of each service |
| distribution_snapshot | JSON | Full JSON of the distribution statistics of each service |
| created_at | TIMESTAMP | |

### constructs (construct enumeration table)

| Column | Type | Description |
|----|------|------|
| construct_id | BIGINT | Auto-increment primary key |
| candidate_id | BIGINT | References candidates |
| linker | VARCHAR | Linker type: "flexible" or "rigid" |
| position | VARCHAR | Fusion position: "N", "internal", "C" |
| scaffold_seq | VARCHAR | Silk protein scaffold sequence |
| linker_seq | VARCHAR | Linker sequence |
| peptide_seq | VARCHAR | Functional peptide sequence |
| full_sequence | VARCHAR | Full construct amino acid sequence |

### checkpoint (checkpoint table)

The core of resume-from-interruption.

| Column | Type | Description |
|----|------|------|
| stage | VARCHAR | Stage name |
| step | VARCHAR | Sub-step name |
| status | VARCHAR | "running" / "done" / "failed" |
| total_items | BIGINT | Total number of items to process in this step |
| processed_items | BIGINT | Number already processed |
| error_message | VARCHAR | Error message on failure |
| started_at | TIMESTAMP | |
| completed_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

---

## 4. Checkpoint and Resume Mechanism

### Design Principles

1. **Idempotency**: each stage's output depends only on the input data and is unaffected by previous runs
2. **Fine granularity**: update the checkpoint after each processed batch (e.g., 100k rows)
3. **Auditability**: the checkpoint table records the start, end, and error information of each stage

### Recovery Flow

```
Checkpoint system:

At stage start:
  checkpoint.upsert(stage="stage1", status="running", started_at=now())

When resuming a run:
  status = checkpoint.get("stage1")?.status
  if status == "done":
      skip → proceed to Stage 2
  elif status == "running":
      query the largest processed candidate_id
      continue from the breakpoint
  elif status is None or status == "failed":
      restart Stage 1

At stage completion:
  checkpoint.upsert(stage="stage1", status="done", completed_at=now())
```

---

## 5. Read/Write Interface Paradigm

All database operations are accessed through the unified interface module `main/stages3/db.py`; pipeline scripts do not construct SQL queries directly.

Recommended natural-language-style interface (describes the purpose, no code):

- **Initialize the database**: create the pipeline.db file and run all CREATE TABLE statements
- **Write the candidate peptide pool**: batch-insert candidate records with automatic deduplication
- **Record scores**: batch-write to the stage score tables, associated by candidate_id
- **Read pending candidates**: query the list of candidates that have not yet completed the current stage
- **Update checkpoints**: record the current processing progress in the checkpoint table
- **Compute distribution statistics**: run aggregation queries against the specified table and return the standard deviation and each percentile
- **Compute weights**: read the standard deviations from the distribution statistics table and compute normalized weights
- **Generate rankings**: apply the weights to the score table, compute the weighted composite score, and output a sorted ranking

---

## 6. Performance and Space Estimates

### Storage Space

| Table | Estimated rows | Estimated size |
|----|---------|---------|
| candidates | 20-60 million | ~2-6 GB |
| stage1_scores | 20-60 million | ~3-9 GB |
| stage2_scores | 2-6 million (after passing Stage 1) | ~1-3 GB |
| constructs | 20-50k (top candidates) | ~50 MB |
| Others + indexes | — | ~1 GB |
| **Total** | | **~10-20 GB** |

DuckDB's single-file design and columnar compression make the actual disk footprint far smaller than that of a row-oriented database.

### Expected Query Performance

| Operation | Data volume | Expected time |
|------|--------|---------|
| Write 1 million rows | 1 million | < 1s |
| Compute stddev over 50 million sequences | 50 million | ~2-5s |
| Fetch the Top 1000 by ranking | 5 million | < 1s |
| Export 100k rows to CSV | 100k | < 1s |
| Composite query with JOIN | 5 million | ~1-2s |

DuckDB's columnar storage means aggregation computations (standard deviation, percentiles, etc.) read only the columns they need and do not scan entire rows.
