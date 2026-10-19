> English translation of [README.md](README.md). The Chinese original is kept unchanged as the source of truth.

# Round 1: Lightweight Scoring — Report

**Time**: 2026-05-17 15:37:20
**Duration**: 944 seconds
**Input**: 1,055,116 peptides
**Output directory**: output2/

## Scoring Services

| Service | Weight | Direction | Concurrency | Valid count |
|------|------|------|------|--------|
| AnOxPePred | 0.50 | positive (higher is better) | 10 | 1,055,116 |
| ToxinPred3 | 0.15 | negative (lower is better) | 2 | 0 |
| AlgPred2 | 0.10 | negative (lower is better) | 10 | 1,055,116 |

## Composite Score Distribution

```
composite score distribution (n=1055116):
  mean:   0.3768
  median: 0.3726
  std dev: 0.0392
  min: 0.2278
  max: 0.6132
  P5: 0.3200  |  P25: 0.3485  |  P75: 0.4012  |  P95: 0.4478

  distribution histogram:
  0.2278-0.2760: ░░░░░░░░░░░░░░  (644 seqs, 0.1%) 
  0.2760-0.3241: █░░░░░░░░░░░░░  (70,554 seqs, 6.7%) 
  0.3241-0.3723: ██████░░░░░░░░  (454,357 seqs, 43.1%) 
  0.3723-0.4205: █████░░░░░░░░░  (384,710 seqs, 36.5%) ← mean
  0.4205-0.4687: ██░░░░░░░░░░░░  (123,695 seqs, 11.7%) 
  0.4687-0.5169: ░░░░░░░░░░░░░░  (19,803 seqs, 1.9%) 
  0.5169-0.5650: ░░░░░░░░░░░░░░  (1,311 seqs, 0.1%) 
  0.5650-0.6132: ░░░░░░░░░░░░░░  (41 seqs, 0.0%) 

anoxpepred distribution (n=1055116):
  mean:   0.3244
  median: 0.3191
  std dev: 0.0460
  min: 0.1576
  max: 0.6046
  P5: 0.2586  |  P25: 0.2910  |  P75: 0.3528  |  P95: 0.4085

  distribution histogram:
  0.1576-0.2135: ░░░░░░░░░░░░░░  (525 seqs, 0.0%) 
  0.2135-0.2693: █░░░░░░░░░░░░░  (101,877 seqs, 9.7%) 
  0.2693-0.3252: ██████░░░░░░░░  (479,971 seqs, 45.5%) ← mean
  0.3252-0.3811: █████░░░░░░░░░  (348,249 seqs, 33.0%) 
  0.3811-0.4370: █░░░░░░░░░░░░░  (106,211 seqs, 10.1%) 
  0.4370-0.4929: ░░░░░░░░░░░░░░  (17,014 seqs, 1.6%) 
  0.4929-0.5487: ░░░░░░░░░░░░░░  (1,220 seqs, 0.1%) 
  0.5487-0.6046: ░░░░░░░░░░░░░░  (48 seqs, 0.0%) 

algpred2 distribution (n=1055116):
  mean:   0.3616
  median: 0.3560
  std dev: 0.0656
  min: 0.0900
  max: 0.8830
  P5: 0.2650  |  P25: 0.3190  |  P75: 0.3980  |  P95: 0.4780

  distribution histogram:
  0.0900-0.1891: ░░░░░░░░░░░░░░  (2,038 seqs, 0.2%) 
  0.1891-0.2883: ██░░░░░░░░░░░░  (114,000 seqs, 10.8%) 
  0.2883-0.3874: ████████░░░░░░  (618,779 seqs, 58.6%) ← mean
  0.3874-0.4865: ████░░░░░░░░░░  (276,734 seqs, 26.2%) 
  0.4865-0.5856: █░░░░░░░░░░░░░  (38,498 seqs, 3.6%) 
  0.5856-0.6847: ░░░░░░░░░░░░░░  (4,507 seqs, 0.4%) 
  0.6847-0.7839: ░░░░░░░░░░░░░░  (526 seqs, 0.0%) 
  0.7839-0.8830: ░░░░░░░░░░░░░░  (33 seqs, 0.0%) 

```

## Safety Flag Statistics

| Level | Count | Share |
|------|------|------|
| 🟢 normal | 1,022,267 | 96.9% |
| 🟡 caution | 32,472 | 3.1% |
| 🔴 high risk | 377 | 0.0% |
| ⚠ missing data | 0 | 0.0% |

## Top 10

| ID | Sequence | Length | Composite score | Safety flag |
|----|------|------|--------|----------|
| pep_622882 | MGMGQFPSPHHHQQQQPQHA      | 20 | 0.6132 | safe |
| pep_190781 | EAVSGEHHHHVPDHR           | 15 | 0.6014 | safe |
| pep_084749 | AVSGEHHHHVPDHR            | 14 | 0.5965 | safe |
| pep_178250 | DVRPIMHHPPNQID            | 14 | 0.5873 | safe |
| pep_985082 | VSGEHHHHVPDHR             | 13 | 0.5858 | safe |
| pep_377164 | HHHHHPPMI                 | 9 | 0.5847 | safe |
| pep_812915 | SHHHHH                    | 6 | 0.5838 | safe |
| pep_1029020 | YGYPPGPPPPPPPPPPRR        | 18 | 0.5831 | safe |
| pep_1041771 | YPPGPPPPPPPPPPR           | 15 | 0.5802 | safe |
| pep_232488 | EPFHHPPPPVPPR             | 13 | 0.5778 | safe |

## Bottom 10

| ID | Sequence | Length | Composite score | Safety flag |
|----|------|------|--------|----------|
| pep_002974 | AACEQLHQQQQQQQEETAAATLLLQ | 30 | 0.2278 | safe |
| pep_799568 | SEEKTEAAAAAAAAAAAAAAAPQPE | 27 | 0.2306 | algpred2:danger(0.709) |
| pep_799567 | SEEKTEAAAAAAAAAAAAAAAPQPE | 26 | 0.2378 | algpred2:caution(0.692) |
| pep_325891 | GIEYKPVSATGAEDK           | 15 | 0.2407 | algpred2:danger(0.725) |
| pep_799570 | SEEKTEAAAAAAAAAAAAAAAPQPE | 29 | 0.2409 | algpred2:danger(0.701) |
| pep_196724 | EEEEAAKEEKEESDDEAAVEEEEEE | 26 | 0.2412 | algpred2:caution(0.682) |
| pep_642634 | NEEADDSVTIAGK             | 13 | 0.2421 | algpred2:caution(0.509) |
| pep_895244 | TLQLLNQQEQEKEESSSEEEEEKAE | 29 | 0.2428 | safe |
| pep_799569 | SEEKTEAAAAAAAAAAAAAAAPQPE | 28 | 0.2447 | algpred2:danger(0.710) |
| pep_200459 | EEPAKEEAPAE               | 11 | 0.2462 | algpred2:danger(0.783) |

## Output

- `final/top50k.csv` — the Top 50,000 entries → Round 2
- `final/all_scored.csv` — scoring details for all 1,055,116 entries
- `final/danger_list.csv` — 377 🔴 high-risk peptides
- `scores/*_results.json` — raw responses from each service
