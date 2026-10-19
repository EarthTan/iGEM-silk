> English translation of [PLAN.md](PLAN.md). The Chinese original is kept unchanged as the source of truth.

# Stages4 Pipeline Plan: Hierarchical Filtering + Safety First

> Version: v2.0 — 2026-05-18
> Data sources: UniProt (225M) + MGnify (624M)
> Input candidates: ~19.9M (produced by stages3 Round 0 preprocessing)
> Target: 19.9M → Top 100 + Bottom 100

---

## 1. Background: The Two Fatal Problems of stages2

### Problem 1: Weighted averaging diluted critical safety attributes

Stages2 used a weighted average to blend attributes from different dimensions, such as antioxidant capacity, hemolysis, allergenicity, and MHC binding.

```
AnOxPePred(0.45) + ToxinPred3(0.13) + HemoPI2(0.09) + MHCflurry(0.05) + ...
```

In this formula, HemoPI2 carries a weight of only 0.05–0.09, which means that even if a peptide has extremely poor hemolytic behavior (high hemolysis risk), its composite score can still rank near the top as long as its antioxidant score is high enough. **Safety attributes became score components that could be "compensated", instead of hard conditions with veto power.**

**The correct approach**: safety attributes should be hard thresholds (pass / eliminate) and should not participate in weighted blending.

### Problem 2: The dual channels were still dominated by antioxidant in the composite score

Although the initial dual-channel split used pure AnOxPePred (correct), subsequent Rounds 3–7 still used a composite score that included AnOxPePred weight for ranking and screening. This caused:

- The Bottom channel (peptides with the worst antioxidant capacity) was still affected by residual AnOxPePred weight in later rounds
- Safety screening was not truly independent of the antioxidant signal

**The correct approach**: antioxidant is used only once, for the dual-channel split, and does not participate in any ranking in later rounds.

---

## 2. stages4 Core Principles

### Principle A: Hierarchical filtering; never average across attributes

Each round uses a single screening criterion — either rank and take a percentage, or eliminate with a hard threshold. The same round never blends different attributes in a weighted average.

### Principle B: Safety attributes use hard thresholds

Safety-related attributes such as toxicity, hemolysis, and allergenicity only have pass/eliminate thresholds and do not participate in any score blending.

### Principle C: Antioxidant is used only once

AnOxPePred is used only for the dual-channel split in Round 1. Once the channels are fixed, no later round uses the antioxidant score.

### Principle D: Variable weighting mechanism (SD-driven + manual adjustment)

Weighted averaging is used only in Round 3 (deep scoring), with a two-layer weighting mechanism:

- **Base weights**: SD-driven, `w_base = σ_i / Σσ_j`; attributes with high discriminative power automatically receive high weight
- **Manual adjustment**: multiply the SD weights by a manual coefficient `α`, allowing domain knowledge to intervene

```
w_final_i = w_base_i × α_i         (renormalize so that Σw = 1)
```

By default `α = 1.0` for all attributes (purely SD-driven). Manual coefficients must be explicitly recorded in the `weight_config` table, together with the reason for the adjustment.

**Special handling of AnOxPePred**: although it has already been used as a split criterion in Round 1, if you want the antioxidant signal to participate in deep scoring in Round 3, you can use a manual coefficient `α > 1.0` to give it a higher weight in the average (for example α = 1.3). The precondition is that the split channels are already fixed, so the Round 3 antioxidant score only discriminates among candidates within a channel and does not affect cross-channel comparison.

| Attribute group | Handling | Location |
|--------|---------|------|
| Antioxidant | Used for the Round 1 split; may optionally participate in Round 3 weighting (participates by default, α=1.0) | Round 1, Round 3 |
| Safety (toxicity/hemolysis/allergenicity/immunogenicity) | Hard threshold pass/eliminate | Round 1–2 |
| Function (B-cell epitope/thermal stability/solubility/cell penetration) | SD-weighted composite score | Round 3 |
| 3D structure (SASA/Aggrescan3D/pLDDT) | SD weighting or independent ranking | Round 6–7 |

### Principle E: From light to heavy, tightening step by step

```
Round 1 (light, ~5min/million) → rank and take the top few percent
Round 2 (light, safety thresholds)   → hard elimination
Round 3 (heavy, GPU~min/hundred) → SD weighting → take the top few percent
Round 4 (light, enumeration)       → rank and take the top few percent
Round 5 (heaviest, GPU~min/construct) → all pass
Round 6 (light, CPU seconds/construct)    → score all
Round 7 (purely local)          → final ranking
```

---

## 3. Eight-Round Funnel Design

### Round 0: Data preprocessing

**Reuse the results of stages3 Round 0**, with no algorithmic changes.

| Step | Operation | Data volume |
|------|------|--------|
| Length filtering | 3–30 aa | 849M → ~5% |
| AA filtering | only the 20 standard amino acids | + deduplication |
| Write to DB | DuckDB `candidates` table | 19,890,021 |

**Expected runtime**: ~99 min

---

### Round 1: Single-metric antioxidant split

**Core change**: this is the first time the antioxidant score is used. If you choose to let AnOxPePred participate in Round 3 weighting, then this is the only basis for the dual-channel split, rather than its only point of use.

| Step | Operation | Basis | Expected pass count |
|------|------|------|-----------|
| 1a | Run AnOxPePred on all 19.9M candidates | antioxidant activity prediction | all 19.9M scored |
| 1b | Run AlgPred2 | allergenicity hard threshold ≥0.30 → eliminate | eliminate ~15% |
| 1c | Sort the AlgPred2-passing candidates by AnOxPePred | pure antioxidant score, no blending | — |
| 1d | Take the Top 10% → Top channel | the 10% with the best antioxidant capacity | ~1.7M |
| 1e | Take the Bottom 1% → Bottom channel | the 1% with the worst antioxidant capacity (negative control) | ~170K |

**Services involved**: AnOxPePred (GPU), AlgPred2 (CPU)

**Output tables**: `round1_scores`, `round1_channels`

---

### Round 2: Safety screening (pure hard thresholds, no weighting)

**Core change**: safety attributes do not participate in any blending; each attribute eliminates independently.

| Step | Operation | Elimination criterion |
|------|------|---------|
| 2a | Run ToxinPred3 | ≥0.38 → eliminate (high toxicity risk) |
| 2b | Run HemoPI2 | ≥0.55 → eliminate (hemolysis risk) |
| 2c | Run MHCflurry | ≥0.5 → eliminate (immunogenicity risk) |
| 2d | Merge the elimination lists | eliminate if any safety item fails |
| 2e | Survivors enter Round 3 | all safety items pass |

**Services involved**: ToxinPred3 (CPU), HemoPI2 (CPU), MHCflurry (GPU)

**Design rationale**:
- Safety attributes are "veto" conditions, not "compensable" ones
- No composite score and no ranking are needed, only pass/eliminate
- The three services can run concurrently and do not depend on each other

**Output tables**: `round2_scores`, `round2_passed`, `round2_excluded`

---

### Round 3: Deep scoring + variable weights (the only weighted location)

**Core change**: the only place in the entire pipeline that uses a weighted average. It adopts a two-layer weighting mechanism of SD-driven weights plus manual adjustment.

| Step | Operation | Details |
|------|------|------|
| 3a | Run BepiPred3 | B-cell epitope prediction (GPU) |
| 3b | Run TemStaPro | thermal stability prediction (GPU) |
| 3c | Run SoDoPE | solubility prediction (CPU) |
| 3d | Run pLM4CPPs | cell penetration prediction (GPU) |
| 3e | Run GraphCPP | cell penetration GNN (GPU) |
| 3f | (optional) Run AnOxPePred | if antioxidant is to participate in weighting |
| 3g | Compute the winsorized SD of each service | clip the extreme 1% |
| 3h | Base weights | w_base_i = σ_i / Σσ_j |
| 3i | Manual adjustment | w_final_i = w_base_i × α_i, then renormalize |
| 3j | Compute the composite score | Σ(w_final_i × score_i_normalized) |
| 3k | Rank and take the Top N% | for example Top 5% |

**Weight formula**:

```
// base: SD-driven
for each service s in participating_services:
    σ_s = winsorized_stddev(scores_s)
    w_base_s = σ_s / Σσ_all

// manual adjustment
for each service s:
    w_final_s = w_base_s × α_s       // α >= 0, default 1.0

// renormalization
Σw_final = Σ(w_final_s)
w_norm_s = w_final_s / Σw_final
```

**Manual coefficient record format**:

| Service | α | Reason |
|------|---|------|
| anoxpepred | 1.0 | default (no extra boost) |
| bepipred3 | 1.0 | default |
| temstapro | 1.0 | default |
| ... | 1.0 | default |

If one day you decide to "raise the AnOxPePred weight to 1.3×", you only need to change one number, and every historical record remains traceable.

**Output tables**: `round3_scores`, `round3_ranking`, `score_distribution`, `weight_config`

---

### Round 4: Construct enumeration + attribute scoring

| Step | Operation |
|------|------|
| 4a | Take the Round 3 Top N peptides (Top channel) + Bottom M peptides (Bottom channel) |
| 4b | Enumerate 3 fusion positions (N-terminus / C-terminus / both ends) |
| 4c | Enumerate 2 linkers (Flex_GGGGSx1 / Flex_GGGGSx2) |
| 4d | Assemble the full sequence (scaffold ~346aa + linker + peptide) |
| 4e | Run SoDoPE (solubility of the full-length construct) |
| 4f | Run TemStaPro (thermal stability of the full-length construct) |
| 4g | Take the Top N into Round 5 |

**Note**: this round does not involve weighted averaging. SoDoPE and TemStaPro are recorded separately.

**Output tables**: `constructs`, `construct_scores`

---

### Round 5: 3D structure prediction

| Step | Operation |
|------|------|
| 5a | OmegaFold inference (all constructs) |
| 5b | Extract pLDDT confidence |
| 5c | Store PDB files named by construct |

**Services involved**: OmegaFold (GPU, serial)

**Output tables**: `structure_results`, PDB files

---

### Round 6: PDB evaluation

| Step | Operation |
|------|------|
| 6a | SASA calculation (surface exposure of the peptide segment; higher is better) |
| 6b | Aggrescan3D calculation (aggregation risk; lower is better) |

**Services involved**: SASA (CPU), Aggrescan3D (CPU)

**Note**: no weighted blending. SASA and Aggrescan3D are recorded separately.

**Output tables**: `pdb_eval`

---

### Round 7: Final ranking output

| Step | Operation |
|------|------|
| 7a | Independent ranking of the Top channel (based on the Round 6 3D metrics) |
| 7b | Independent ranking of the Bottom channel |
| 7c | Generate the final output package (CSV + reports) |

**Ranking scheme**: perform an SD-weighted ranking over the three 3D metrics SASA, (1-Aggrescan3D), and pLDDT. It is also acceptable to sort directly by SASA (following the stages2 experience: SASA has the best discriminative power).

**Output**:
- `top100.csv` — Top channel ranking
- `bottom100.csv` — Bottom channel ranking
- `score_distribution.json` — final score distribution
- a separate folder per construct (with FASTA, PDB, scores)

---

## 4. File System Conventions

### Naming rules

Uniformly use the `s4_roundXX_name.py` format:

```
main/stages4/
├── PLAN.md                        # ← this document
├── __init__.py
│
├── s4_round00_preprocess.py       # data preprocessing (can be skipped)
├── s4_round01_antioxidant_split.py # single-metric antioxidant split
├── s4_round02_safety_screen.py     # safety screening (hard thresholds)
├── s4_round03_deep_scoring.py      # deep scoring + variable weights
├── s4_round04_enumerate.py         # construct enumeration
├── s4_round05_3d.py                # 3D structure prediction
├── s4_round06_pdb_eval.py          # PDB evaluation
├── s4_round07_final.py             # final ranking
│
├── s4_db.py                        # DuckDB database interface
├── s4_docker_utils.py              # Docker on-demand startup
├── s4_service_map.py               # service dependency map
├── s4_analytics.py                 # variance-aware weighting engine (with manual adjustment)
│
├── plan/                           # storage for planning documents
│
└── __pycache__/
```

### Naming comparison with stages2

| Meaning | stages2 | stages4 |
|------|---------|---------|
| Data preprocessing | `step00_integrate.py` | `s4_round00_preprocess.py` |
| Lightweight scoring | `round01_lightweight.py` | `s4_round01_antioxidant_split.py` |
| Safety screening | (mixed into round02–03) | `s4_round02_safety_screen.py` |
| Deep scoring | `round03_heavy.py` | `s4_round03_deep_scoring.py` |
| Construct | `round04_enumerate.py` | `s4_round04_enumerate.py` |
| 3D structure | `round05_3d.py` | `s4_round05_3d.py` |
| PDB evaluation | `round06_pdb_eval.py` | `s4_round06_pdb_eval.py` |
| Final ranking | `round07_final.py` | `s4_round07_final.py` |

### Output directory structure

```
output4/
├── STATUS.md
├── pipeline.db                    # DuckDB database
├── reports/                       # per-round reports
│   ├── round0_report.md
│   ├── round1_report.md
│   └── ...
├── pdb/                           # 3D structure files
│   └── con_XXXX/
│       ├── construct.fasta
│       ├── omegafold.pdb
│       └── scores.json
├── logs/                          # run logs
└── final/                         # final output
    ├── top100.csv
    ├── bottom100.csv
    ├── weight_config.json          # weight configuration + manual adjustment records
    ├── score_distribution.json
    └── constructs/                # a separate folder per construct
```

---

## 5. Database Design

### Notes on DuckDB

Stages4 uses DuckDB to manage state. Although the data volume (tens of millions) is far smaller than stages3 (billions), the advantages of using a database still hold:
- a unified checkpoint/resume mechanism
- flexible querying (SQL is more reliable than handing off files through CSV)
- most of stages3's `db.py` can be reused

### Table list

| Table | Purpose | Written in round | Expected rows |
|----|------|---------|---------|
| `candidates` | candidate peptides | Round 0 | 19.9M |
| `round1_scores` | AnOxPePred + AlgPred2 | Round 1 | 19.9M |
| `round1_channels` | dual-channel membership (Top/Bottom) | Round 1 | ~1.87M |
| `round2_scores` | safety service scores | Round 2 | ~1.87M |
| `round2_passed` | candidates passing the safety thresholds | Round 2 | ~1.5M |
| `round3_scores` | deep service scores | Round 3 | ~1.5M |
| `round3_ranking` | SD-weighted ranking | Round 3 | ~1.5M |
| `constructs` | construct enumeration | Round 4 | ~10K–50K |
| `construct_scores` | construct-level scores | Round 4 | ~10K–50K |
| `structure_results` | 3D structure results | Round 5 | ~500–5K |
| `pdb_eval` | PDB evaluation results | Round 6 | ~500–5K |
| `final_ranking` | final ranking | Round 7 | ~200 |
| `score_distribution` | score distribution statistics | Round 3, 7 | ~20 |
| `weight_config` | weight configuration (SD weights + manual coefficient α) | Round 3, 7 | ~10 |
| `checkpoint` | checkpoints | All | ~20 |

### Differences from stages2

| Dimension | stages2 | stages4 |
|------|---------|---------|
| State management | CSV file hand-off | **unified DuckDB management** |
| Round 1 output | `all_scored.csv` (full volume, no channel labels) | `round1_channels` (with dual-channel membership) |
| Round 2 safety handling | mixed into the composite score with low weight | **independent hard-threshold elimination, in a separate table** |
| Weighted locations | Round 2 + Round 3 + Round 6 | **Round 3 only** |
| Weight source | manually fixed | **SD-driven + manual coefficient α** |
| Number of antioxidant uses | implicitly used in multiple rounds | **Round 1 split; optional participation in Round 3** |

---

## 6. Data Volume Estimates

### Screening funnel

```
19,890,021  candidates
    │ Round 1: rank by AnOxPePred and take the Top 10%
    ▼
~1,990,000  Top channel (+ ~200,000 Bottom channel)
    │ Round 2: safety hard thresholds (Toxin/Hemo/MHC)
    ▼
~1,500,000  safety-passing
    │ Round 3: deep scoring SD weighting → Top 5%
    ▼
~75,000     deep-scoring-passing
    │ Round 4: enumerate × 6 (3 pos × 2 linker) → SoDoPE/TemStaPro → Top 5%
    ▼
~22,500     constructs
    │ Round 5–6: OmegaFold + SASA + Aggrescan3D (all pass)
    ▼
~22,500     scored constructs
    │ Round 7: final ranking
    ▼
  Top 100 + Bottom 100
```

### Bottleneck estimates

| Round | Most time-consuming service | Time per item | Total time (est.) | After concurrency speedup |
|------|-----------|---------|-------------|-----------|
| Round 1 | AnOxPePred | ~0.1s | ~23d | ~2d (batch 1K, concurrency 10) |
| Round 2 | ToxinPred3 | ~0.5s | ~11d | ~1d (batch 10, concurrency 5) |
| Round 3 | BepiPred3 (GPU) | ~2.5s | ~43d | ~2d (concurrency 5, Semaphore) |
| Round 5 | OmegaFold (GPU) | ~120s | ~31d | ~31d (serial, cannot be parallelized) |

---

## 7. Variable Weighting Mechanism in Detail

### Two-layer weight structure

```
┌────────────────────────────────────────────────────────────────────────┐
│                     weight_config table                                │
│                                                                        │
│  {                                                                     │
│    "round": 3,                                                         │
│    "formula": "winsorized_stddev_normalized",                          │
│    "sd_weights": {                                                     │
│      "bepipred3_score":  0.31,    ← data-driven base weight            │
│      "temstapro_score":  0.18,                                         │
│      "sodope_score":     0.22,                                         │
│      "plm4cpps_score":   0.19,                                         │
│      "graphcpp_score":   0.10                                          │
│    },                                                                  │
│    "manual_coefficients": {                                            │
│      "bepipred3_score":  1.0,     ← manual adjustment coefficient      │
│      "temstapro_score":  1.0,                                          │
│      "sodope_score":     1.0,                                          │
│      "plm4cpps_score":   1.0,                                          │
│      "graphcpp_score":   1.0                                           │
│    },                                                                  │
│    "final_weights": {                                                  │
│      "bepipred3_score":  0.31,    ← final weights after normalization  │
│      ...                                                               │
│    },                                                                  │
│    "adjustment_reason": "default configuration, no manual adjustment"  │
│  }                                                                     │
└────────────────────────────────────────────────────────────────────────┘
```

### Adjustment principles

1. By default all `α = 1.0` (purely SD-driven, no manual intervention needed)
2. Changing α requires filling in `adjustment_reason` (e.g. "AnOxPePred is a core function metric, slightly boosted")
3. Multiple α value sets can be tried in a single run for sensitivity analysis
4. All historical adjustment records are kept in the `weight_config` table and are fully traceable

### Usage examples

| Scenario | Operation | Effect |
|------|------|------|
| Default | all α = 1.0 | purely data-driven |
| Slightly emphasize antioxidant | anoxpepred α = 1.3 | SD weight × 1.3, then renormalize |
| Exclude a non-discriminative attribute | temstapro α = 0 | fully excluded from the weighting |
| Emphasize B-cell epitope | bepipred3 α = 1.5 | B-cell epitope weight raised by 50% |

---

## 8. Comparison with stages2

| Dimension | stages2 (problem) | stages4 (fix) |
|------|----------------|-----------------|
| Safety attributes | mixed into the weighted average with low weight (0.05–0.13), can be "compensated" by antioxidant | **independent hard-threshold elimination**, veto |
| Antioxidant usage | implicitly used in multiple rounds, contaminating the dual channels | **dedicated to the Round 1 split; optional participation in Round 3** |
| Dual-channel isolation | later rankings still affected by antioxidant | **independent per-channel ranking, no cross-contamination** |
| Weighting method | manually fixed weights (assigned by experience) | **SD-driven + manual coefficients (data-driven + domain knowledge)** |
| Weighted locations | Round 2 + Round 3 + Round 6 | **Round 3 only** |
| Weight auditability | manually noted in CSV | **weight_config table: SD weights + manual coefficients + reasons** |
| File naming | `roundXX_name.py` + `step00` mixed | **uniform `s4_roundXX_name.py`** |
| State management | CSV file hand-off | **unified DuckDB management** |
| Non-discriminative attributes | still assigned a fixed weight | **automatically drop to zero weight, or manually set α=0** |
| Checkpoint/resume | manually inspect output files | **automatic recovery via the checkpoint table** |

---

## 9. Technical Architecture

### Infrastructure sources

| Component | Source | Changes |
|------|------|------|
| `s4_db.py` | refactored from stages3 `db.py` | table names changed to round_*; channel/safety screening operations added |
| `s4_docker_utils.py` | copied directly from stages3 | no changes |
| `s4_service_map.py` | rewritten | service dependencies remapped to the 8 rounds |
| `s4_analytics.py` | refactored from stages3 `analytics.py` | support for manual coefficient α added |
| `ServiceClient` | `main/client.py` | reused directly |

### Concurrency strategy

| Round | Strategy | Notes |
|------|------|------|
| Round 1 | Semaphore(10–20), batch 1K/request | AnOxPePred can handle high concurrency |
| Round 2 | Semaphore(2–5), ToxinPred3 serialized | ToxinPred3 sklearn is not thread-safe |
| Round 3 | Semaphore(3–5) per GPU service | GPU services limit concurrency to prevent OOM |
| Round 5 | Semaphore(1) serial | OmegaFold blocks the event loop |
| Round 6 | Semaphore(10) | CPU services can handle high concurrency |

### Checkpoints and resume

Reuse stages3's checkpoint mechanism: `set_checkpoint()` / `get_checkpoint()` / `get_last_processed_id()`.

---

## 10. Open Decisions

| Question | Options | Recommendation |
|------|------|------|
| What % for the Round 1 Top? | 5% / 10% / 20% | 10% (~1.99M) |
| What % for the Round 1 Bottom? | 0.5% / 1% / 2% | 1% (~199K) |
| What % for Round 3? | 1% / 5% / 10% | 5% (~75K) |
| What % for Round 4? | 1% / 5% / 10% | 5% (~22.5K constructs) |
| MHCflurry hard threshold? | ≥0.5 / ≥0.7 / none | need to confirm against the literature |
| Should AnOxPePred participate in Round 3 weighting? | yes / no | recommended: yes (α=1.0 by default) |
| Round 7 ranking basis | pure SASA / SD-weighted (3D) | recommended: look at the distribution first |
| Reuse the stages3 DB? | reuse / rerun | reuse if the schema is compatible |
