> English translation of [PLAN2.md](PLAN2.md). The Chinese original is kept unchanged as the source of truth.

# Stages2 Pipeline Plan (PLAN2) — v2 revision

> **Goal**: re-run the complete stages2 pipeline, write to `output2/`, fix the bugs in the original scripts, and add Bottom-N.
>
> **Key changes (v2)**:
> 1. Round 1 **does not run ToxinPred3** (1.05M entries are too slow, ~22h); instead it is run later on the 50K in Round 2
> 2. Round 2 **splits by pure antioxidant score** into top25K + bottom25K, then runs the 3 safety services
> 3. Round 3 **runs the heavy services on the 50K** (originally 10K → expanded to 50K with dual channels)
> 4. The weighted composite score formula is recorded as a fixed definition for uniform downstream use

---

## Core differences from the original scripts

| Dimension | Original stages2 scripts | PLAN2 fixed version (v2) |
|------|----------------|-------------------|
| **Output directory** | `output/` | **`output2/`** |
| **Utility functions** | Copy-pasted 8 times in every script | Centrally managed in `common.py` |
| **Split strategy** | Sort by weighted composite score (antioxidant + safety mixed) | **Split by pure AnOxPePred score**, taking top25K + bottom25K |
| **ToxinPred3** | Forced through 1.05M entries in Round 1 (~22h) | **Deferred to Round 2 on 50K** (~48 min, acceptable) |
| **Round 3 input** | 10K entries | **50K entries** (top25K + bottom25K, dual-channel) |
| **Round 4 scoring** | SoDoPE only | Adds full-length AnOxPePred + BepiPred3 scoring |
| **Resume from checkpoint** | None | checkpoint.json |
| **Concurrency control** | All `CONCURRENT_CHUNKS=10` | Tuned per service (ToxinPred3=2, others=10) |
| **Exception safety** | Some places missing `return_exceptions=True` | Uniform two-layer exception isolation |
| **Docker orchestration** | Manual | `docker_utils.py` brought in from stages3 |

---

## Data flow overview

```
                     function_1 (24,694 entries)
                     function_2 (1,055,961 entries)
                     function_3 (1,117 entries)
                            │
                     ┌──────┴──────┐
                     │   Step 0    │  ← merge, dedup, length filter (3-30aa)
                     └──────┬──────┘
                            │ ~1.05M entries
                            ▼
              ╔═════════════════════════════╗
              ║  Round 1: Lightweight       ║  ← AnOxPePred + AlgPred2 (no ToxinPred3)
              ║  1.05M → full scoring       ║     sort by pure anoxpepred, ready for the split
              ╚═════════════════════════════╝
                            │
                            ▼
              ╔════════════════════════════════════════╗
              ║  Round 2: Split + safety scoring       ║
              ║  ① by anoxpepred: top25K + bottom25K   ║
              ║  ② run ToxinPred3 + HemoPI2 + MHCflurry║
              ╚════════════════════════════════════════╝
                            │ 50K entries (with dual-channel labels)
                            ▼
              ╔═══════════════════════════════╗
              ║  Round 3: Heavy-service       ║
              ║  BepiPred3 + TemStaPro        ║
              ║  50K → top N + bottom M       ║
              ╚═══════════════════════════════╝
                           ╱╲
                          ╱  ╲
                         ╱    ╲
                        ▼      ▼
            ╔══════════════╗  ╔══════════════════╗
            ║ Round 4a:    ║  ║ Round 4b:        ║
            ║ Top enum     ║  ║ Bottom enum      ║
            ╚══════════════╝  ╚══════════════════╝
                        ▼      ▼
              ╔═══════════════════════════╗
              ║  Round 5: 3D structure    ║  ← ESMFold + OmegaFold
              ║  Dual-model concurrent    ║     all constructs treated alike
              ╚═══════════════════════════╝
                            │
                            ▼
              ╔═══════════════════════════╗
              ║  Round 6: PDB evaluation  ║  ← SASA + Aggrescan3D
              ╚═══════════════════════════╝
                            │
                            ▼
              ╔═══════════════════════════╗
              ║  Round 7: Final output    ║  ← Top + Bottom dual ranking
              ║  two rankings + report    ║
              ╚═══════════════════════════╝
```

---

## Output directory structure

```
output2/
├── STATUS.md                        ← pointer to the latest progress
│
├── step00_integrate/                ← Step 0: data integration (cleaned.csv, 1.05M entries)
├── round01_lightweight/             ← Round 1: AnOxPePred + AlgPred2 (full scoring)
│   └── final/
│       ├── all_scored.csv           ← all 1.05M entries (with per-service scores)
│       └── top50k.csv              ← sorted by weighted score (for reference only)
├── round02_scoring/                 ← Round 2: split + ToxinPred3/HemoPI2/MHCflurry
│   └── final/
│       ├── all_50k.csv             ← all 50K (top25K+bottom25K+5 service scores+channel)
│       ├── top25k.csv
│       └── bottom25k.csv
├── round03_heavy/                   ← Round 3: BepiPred3 + TemStaPro heavy services
│   └── final/
│       ├── top80.csv               ← construct candidates selected from the Top channel
│       └── bottom10.csv            ← negative controls selected from the Bottom channel
├── round04_enumerate/               ← Round 4: enumeration + construct-level scoring
├── round05_3d/                      ← Round 5: ESMFold + OmegaFold 3D
├── round06_pdb_eval/               ← Round 6: SASA + Aggrescan3D
│
└── round07_final/                   ← Round 7: final dual-channel output
    ├── README.md                    ← full-pipeline report
    ├── top_ranking.csv              ← Top constructs (composite score → SASA ranking)
    ├── top10_summary.csv
    ├── bottom_ranking.csv           ← Bottom constructs
    ├── bottom10_summary.csv
    ├── score_distribution.json
    └── constructs/                  ← a separate folder for each construct
```

---

## Bottom-N: the worst antioxidant peptides with normal safety dimensions

### Motivation

The main pipeline ranks by weighted composite score, where antioxidant activity (AnOxPePred) has a weight of 0.50 and dominates the ranking. But during wet-lab validation, besides the "best" candidates, one sometimes also needs "worst but safe" controls — that is, peptides that perform well on every safety dimension but have the lowest antioxidant activity.

These peptides can serve as:
1. **Negative controls**: compared against the Top peptides to validate the dynamic range of the antioxidant activity assay
2. **Safety boundary validation**: confirming that even the peptides with the worst antioxidant activity are still safe on their other properties
3. **Unexpected findings**: some peptides may score low on AnOxPePred (a CNN model) yet actually have other activities that the model does not capture

### Screening logic

After obtaining all 7 service scores in Round 3, run the Bottom-N screening in parallel:

```
From the 10,000 scored peptides:
  1. Safety filters (all must pass):
     - ToxinPred3 < 0.60 (safe)
     - AlgPred2   < 0.50 (safe)
     - HemoPI2    < 0.70 (safe)
     - MHCflurry  < 0.50 (low immunogenicity)
     - BepiPred3  < 0.60 (low B-cell epitope risk)
     - (TemStaPro > 0.30 if available, stability acceptable)
  2. Sort by AnOxPePred in ascending order (antioxidant activity from low to high)
  3. Take the Bottom 10 (worst antioxidant activity but safe on the other dimensions)
```

### Downstream flow

The Bottom 10 peptides go through exactly the same downstream flow as the Top 80 peptides:
- Round 4: enumeration (×2 Linkers × 3 positions = 60 constructs) + SoDoPE + construct-level re-score
- Round 5: ESMFold + OmegaFold 3D prediction
- Round 6: SASA + Aggrescan3D evaluation
- Round 7: Bottom ranking output separately and displayed alongside the Top ranking

This way, the final Round 7 report clearly shows:
```
─────────────────────────────────────
  Top 10 (highest composite score, AnOxPePred-dominated)
─────────────────────────────────────
  1. pep_000142 | AnOxPePred=0.89 | composite=0.72
  2. pep_000831 | AnOxPePred=0.87 | composite=0.70
  ...

─────────────────────────────────────
  Bottom 10 (safe but lowest AnOxPePred)
─────────────────────────────────────
  1. pep_003214 | AnOxPePred=0.12 | ToxinPred3=0.21 | HemoPI2=0.34 ← lowest antioxidant but safe
  2. pep_008912 | AnOxPePred=0.15 | ToxinPred3=0.18 | HemoPI2=0.29
  ...
```

---

## Detailed changes per round

### Step 0: data integration (`step00_integrate.py`)

**Differences from the original script**:
- Only change: output directory from `output/` → `output2/`
- Imports the utility functions from `common.py` instead of local copies
- Data logic unchanged

**Input**: `data/function_1.csv`, `data/function_2.csv`, `data/function_3.csv`
**Output**: `output2/step00_integrate/final/cleaned.csv` (~1.05M entries)
**Dependencies**: none
**Estimated time**: ~30s

---

### Round 1: lightweight scoring (`round01_lightweight.py`)

**Differences from the original script**:
- Outputs to `output2/`
- Uses `common.py`
- **Does not run ToxinPred3** — running 1.05M entries through sklearn's ExtraTreesClassifier would take ~22 hours, so it is deferred to Round 2 on the 50K
- Concurrency tuned per service: AnOxPePred=10, AlgPred2=10
- Uniform `asyncio.gather` exception safety
- Outputs `all_scored.csv` (full scoring) for the Round 2 split

**Services**: AnOxPePred(0.50) + AlgPred2(0.10)
**Input**: `output2/step00_integrate/final/cleaned.csv` (~1.05M entries)
**Output**:
- `final/all_scored.csv` — scoring details for all 1.05M entries
- `final/top50k.csv` — Top 50K sorted by weighted composite score (for reference only; Round 2 does not use this ordering)
**Dependencies**: Step 0
**Estimated time**: ~15 min

---

### Round 2: split + safety scoring (`round02_scoring.py`)

**v2 changes (completely different from the original PLAN2!)**:
- **Split by pure antioxidant score**: read `all_scored.csv` and sort by the raw `anoxpepred` score in descending order
  - Top 25K: the 25,000 entries with the best antioxidant activity
  - Bottom 25K: the 25,000 entries with the worst antioxidant activity (negative controls)
  - Discards the Round 1 weighted composite score ordering
- **Runs ToxinPred3 at this point**: because Round 1 skipped the full set, it runs here on the 50K alone (concurrency 2)
- **Adds HemoPI2 + MHCflurry** (concurrency 10 each)
- **Retains the AlgPred2 scores** (from Round 1)
- **Computes and records the composite score**: the 5-service weights are recorded as fixed values in the script
```
weighted_score = Σ(normalized_i × weight_i) / Σ(weight_i)
  positive: anoxpepred (0.50)
  reverse:  toxinpred3 (0.15) + algpred2 (0.10) + hemopi2 (0.10) + mhcflurry (0.05)
```
- **Output carries a channel label** (top/bottom) that propagates through all later rounds

**Input**: `output2/round01_lightweight/final/all_scored.csv` (full scoring of 1.05M entries)
**Output**:
- `final/all_50k.csv` — all 50K (top25K + bottom25K + 5 service scores + composite score + safety flags + channel label)
- `final/top25k.csv` — Top 25K
- `final/bottom25k.csv` — Bottom 25K
**Dependencies**: Round 1
**Estimated time**: ~50 min (ToxinPred3 is the bottleneck)

---

### Round 3: heavy-service scoring (`round03_heavy.py`)

**v2 changes**:
- **Input expanded from 10K to 50K** (top25K + bottom25K, dual-channel)
- **Selects top N and bottom M per channel**:
  - Top channel: take the first N entries by composite score within the top25K
  - Bottom channel: apply the safety filters within the bottom25K → take the M entries with the worst antioxidant activity
- Adds BepiPred-3.0(0.07) + TemStaPro(0.05)
- `asyncio.wait_for` cannot interrupt C extensions → switched to socket-level timeouts

**Services**: adds BepiPred-3.0(0.07) + TemStaPro(0.05)
**Input**: `output2/round02_scoring/final/all_50k.csv`
**Output**:
- `output2/round03_heavy/final/top80.csv` — Top 80 by composite score in the Top channel
- `output2/round03_heavy/final/bottom10.csv` — Bottom channel after safety filtering, taking the 10 entries with the worst antioxidant activity
- `output2/round03_heavy/final/all_scored.csv` — scoring details for all 50K
**Dependencies**: Round 2
**Estimated time**: depends on service concurrency performance

---

### Round 4: enumeration + construct scoring (`round04_enumerate.py`)

**Differences from the original script**:
- Outputs to `output2/`
- Uses `common.py`
- **New: construct-level re-score** — after enumeration, run AnOxPePred + BepiPred3 on the full-length constructs,
  compute the activity change ratio (construct_score / peptide_score), and update the composite score
- **Top + Bottom dual-channel enumeration** — the first 40 entries from the Top 80 plus all 10 Bottom entries, enumerated separately
- Group ranking logic identical to the original script (group by peptide × linker, take the highest score within a group)

**Construct-level scoring formula** (from the original PLAN.md but never implemented):
```
composite (R2) = peptide composite (Round 3) × 0.40
               + SoDoPE × 0.25
               + construct_AnOxPePred × 0.20
               + construct_BepiPred × 0.10
               + TemStaPro × 0.05 (if available)
```

**Activity change ratio**:
```
AnOxPePred_change_ratio = construct_AnOxPePred / peptide_AnOxPePred (from Round 3)
BepiPred_change_ratio   = construct_BepiPred  / peptide_BepiPred  (from Round 3)
change ratio > 1.0 → activity is enhanced after fusion
change ratio ≈ 1.0 → unaffected by the scaffold
change ratio < 0.8 → significant drop, flag a warning
```

**Enumeration parameters**:
- Top channel: 40 peptides × 2 Linkers × 3 positions = 240 constructs → group ranking → Top groups
- Bottom channel: 10 peptides × 2 Linkers × 3 positions = 60 constructs → group ranking → Bottom groups
- Construct cap: ≤100 (the two channels combined do not exceed this; roughly 80% top + 20% bottom)

**Input**:
- `output2/round03_heavy/final/top80.csv`
- `output2/round03_heavy/final/bottom10.csv`
- `data/silk.fasta`
- `data/linker.fasta`

**Output**:
- `output2/round04_enumerate/final/constructs_top.csv` — Top constructs
- `output2/round04_enumerate/final/constructs_bottom.csv` — Bottom constructs
- `output2/round04_enumerate/final/all_constructs.csv` — all of them
- `output2/round04_enumerate/final/all_constructs.fasta` — all of them, entering 3D
- `output2/round04_enumerate/final/context_effect.csv` — free vs. fused activity change

**Dependencies**: Round 3
**Estimated time**: ~5 min

---

### Round 5: 3D structure prediction (`round05_3d.py`)

**Differences from the original script**:
- Outputs to `output2/`
- Uses `common.py`
- **Brings in `docker_utils.py`** (adapted from stages3) instead of manual service management
- Retains the OmegaFold Docker bridge IP detection (`_fix_omegafold_docker_network()`, a pattern validated by the original script)
- Fixes the bug where the original script killed the structure service itself
- All constructs (top + bottom) are processed uniformly, with no distinction

**Services**: ESMFold(port 8203) + OmegaFold(port 8204)
**Input**: `output2/round04_enumerate/final/all_constructs.fasta`
**Output**: `output2/round05_3d/constructs/con_XXXX/` (a separate folder per construct)
**Dependencies**: Round 4
**Estimated time**: ~2h (90 constructs, concurrency 2+2)

---

### Round 6: PDB evaluation (`round06_pdb_eval.py`)

**Differences from the original script**:
- Outputs to `output2/`
- Uses `common.py`
- Fixes the output file name: writes `sasa_ranking.csv` (consistent with what round07 expects)
- Uses `docker_utils.py` to make sure SASA + Aggrescan3D are ready

**Services**: SASA(port 8101) + Aggrescan3D(port 8102)
**Input**: `output2/round05_3d/constructs/con_XXXX/`
**Output**: `output2/round06_pdb_eval/final/sasa_ranking.csv`
**Dependencies**: Round 5
**Estimated time**: ~3 min

---

### Round 7: final output (`round07_final.py`)

**Differences from the original script**:
- Outputs to `output2/`
- Uses `common.py`
- Fixes the original script reading `final_ranked_sasa.csv` (which does not exist) → reads `sasa_ranking.csv` (already fixed)
- Fixes the round labels in the README (the original script displayed stages1's labels, all wrong)
- **Adds a Bottom ranking** — displayed alongside the Top ranking, each with its own independent ranking

**Ranking criterion**:
- Top ranking: by SASA exposure from high to low (same as the original design)
- Bottom ranking: by SASA exposure from high to low (same criterion as Top, ranked independently)

**Input**: `output2/round06_pdb_eval/final/sasa_ranking.csv`
**Output**:
```
output2/round07_final/
├── README.md                     ← full-pipeline report (with Top + Bottom comparison table)
├── top_ranking.csv               ← Top constructs ranking
├── top10_summary.csv             ← condensed Top 10 table
├── bottom_ranking.csv            ← Bottom constructs ranking
├── bottom10_summary.csv          ← condensed Bottom 10 table
├── score_distribution.json       ← distribution of each score dimension
└── constructs/                   ← a separate folder for each construct
```
**Dependencies**: Round 6
**Estimated time**: ~1s

---

## Script list and writing order

The following are all the scripts involved in PLAN2, listed in writing order (foundation first, then applications):

| # | File name | Description | New/Modified |
|---|--------|------|-----------|
| 1 | `main/stages2/common.py` | **Shared utility module**: log, describe, make_dir, write_json, calc_safety_flag, checkpoint read/write | **New** |
| 2 | `main/stages2/step00_integrate.py` | Data integration (reuse the existing logic, switch to common.py, change output to output2/) | **Rewritten** |
| 3 | `main/stages2/round01_lightweight.py` | Round 1 rewritten (checkpoints, per-service concurrency, fixed output names) | **Rewritten** |
| 4 | `main/stages2/round02_scoring.py` | Round 2 rewritten (do not move ToxinPred3, fix input names, checkpoints) | **Rewritten** |
| 5 | `main/stages2/round03_heavy.py` | Round 3 rewritten (checkpoints, new Bottom-N, fixed timeout handling) | **Rewritten** |
| 6 | `main/stages2/round04_enumerate.py` | Round 4 rewritten (construct re-score, Top+Bottom dual-channel) | **Rewritten** |
| 7 | `main/stages2/round05_3d.py` | Round 5 rewritten (docker_utils, fixed the bug that killed itself) | **Rewritten** |
| 8 | `main/stages2/round06_pdb_eval.py` | Round 6 rewritten (fixed output file name, docker_utils) | **Rewritten** |
| 9 | `main/stages2/round07_final.py` | Round 7 rewritten (fixed labels, Bottom ranking, fixed file names) | **Rewritten** |

**External dependencies** (reused from stages3, unchanged):
- `main/stages3/docker_utils.py` — on-demand startup of Docker microservices
- `main/stages3/service_map.py` — service dependency map (need to confirm whether it can be reused directly, or whether a simplified version should be created for stages2)

---

## Execution plan

### Phase 1: write all scripts ✅

All scripts have been written (step00 → round01 → round07).

### Phase 2: step-by-step execution (in progress)

After each step, check the output and confirm it is correct before moving to the next step:

```bash
# Step 0: data integration (~30 seconds) ✅ complete
uv run python -m main.stages2.step00_integrate
# → 1,055,116 entries cleaned

# Round 1: lightweight scoring (~15 minutes) ✅ complete
uv run python -m main.stages2.round01_lightweight
# → AnOxPePred + AlgPred2 full scoring complete
# → all_scored.csv + top50k.csv written

# Round 2: split + safety scoring (~50 minutes) 🔄 in progress
uv run python -m main.stages2.round02_scoring
# → HemoPI2 ✅ 50K/380s
# → MHCflurry ❌ model not downloaded (need to fix the Dockerfile --release argument)
# → ToxinPred3 ⏳ running (concurrency 2, estimated ~48 minutes)
# → output: all_50k.csv (with channel label + 5 service scores + composite score + safety flags)

# Round 3: heavy-service scoring
uv run python -m main.stages2.round03_heavy
# → run BepiPred3 + TemStaPro on the 50K
# → output top80 + bottom10

# Round 4: enumeration + construct scoring
uv run python -m main.stages2.round04_enumerate
# → dual-channel enumeration + construct-level re-score

# Round 5: 3D structure prediction (~2 hours)
uv run python -m main.stages2.round05_3d
# → ESMFold + OmegaFold

# Round 6: PDB evaluation (~3 minutes)
uv run python -m main.stages2.round06_pdb_eval
# → SASA + Aggrescan3D

# Round 7: final output (~1 second)
uv run python -m main.stages2.round07_final
# → Top + Bottom dual ranking
```

### Phase 3: validation

- Compare the difference between the top and bottom AnOxPePred distributions
- Check that every safety dimension score for the bottom entries is below its threshold
- Confirm that all PDB files load correctly

---

## Caveats

1. **Isolation from stages3** — stages3 is running Step 1 on `output3/`. This pipeline uses `output2/`
   and `main/stages2/`, and does not touch `output3/` or `main/stages3/`. Docker services may be
   occupied by stages3 (such as anoxpepred, algpred2), so run a health check before starting.

2. **Docker service contention** — if stages3's Step 1 is using anoxpepred and algpred2, stages2's
   Round 1 will conflict with it. It is recommended to wait until stages3 Step 1 finishes before starting stages2,
   or to ensure the service instances are independent.

3. **GPU memory** — if stages3 has enabled GPU services (such as bepipred3, temstapro), stages2's Rounds 3/5
   may run out of GPU memory. Check GPU memory usage with `nvidia-smi` before running.

4. **Bottom-N are not "bad peptides"** — the Bottom-N peptides pass the thresholds on every safety dimension;
   their AnOxPePred score is simply the lowest. They are safe controls, not "failed" peptides.

5. **Construct-level re-scoring adds time** — the full-length AnOxPePred + BepiPred3 scoring added in Round 4
   costs roughly 2-5 extra minutes, which is acceptable at the scale of ≤100 constructs.
