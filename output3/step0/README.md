> **English** | [中文](README.zh.md)

# Step 0 — Data Preprocessing Report

> Generated: 2026-05-17 02:59

## Overview

Short peptides of 3-30aa were extracted from the two very large FASTA databases UniProt + MGnify (222G combined) and, after filtering for standard amino acids, written into DuckDB.

| Metric | Value |
|------|-----|
| Total candidate pool | **19,890,021** |
| Total sequences scanned | 849,416,450 |
| Total duration | 5,924s (~98.7 min) |
| DB file | 2.6 GB |
| Filter range | 3-30 aa |
| Data sources | UniProt 102G + MGnify 120G |

## Data Source Statistics

| Source | Scanned | Written | Pass rate |
|--------|------|------|--------|
| UniProt | 225,619,586 | 733,573 | 0.33% |
| MGnify | 623,796,864 | 19,156,448 | 3.07% |

## Length Distribution

The distribution is mainly concentrated in the 20-30 aa range (long peptides dominate), which matches expectations.

| Length range | Count | Share |
|---------|------|------|
| 3-10 | 45,255 | 0.2% |
| 11-19 | 176,701 | 0.9% |
| 20-25 | 9,621,829 | 48.4% |
| 26-30 | 10,052,401 | 50.5% |

## Deduplication

The `candidates` table in DuckDB is indexed on `source + source_id` for exact deduplication. CD-HIT was not used (testing showed it is essentially ineffective for 3-30aa short peptides, with a clustering rate <5% at any threshold).

## Pipeline Status

```json
{
  "stage0_uniprot": {"status": "done", "total": 225619586, "written": 733573},
  "stage0_mgy":     {"status": "done", "total": 623796864, "written": 19156448},
  "stage0":         {"status": "done", "total": 19890021}
}
```

## Key Technical Metrics

| Item | Value |
|------|------|
| UniProt scan speed | 123k seq/s (average) |
| MGnify scan speed | 192k seq/s (average) |
| DB write batch size | 100k/batch |
| Write method | batch INSERT with VALUES clauses (10k per SQL statement) |
| Peak memory usage | ~1.8 GB RSS |

## Output Files

```
output3/
├── pipeline.db              ← 2.6G DuckDB (19.9M candidates)
├── reports/
│   └── stage0_report.md     ← automated data statistics report
└── step0/
    └── README.md            ← this file
```
