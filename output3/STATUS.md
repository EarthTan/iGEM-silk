> **English** | [中文](STATUS.zh.md)

# Stages3 Pipeline Status

> Last updated: 2026-05-17 03:00

## Environment

| Item | Value |
|------|-----|
| Python | 3.13.13 |
| DuckDB | 1.5.2 |
| CD-HIT | v4.8.1 |
| GPU | NVIDIA RTX 5880 Ada (49GB) |
| Disk | 876G available (estimated) |
| DB path | `output3/pipeline.db` (2.6G) |

## Pipeline Progress

| Step | Status | Output |
|------|------|------|
| **Step 0** | ✅ **complete** | 19,890,021 candidates, 98.7 min |
| **Step 1** | 🔄 **running** | AnOxPePred (antioxidant) + AlgPred2 (allergen exclusion) |
| Step 2 | ⏳ pending | — |
| Step 3 | ⏳ pending | — |
| Step 4 | ⏳ pending | — |
| Step 5 | ⏳ pending | — |
| Step 6 | ⏳ pending | — |

## Candidate Pool Statistics

| Source | Count |
|--------|------|
| uniprot | 733,573 |
| mgy | 19,156,448 |
| **Total** | **19,890,021** |

## Step 0 Run Parameters

```
command: PYTHONUNBUFFERED=1 uv run python -m main.stages3.stage00_preprocess
DB:    output3/pipeline.db
filter:  3-30 aa, 20 standard amino acids
write:  VALUES batching (10k per SQL statement), BATCH_SIZE=100k
```
