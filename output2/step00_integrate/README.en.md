> English translation of [README.md](README.md). The Chinese original is kept unchanged as the source of truth.

# Step Zero: Data Integration — Report

**Time**: 2026-05-17 15:02:47
**Duration**: 18.1 seconds
**Output directory**: output2/

## Data Sources

| File | Total rows | Antioxidant subset |
|------|--------|-----------|
| function_1.csv | 24,694 | 1,627 |
| function_2.csv | 1,055,961 | 1,055,961 |
| function_3.csv | 1,117 | 1,117 |

## Cleaning Pipeline

```
raw antioxidant total: 1,058,705
  ├─ non-standard amino acids:    42
  ├─ too short (<3aa):   113
  ├─ too long (>30aa):   1530
  ├─ valid sequences:        1,057,020
  └─ after deduplication:          1,055,116
```

## Length Distribution

```
peptide length distribution (n=1055116):
  mean:   10.7909
  median: 10.0000
  std dev: 2.9935
  min: 3.0000
  max: 30.0000
  P5: 7.0000  |  P25: 9.0000  |  P75: 12.0000  |  P95: 16.0000

  distribution histogram:
  3.0000-6.3750: ░░░░░░░░░░░░░░  (2,484 seqs, 0.2%) 
  6.3750-9.7500: █████░░░░░░░░░  (403,221 seqs, 38.2%) 
  9.7500-13.1250: ██████░░░░░░░░  (486,162 seqs, 46.1%) ← mean
  13.1250-16.5000: ██░░░░░░░░░░░░  (114,732 seqs, 10.9%) 
  16.5000-19.8750: ░░░░░░░░░░░░░░  (33,016 seqs, 3.1%) 
  19.8750-23.2500: ░░░░░░░░░░░░░░  (11,239 seqs, 1.1%) 
  23.2500-26.6250: ░░░░░░░░░░░░░░  (2,616 seqs, 0.2%) 
  26.6250-30.0000: ░░░░░░░░░░░░░░  (1,303 seqs, 0.1%) 

```

## Output

- `final/cleaned.csv` — 1,055,116 antioxidant peptides (with peptide_id, sequence, length, source)

## Next Step

Round 1 (lightweight scoring), input: `/home/lenovo/Projects/iGEM-silk/output2/step00_integrate/final/cleaned.csv`
