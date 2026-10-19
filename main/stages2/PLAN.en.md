> English translation of [PLAN.md](PLAN.md). The Chinese original is kept unchanged as the source of truth.

# Stages2 Design Plan

> A fully rebuilt screening pipeline, based on the retrospective lessons from the first full run (1,843 peptides → 90 constructs → ESMFold → OmegaFold → AF3).
>
> **Reference**: `main/PLAN.md` (the original funnel design philosophy, microservice cost analysis, GPU memory management)
> **Retrospective**: `output/REVIEW.md` (problems, lessons and data from the first round)

---

## Core differences from the first round

| Dimension | First round | Second round |
|------|--------|--------|
| **Data volume** | 1,843 entries (antioxidant subset of function.csv only) | ~**1.05M** entries (full antioxidant peptide set from function_1 + 2 + 3) |
| **Screening philosophy** | Hard filtering (absolute elimination of toxic/allergenic/hemolytic peptides) | **Score ranking** (weighted scoring across all dimensions, safety dimensions reverse-scored, no absolute elimination) |
| **Service orchestration** | Filter first → score later (filtering eliminated 94%, leaving 107 peptides to score) | **Three progressive scoring rounds** (light → medium → heavy, shrinking the candidate pool round by round) |
| **CPP prediction** | pLM4CPPs(0.15) + GraphCPP(0.05) take part in scoring | **Removed** (the antioxidant goal does not need CPPs) |
| **3D structure** | ESMFold → OmegaFold → AF3 in serial progression | **OmegaFold + ESMFold run concurrently** |
| **Length constraint** | None | **3 ≤ peptide length ≤ 30** |
| **Safety mechanism** | Hard filtering; anything above the threshold is eliminated outright | **Lenient safety flags**; extremely high-risk peptides are flagged but not removed |

---

## Data flow overview

```
                     function_1 (24,694 entries)
                     function_2 (1,055,961 entries)
                     function_3 (1,117 entries)
                            │
            ┌───────────────┴───────────────┐
            │  Data integration layer       │  ← merge, dedup, length filter (3-30aa), standard AA cleaning
            └───────────────┬───────────────┘
                            │ ~1.05M antioxidant peptides
                            ▼
           ╔═════════════════════════════════╗
           ║  Round 1: Lightweight scoring   ║  ← AnOxPePred + ToxinPred3 + AlgPred2
           ║  ~15 min, Top 50K               ║     ~10 min of actual scoring + parallel overhead
           ╚═════════════════════════════════╝
                            │
                            ▼
           ╔═════════════════════════════════╗
           ║  Round 2: Medium scoring        ║  ← +HemoPI2 + MHCflurry
           ║  ~10 min, Top 5K                ║     re-rank, add 2 services
           ╚═════════════════════════════════╝
                            │
                            ▼
           ╔═════════════════════════════════╗
           ║  Round 3: Heavy-service scoring ║  ← +BepiPred-3.0 (+ optional TemStaPro)
           ║  ~5 min, Top 80                 ║     final ranking
           ╚═════════════════════════════════╝
                            │
                            ▼
           ╔═════════════════════════════════╗
           ║  Enumeration + Construct        ║  ← Top N peptides × 2 Linkers × 3 positions
           ║  scoring (SoDoPE) +             ║     +SoDoPE → group by (peptide, linker)
           ║  group ranking                  ║     → Top groups
           ╚═════════════════════════════════╝
                            │
                            ▼
           ╔═════════════════════════════════╗
           ║  Construct-level re-scoring     ║  ← AnOxPePred + BepiPred on full length
           ║  free vs. fused activity        ║     compute change ratio, update composite score
           ╚═════════════════════════════════╝
                            │
                            ▼
           ╔═════════════════════════════════╗
           ║  Dual-model 3D prediction       ║  ← OmegaFold + ESMFold run concurrently
           ║  ≤100 constructs                ║     take the higher-confidence result
           ╚═════════════════════════════════╝
                            │
                            ▼
           ╔═════════════════════════════════╗
           ║  PDB evaluation + final report  ║  ← SASA + Aggrescan3D → final ranking
           ╚═════════════════════════════════╝
```

---

## Scoring service system

### Weight summary table (6+1 services, total = 1.00)

| Service | Weight | Direction | Category | Throughput | Round(s) | What it measures |
|------|------|------|------|------|----------|----------|
| **AnOxPePred** | **0.50** | Positive | Core function | ~200 seq/s | Round 1 | Antioxidant activity (CNN) |
| **ToxinPred3** | 0.15 | **Reverse** | Safety dimension | ~2000 seq/s | Round 1 | Toxicity prediction |
| **AlgPred2** | 0.10 | **Reverse** | Safety dimension | ~2000 seq/s | Round 1 | Allergenicity prediction |
| **HemoPI2** | 0.10 | **Reverse** | Safety dimension | ~100 seq/s | Round 2 | Hemolysis prediction |
| **MHCflurry** | 0.05 | **Reverse** | Immunogenicity | ~500 seq/s | Round 2 | MHC-I binding affinity |
| **BepiPred-3.0** | 0.10 | Positive | Immune epitope | ~50 seq/s | Round 3 | B-cell epitope potential |
| **TemStaPro** | *0.05* | Positive | Stability | ~20 seq/s | Round 3 (optional) | Thermal stability |

**Removed services** (compared with the first round):
- ~~pLM4CPPs~~ (CPP, irrelevant to the antioxidant goal)
- ~~GraphCPP~~ (CPP, and a throughput bottleneck at 30 seq/s)

**All safety dimensions are reverse-scored**: a higher raw score → after normalization `1.0 - score` → lower weighted contribution → lower rank. Extremely high-risk peptides naturally sink to the bottom, with no hard threshold.

### Throughput design logic of the three progressive rounds

| Round | Services | Candidate volume | Bottleneck service | Elapsed | Cumulative |
|------|------|--------|----------|------|------|
| R1 | AnOxPePred(200/s) + ToxinPred3(2000/s) + AlgPred2(2000/s) | 1,057,020 | AnOxPePred: 1M/200≈**83 min** | ~15 min* | ~15 min |
| R2 | + HemoPI2(100/s) + MHCflurry(500/s) | 50,000 | HemoPI2: 50K/100≈**8 min** | ~10 min | ~25 min |
| R3 | + BepiPred-3.0(50/s) | 5,000 | BepiPred: 5K/50≈**2 min** | ~5 min | ~30 min |

*\* The actual runtime of Round 1 is far shorter than 83 min, because `predict_batch` in client.py calls multiple services concurrently (it does not wait for AnOxPePred to finish before starting ToxinPred3). All three services are dispatched at once and the slowest one is awaited ≈ AnOxPePred's time. Also, the 1M entries are split into batches of 1,000, and httpx concurrency reduces network overhead.*

**Core principle**: BepiPred-3.0 (the heaviest, 50 seq/s) runs only on the 5,000 entries output by Round 2, not on all 1M. This follows the conclusion of the original PLAN.md — "keep the heavy work for the few".

---

## Safety flag system

No hard filtering threshold is set, but there are **three levels of safety flags**:

| Level | Flag | ToxinPred3 | AlgPred2 | HemoPI2 | Behavior |
|------|------|-----------|----------|---------|------|
| 🟢 Normal | `safe` | < 0.60 | < 0.50 | < 0.70 | No flag |
| 🟡 Caution | `caution` | 0.60-0.80 | 0.50-0.70 | 0.70-0.85 | Flagged in the ranking table |
| 🔴 High risk | `danger` | ≥ 0.80 | ≥ 0.70 | ≥ 0.85 | Flagged + listed separately in the README |

**These flags do not affect the ranking computation**; the safety services naturally push the ranking down through "reverse scoring". The flags are provided in the report for reference only — if a peptide has an extremely high AnOxPePred score but is high-risk on ToxinPred3, the user can see it.

Only extreme cases get a 🔴, avoiding the first round's problem where AlgPred2 at a 0.30 threshold wrongly killed 58%.

---

## Detailed design of each stage

### Round 1: Lightweight scoring (`round01_lightweight.py`)

**Preconditions**: data has been integrated (function_1 + 2 + 3 merged, deduplicated, length-filtered, standard-AA-cleaned)

**Services involved**:
- AnOxPePred (antioxidant core, weight 0.50)
- ToxinPred3 (toxicity, reverse, weight 0.15)
- AlgPred2 (allergenicity, reverse, weight 0.10)

**Execution flow**:
1. Load the 1.05M candidate peptides and assign a `peptide_id` to each
2. Submit `predict_batch` to the 3 services concurrently (automatically split into batches of 1,000)
3. Collect the results and compute the weighted composite score
4. Safety flags: check the score of each safety service and assign a `safe`/`caution`/`danger` flag
5. Sort by composite score in descending order and take the **Top 50,000**

**Output**:
```
output/round01_lightweight/
├── README.md              ← score distribution, Top 20 showcase, safety flag statistics
├── run.log
├── scores/                ← raw returns from each service
├── final/passed.csv       ← Top 50,000 (with composite score + safety flags)
└── final/danger_list.csv  ← 🔴 high-risk peptides listed separately
```

**Expected elapsed time**: ~15 minutes (concurrent calls, live network round trips)
**Expected safety flag distribution**: ~1-5% 🔴 (about 10,000-50,000 entries)

---

### Round 2: Medium scoring (`round02_medium.py`)

**Preconditions**: Round 1 is complete and the scoring data for the Top 50,000 exists

**Additional services**:
- HemoPI2 (hemolysis, reverse, weight 0.10)
- MHCflurry (MHC-I, reverse, weight 0.05)

**Execution flow**:
1. Read the Top 50,000 from Round 1
2. Additionally call HemoPI2 + MHCflurry (only on the 50K)
3. Merge the 3 scores from Round 1 and recompute the composite score with the 5-service weights
4. Update the safety flags (HemoPI2 is now included)
5. Sort by composite score in descending order and take the **Top 5,000**

**Output**:
```
output/round02_medium/
├── README.md              ← ranking changes, score distribution of the new services
├── run.log
├── scores/                ← raw returns from HemoPI2 + MHCflurry
├── final/passed.csv       ← Top 5,000 (with scores from all 5 services)
└── final/rank_changes.csv ← rank changes relative to Round 1
```

**Expected elapsed time**: ~10 minutes

---

### Round 3: Heavy-service scoring (`round03_heavy.py`)

**Preconditions**: Round 2 is complete and the scoring data for the Top 5,000 exists

**Additional services**:
- BepiPred-3.0 (B-cell epitope, weight 0.10)
- TemStaPro (thermal stability, weight *0.05*, optional — run if ready, otherwise skip, set its weight to zero and renormalize)

**Execution flow**:
1. Read the Top 5,000 from Round 2
2. Additionally call BepiPred-3.0 (+ TemStaPro if available)
3. Recompute the final composite score with all 6 (or 7) services
4. Take the **Top 80** by composite score
5. Generate a complete scoring report (all service scores, safety flags, ranking trajectory)

**Output**:
```
output/round03_heavy/
├── README.md              ← final ranking report, Top 20 showcase
├── run.log
├── scores/                ← raw returns from BepiPred and others
├── final/
│   ├── top80.csv          ← final Top 80 peptides
│   ├── all_scored.csv     ← scoring details for all 5,000 entries
│   ├── trajectory.csv     ← cross-round rank changes (R1→R2→R3)
│   └── danger_list.csv    ← final list of 🔴 high-risk peptides
```

**Expected elapsed time**: ~5 minutes (without TemStaPro), ~10 minutes (with TemStaPro)

---

### Stage 4: Enumeration + construct scoring + re-evaluation (`stage04_enumerate.py`)

**Preconditions**: Round 3 is complete and the Top 80 peptides exist

**Enumeration parameters**:
- **Number of preferred peptides**: take the Top 20 (configurable, but no more than the Top 80)
- **Linkers**: select 2-4 kinds from linker.fasta (flexible GGGGSx1/x2 + other selected ones)
- **Position schemes**: N-terminus / C-terminus / both ends (3 kinds)
- **Output cap**: ≤100 constructs enter 3D prediction

**Construct sequence construction**:
```
N-terminus: [functional peptide] + [Linker] + [silk fibroin core] + [His6]
C-terminus: [silk fibroin core] + [Linker] + [functional peptide] + [Linker] + [His6]
Both ends:  [functional peptide] + [Linker] + [silk fibroin core] + [Linker] + [functional peptide] + [Linker] + [His6]
```

**SoDoPE scoring**: solubility prediction for each construct (<1 ms per entry, extremely fast)

**Group ranking logic** (reusing the strategy validated in the first round):
1. Group by `(peptide_id, linker_id)`, 3 positions per group
2. Take the highest composite score within a group to represent that group
3. Sort the groups and select the Top K groups
4. Output all 3 positions of each group → enter 3D prediction

**Group composite score formula**:
```
G-FASTA composite = peptide composite (Round 3) × 0.60 + SoDoPE × 0.30 + TemStaPro × 0.10 (if available)
```

**Adaptive control**: adjust K so that the number of constructs entering 3D is ≤ 100.
- K=33 → 99 constructs (20 peptides × 2 Linkers may not be enough? In practice there are only 40 groups, so all of them can go)

**Construct-level re-scoring sub-flow** (after SoDoPE):

1. Take all candidate constructs (≤100 entries) and submit them to **AnOxPePred + BepiPred-3.0** concurrently
2. Compute the **activity change ratio** for each construct:

```
change ratio = construct_service_score / peptide_service_score (from Round 3)
```

3. Update the group composite score with the re-scoring, and output **context_effect.csv** (free vs. fused comparison table)

**Output**:
```
output/stage04_enumerate/
├── README.md
├── run.log
├── scores/
│   ├── all_ranked.csv        ← scoring details for all constructs
│   ├── context_effect.csv    ← free vs. fused activity change comparison
│   └── per_service/          ← raw returns from each service
├── final/
│   ├── constructs.csv        ← scoring details for all constructs
│   ├── topN.fasta            ← FASTA of the N constructs → 3D prediction
│   ├── topN.csv              ← scoring details
│   └── stage5_input.json     ← Stage 5 configuration
```

**Expected elapsed time**: <1 second (enumeration) + <1 second (SoDoPE) + ~2-5 minutes (construct-level AnOxPePred + BepiPred)

---

### Stage 5: Dual-model 3D structure prediction (`stage05_fold.py`)

**Preconditions**: Stage 4 is complete and the FASTA of ≤100 constructs exists

**Core change**: submit all constructs to OmegaFold and ESMFold at the same time and take the higher-confidence result.

**Concurrency strategy**:

| Service | Concurrency | Time per structure | GPU memory | Total time (100 entries) |
|------|------|----------|------|-----------------|
| ESMFold | 3 | ~2 min | ~8 GB × 3 = 24 GB | ~67 min |
| OmegaFold | 3 | ~1 min | ~8 GB × 3 = 24 GB | ~34 min |

**Running the two services at the same time** means a GPU memory conflict — ESMFold and OmegaFold each need about 24 GB (concurrency 3). With 48 GB of GPU memory, **both can run at once**, but each service can only use concurrency 2 instead of 3, giving roughly:
- ESMFold (concurrency 2): 100 × 2 min / 2 = 100 min
- OmegaFold (concurrency 2): 100 × 1 min / 2 = 50 min
- Both running concurrently ≈ **100 min** (the slower one, ESMFold, dominates)

If GPU memory is insufficient, run them in series: finish OmegaFold first (~34 min), then ESMFold (~67 min), for ~101 min total. In practice the total time under asynchronous concurrent scheduling is about the same.

**Output strategy**:
- For each construct, wait for both the ESMFold and OmegaFold results
- Take the PDB with the higher pLDDT as the "best structure"
- Constructs where both fail are rescued separately with AlphaFold3 (limited to the Top 3, ~80 min per entry)

**Checkpoint mechanism** (reusing the first round's experience): save a checkpoint every 5 completed constructs, so the run can resume after a crash.

**Output**:
```
output/stage05_fold/
├── README.md
├── run.log
├── pdb_esmfold/           ← PDBs generated by ESMFold
├── pdb_omegafold/         ← PDBs generated by OmegaFold
├── pdb_best/              ← best PDB per construct (higher of the two)
├── scores/
│   ├── esmfold_plddt.csv
│   ├── omegafold_plddt.csv
│   └── comparison.csv     ← dual-model pLDDT comparison
├── checkpoint.json
├── final/
│   ├── best_structures.csv
│   └── stage6_input.json
```

**pLDDT quality assessment**:
| pLDDT range | ESMFold assessment | OmegaFold assessment (0-100) | Action |
|-----------|-------------|----------------------|------|
| ≥ 0.70 / ≥ 70 | High confidence | High confidence | Use directly |
| 0.50-0.70 / 50-70 | Trustworthy | Trustworthy | Use, flag as "medium confidence" |
| < 0.50 / < 50 | Low confidence | Low confidence | Flag, consider AF3 validation |

**Expected elapsed time**: ~100 minutes (100 constructs, concurrency 2+2)

---

### Stage 6: PDB evaluation + final report (`stage06_pdb_eval.py`)

**Preconditions**: Stage 5 is complete and the best PDB files exist

**Evaluation services**:
- **SASA** (solvent-accessible surface area, CPU, 1-5 s per entry, concurrency 10): evaluates functional peptide exposure
- **Aggrescan3D** (aggregation propensity, CPU Docker, 1-15 min per entry, concurrency 2): evaluates aggregation risk

**Composite scoring**:
```
final_score = composite_score(Stage 4) × 0.60 + SASA × 0.40
Aggrescan3D is for reference only and is not included in the weighting
```

**Output**: a final ranking report containing scores for all dimensions (peptide score × 5-6 services + SoDoPE + ESMFold pLDDT + OmegaFold pLDDT + SASA + Aggrescan3D).

**Expected elapsed time**: SASA ~2 min + Aggrescan3D ~25-60 min

---

## Three-round ranking trajectory

The rank change of each peptide across the three rounds is an important quality signal:

```
Peptide XXX:
  Round 1 rank: 12/1,057,020  (3 services only)
  Round 2 rank: 8/50,000      (+HemoPI2 + MHCflurry)
  Round 3 rank: 3/5,000       (+BepiPred-3.0)
  Conclusion: rank rises steadily; all dimensions agree ✅

Peptide YYY:
  Round 1 rank: 15/1,057,020
  Round 2 rank: 4,218/50,000  (HemoPI2 hemolysis score very high, so reverse scoring drops it sharply)
  Round 3 rank: eliminated
  Conclusion: good antioxidant but high hemolysis risk, naturally eliminated ✅
```

This trajectory analysis is generated automatically in the final report.

---

## Per-round statistical report specification

The README.md output by each round must contain the following statistics, so that the data distribution is transparent and traceable.

### Core statistics

**Composite score distribution table** (computed over all candidate peptides):

```
Composite score distribution (n=50000):
  mean:     0.3724
  median:   0.3681
  std dev:  0.0823
  min:      0.1124
  max:      0.6831
  P5:       0.2341  |  P25: 0.3012  |  P75: 0.4421  |  P95: 0.5214
```

### Distribution histogram

```
  0.0-0.1: ██░░░░░░░░░░  (450 entries,    0.9%)
  0.1-0.2: ██████░░░░░░  (2,891 entries,  5.8%)
  0.2-0.3: ████████████  (12,450 entries, 24.9%)
  0.3-0.4: ████████████  (19,234 entries, 38.5%)  ← mean
  0.4-0.5: ████████░░░░  (11,023 entries, 22.0%)
  0.5-0.6: ████░░░░░░░░  (4,512 entries,   9.0%)
  0.6-0.7: ██░░░░░░░░░░  (1,234 entries,   2.5%)
  0.7+:    ░░░░░░░░░░░░  (206 entries,     0.4%)
```

The histogram bins adapt to the data range so that 6-10 intervals are displayed. Bars are filled proportionally with the character blocks `█` (solid) and `░` (blank), with a fixed total width of 14 characters.

### Individual distribution for each service

Also output a separate distribution for each scoring service, to make it easy to spot an anomalous service:

```
AnOxPePred distribution (n=50000):
  mean: 0.3412, std dev: 0.1124, median: 0.3289
  P5: 0.1421  P25: 0.2612  P75: 0.4223  P95: 0.5342
  [histogram]

ToxinPred3 distribution (n=50000):
  mean: 0.2841, std dev: 0.1532, ...
  [histogram]
```

### Top / Bottom showcase

- **Top 10** peptides: rank, ID, composite score, per-service scores, safety flags
- **Bottom 10** peptides: same as above
- **Before/after comparison**: if inherited from the previous round, show the ±10 entries with the largest rank changes

---

## Construct-level re-scoring (within Stage 4)

### Motivation

A peptide's score in the free state (AnOxPePred, etc.) measures its **intrinsic activity**. But once fused onto the silk fibroin scaffold, the conformational environment may change how it performs. If a peptide has a high free-state score but its construct score drops significantly, the scaffold context is suppressing its activity — an important ranking signal.

### Scope of applicability

Not every service is suitable for running on a full-length construct. Judging by each model's training data:

| Service | Full-length applicability | Rationale |
|------|-----------|------|
| **AnOxPePred** ✅ | **Applicable** | The CNN is based on sequence features (amino acid composition + position); although the meaning differs on a full-length sequence, it can still reflect contextual activity |
| **BepiPred-3.0** ✅ | **Applicable** | ESM-2 650M is pretrained on whole proteins, so long sequences are natively supported |
| **TemStaPro** ✅ | **Applicable** | ProtT5-XL 3B whole-protein model, already used on proteins of hundreds of amino acids |
| SoDoPE | ✅ Already done | Dipeptide lookup table, already run after enumeration |
| MHCflurry ❌ | **Not applicable** | Trained on 9-11 aa MHC motifs |
| ToxinPred3 ❌ | **Not applicable** | Trained on short toxin peptides |
| AlgPred2 ❌ | **Not applicable** | Same as above |
| HemoPI2 ❌ | **Not applicable** | Same as above |

### Execution flow

After Stage 4 enumerates the constructs, append the following after SoDoPE scoring:

1. Take all candidate constructs (≤100 entries) and submit them to **AnOxPePred** and **BepiPred-3.0**
2. For each construct, compute the **activity change ratio**:

```
AnOxPePred_change_ratio = construct_AnOxPePred / peptide_AnOxPePred (from Round 3)
BepiPred_change_ratio   = construct_BepiPred  / peptide_BepiPred  (from Round 3)
```

- change ratio > 1.0 → activity is enhanced after fusion
- change ratio ≈ 1.0 → unaffected by the scaffold
- change ratio < 0.8 → **significant drop**, flag a warning

3. Update the group composite score (incorporating the construct-level re-scoring):

```
G-FASTA composite (R2) = peptide composite (Round 3) × 0.40
                       + SoDoPE × 0.25
                       + construct_AnOxPePred × 0.20
                       + construct_BepiPred × 0.10
                       + TemStaPro × 0.05 (if available)
```

The SoDoPE weight drops from 0.30 to 0.25, freeing weight for construct-level AnOxPePred (0.20) and BepiPred (0.10). The peptide composite score drops from 0.60 to 0.40.

4. Output **context_effect.csv**: free-state score vs. construct score per peptide, sorted by change ratio. At a glance you can see which peptides perform stably on the scaffold and which have their activity suppressed.

### Expectations

- Most peptides score slightly lower at the construct level than at the peptide level (the scaffold has a dilution effect)
- If a peptide's change ratio is < 0.7, consider flagging "scaffold activity suppression" in the report
- If all peptides have similar change ratios (for example, all within 0.8-1.2), the scaffold's effect on functional peptides is uniform and this metric need not be used for ranking

---

## Output directory structure

```
output/
├── STATUS.md                 ← pointer to the latest progress
├── status/                   ← timestamped status snapshots
├── REVIEW.md                 ← full retrospective (already exists from round 1; round 2 appends to it)
│
├── round01_lightweight/      ← Round 1 output
├── round02_medium/           ← Round 2 output
├── round03_heavy/            ← Round 3 output
├── stage04_enumerate/        ← Stage 4 output
├── stage05_fold/             ← Stage 5 output (dual model)
├── stage06_pdb_eval/         ← Stage 6 output
│
└── final_output/             ← final package (a separate folder for each Top N construct)
```

**Each stage directory contains**: `README.md` (report), `run.log` (log), `final/` (output data), `scores/` (raw scores)

---

## Context management

Follows the context management strategy of section 9 of the original PLAN.md:

- **STATUS.md** — anchor for the latest status, updated at the end of every stage
- **status/status_YYYY-MM-DD_HHMM.md** — timestamped snapshots
- **README.md for each stage** — what was done, why, and what the result was
- **The file system is the memory** — Claude remembers paths, not data

Independent script design: each script can run on its own, e.g. `python -m main.stages2.round01_lightweight`, without depending on an orchestrator.

---

## Implementation order (one step at a time)

| Step | Content | Depends on | Estimated effort |
|------|------|------|----------|
| 1 | Data integration layer: merge function_1/2/3, dedup, length filter, standard AA cleaning | None | One-off |
| 2 | Round 1 lightweight scoring + safety flag script | Step 1 | 1-2 iterations |
| 3 | Round 2 medium scoring script | Step 2 | 1-2 iterations |
| 4 | Round 3 heavy-service scoring script | Step 3 | 1-2 iterations |
| 5 | Stage 4 enumeration + construct scoring | Step 4 | One-off |
| 6 | Stage 5 dual-model 3D prediction | Step 5 | 2-3 iterations |
| 7 | Stage 6 PDB evaluation + final report | Step 6 | 1 iteration |

Each step produces usable intermediate results; adjust and then continue to the next step.
