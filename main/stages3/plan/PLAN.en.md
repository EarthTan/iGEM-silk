> English translation of [PLAN.md](PLAN.md). The Chinese original is kept unchanged as the source of truth.

# Stages3 Pipeline Plan: From Billions to Candidates

> Version: v1.0 — 2026-05-15
> Data sources: uniprot_all_2021_04.fa (102G, 225,619,586 sequences) + mgy_clusters_2022_05.fa (120G, ~624,000,000 sequences)
> Total input: ~850 million sequences
> Goal: from 850 million raw sequences to the top candidate functional peptides

---

## 1. Core Idea: Differentiation-Driven Screening

### Lessons from the Previous Round

In the stages2 run we used a fixed weighting scheme—AnOxPePred was always 0.50, BepiPred was always 0.20, and so on. This scheme has a fundamental problem:

When a score's distribution range is very narrow (for example, the SASA scores of all candidate peptides are concentrated between 0.55 and 0.65, σ ≈ 0.03), giving it an even higher weight is pointless—it cannot separate the candidates and only adds noise to the ranking. Conversely, if another score naturally spreads out widely (for example, AnOxPePred from 0.1 to 0.9, σ ≈ 0.20), that is the real discriminative signal.

### Variance-Aware Weighting

The core innovation of stages3: **score first, look at the distribution, then set the weights**. Rather than deciding in advance which model matters, let the data speak for itself.

The flow is as follows:

```
Stage 1 (lightweight screening) → passers advance to Stage 2
Stage 2 scores the full set across 7+ services
   ↓
Analyze the score distribution of each service (mean, standard deviation, percentiles)
   ↓
Weight = the normalized value of each service's standard deviation (σ_i / Σσ_j)
   ↓
Weighted combination for the final ranking
```

The benefits of doing this:
- **Automatic noise reduction**: services with poor discriminative power automatically receive low weights
- **Dynamic adaptation**: change the dataset or the candidate peptide set and the weights adjust automatically
- **Interpretability**: changes in the weights directly tell you which signal is most useful in the current batch
- **Avoids overfitting**: instead of manually tuning parameters to find the "best weights", they arise naturally from the data

### The Differentiation-First Principle

Every layer of the funnel should be designed according to this principle:

1. First ask: can the screening signal at this layer effectively separate the candidates?
2. If not → consider merging, down-weighting, or skipping this layer
3. If yes → give it enough weight to do its job
4. Periodically check the distribution shift at each layer to prevent signal saturation in the later screening stages

---

## 2. Data Source Overview

| Database | File | Size | Estimated sequences | Characteristics |
|--------|------|------|-----------|------|
| UniProt complete set | `uniprot_all_2021_04.fa` | 102G | 225,619,586 | Swiss-Prot + TrEMBL, contains many full-length proteins |
| MGnify clusters | `mgy_clusters_2022_05.fa` | 120G | ~624,000,000 | Metagenomic protein clusters, naturally enriched in functional peptides |
| **Total** | | **222G** | **~850 million** | |

### Expected Data Quality

- **UniProt**: a mixture of annotated and automatically annotated proteins. The Swiss-Prot portion is manually reviewed, high quality but small (~1-2%); TrEMBL is automatically annotated and contains many full-length proteins and hypothetical proteins.
- **MGnify**: metagenomic data containing many predicted proteins of unknown function. The proportion of short sequences may be higher, and it is a rich source of natural peptides and functional domains.

---

## 3. Six-Stage Funnel Design

### Stage 0: Data Preprocessing

**Goal**: from raw FASTA to a candidate peptide pool

| Step | Operation | Expected effect | Estimated count afterward |
|------|------|---------|-----------|
| 0a | CD-HIT redundancy removal (90% similarity clustering) | Remove highly similar redundant sequences | ~200-300 million |
| 0b | Length filter (3-30 aa) | Keep only the range in which short peptides are predictable | ~30 million - 100 million |
| 0c | Standard amino acid filter | Remove sequences containing non-standard AAs | ~slight reduction |
| 0d | Write to the database | Unified storage with metadata | — |

**Note**: CD-HIT parameters need to be determined experimentally based on the data characteristics. For short peptides (3-30 aa), a 90% clustering threshold may be too loose (short sequences differ little to begin with) and may need to be raised to 95% or even 100% (removing only exact duplicate sequences). This part requires a parameter sweep during preprocessing.

**Output**: the `candidates` table (database), with fields for sequence, length, source, original ID, etc.

### Stage 1: Lightweight Primary Screening

**Goal**: use the two lightest services to quickly cut out unqualified candidates

| Service | Type | Screening method | Expected pass rate |
|------|------|---------|-----------|
| AnOxPePred | Antioxidant prediction | Hard threshold filter (raw score > 0.3) | ~30-50% |
| AlgPred2 | Allergen prediction | Hard threshold exclusion (score ≥ 0.30 eliminated) | ~80-90% |

**Design rationale**: AnOxPePred is our most central signal—antioxidant capacity is the first gate of functional screening. It also showed the best discriminative power in the previous round. AlgPred2 provides absolute exclusion: anything predicted to be an allergen is eliminated outright and does not participate in subsequent scoring.

**Concurrency strategy**: each candidate peptide calls both services concurrently, and the slower one determines completion. There are no dependencies.

**Output**: the `stage1_passed` table (passers) and the `stage1_failed` table (eliminated candidates with reasons).

### Stage 2: Full Scoring + Differentiation-Based Weighting

**Goal**: score the candidate peptides that passed primary screening across all dimensions, and set weights automatically based on the distributions

**Services involved (grouped by function)**:

| Service | Group | Dimension | Expected discriminative power |
|------|-----|------|-----------|
| AnOxPePred | Function | Antioxidant | ★★★★★ |
| BepiPred-3.0 | Function | B-cell epitope | ★★★ |
| pLM4CPPs | Function | Cell penetration | ★★★ |
| GraphCPP | Function | Cell penetration (GNN) | ★★ |
| TemStaPro | Function | Thermal stability | ★★ |
| SoDoPE | Function | Solubility | ★★ |
| MHCflurry | Safety | MHC-I binding (inverse) | ★★★ |
| ToxinPred3 | Safety | Toxicity (absolute exclusion) | — |
| HemoPI2 | Safety | Hemolysis (absolute exclusion) | — |

**Differentiation-based weighting flow**:

1. First score the Stage 1 passers with all services
2. Collect each service's score vector and compute the standard deviation σ
3. Compute the raw weights: `w_i_raw = σ_i`
4. Normalize: `w_i = w_i_raw / Σw_j_raw`
5. Apply the weights to compute the composite score: `composite = Σ(w_i × score_i_normalized)`
6. Rank by composite score and take the Top N

**Handling absolute exclusions**: ToxinPred3 and HemoPI2 predictions do not participate in the weight computation—they are hard elimination criteria, not scoring dimensions. If a candidate peptide is judged toxic or hemolytic, it is eliminated immediately and excluded from the ranking.

**Output**: the `stage2_scores` table (all scores and the final ranking), plus the `excluded_toxic` and `excluded_hemolytic` tables.

### Stage 3: Construct Enumeration

Assemble the Top candidate peptides from Stage 2 with the silk protein scaffold into full constructs, enumerating 3 fusion positions (N-terminus / internal insertion / C-terminus) and 2 linkers (flexible / rigid).

Run SoDoPE (solubility) and TemStaPro (thermal stability) predictions on each construct.

**Output**: the `constructs` table (including sequence, position, linker, and SoDoPE/TemStaPro scores).

### Stage 4: 3D Structure Prediction

Run 3D structure prediction on the top constructs:

| Service | Role | Strategy |
|------|------|------|
| ESMFold | Fallback | Not used by default |
| OmegaFold | Primary | Preferred for all constructs |
| AlphaFold3 / PEP-FOLD4 | Reserved | Not enabled in the current round |

**Key constraint**: a single machine with a single GPU and 128G of memory. ESMFold and OmegaFold must run inference serially. Expect about 2-6 minutes per construct.

**Output**: PDB files (named by construct and stored in `output3/pdb/`), and the `plddt_scores` table.

### Stage 5: PDB Evaluation

Evaluate the surface properties of the generated 3D structures:

| Service | Evaluation dimension |
|------|---------|
| SASA (FreeSASA) | Solvent accessibility of the peptide region |
| Aggrescan3D | Surface aggregation propensity |

The SASA score showed excellent discriminative power in stages2 (σ ≈ 0.098) and is the core signal of this stage.

**Output**: the `pdb_eval` table, containing SASA, Aggrescan3D, pLDDT, and other scores.

### Stage 6: Final Ranking

Combine all signals from Stage 2 (functional scores), Stage 3 (solubility/stability), and Stage 5 (structural scores) for the final weighted ranking.

**The final weights are also variance-aware**—recompute the distributions over all available score dimensions to determine the final composite weights.

**Output**: the `final_ranking` table, the Top 10 / Top 20 candidate constructs, and the complete output package.

---

## 4. Complete Workflow of Variance-Aware Weighting

This is the most fundamental difference between stages3 and stages2 and deserves a detailed explanation:

```
Round 1 (inside Stage 2):
  Run the full set of 7+ services on all candidates
  → compute σ for each service
  → weight = σ_i / Σσ_j
  → weighted ranking → take Top N

Round 2 (Stage 6 final ranking):
  Over all available scores (function + solubility + structure)
  → recompute σ
  → normalize the weights again
  → final ranking
```

**Why two rounds instead of doing it all at once?**

Because Stage 2 and Stage 5 operate on different signal dimensions—Stage 2 produces sequence-level scores and Stage 5 produces structure-level scores. Their distribution characteristics may be completely different. Computing in two rounds lets each round use variance-aware weighting, with one final unified normalization at combination time.

### Potential Risks and Mitigations

| Risk | Mitigation |
|------|---------|
| A service completely loses its discriminative power (σ ≈ 0) | It automatically receives a weight near 0, equivalent to skipping that service |
| Extreme values in one service dominate the weights | Apply winsorization (trimming) first: remove the top and bottom 1% extreme values before computing σ |
| Large distribution differences between batches | If the data volume is large enough (millions), the distribution is stable; for small batches, consider bootstrap confidence intervals |
| Interaction between absolute exclusions and scored items | Absolute exclusions are executed before the weight computation and do not participate in distribution analysis |

---

## 5. Time Estimates

Assuming a single machine with 128G of memory, an RTX 3090 (24G), and SSD storage:

| Stage | Estimated time | Bottleneck | Notes |
|------|---------|------|------|
| Stage 0 (CD-HIT) | 2-5 days | CPU + memory | Depends on the CD-HIT parameters and whether 32 threads are used |
| Stage 0 (3-30aa filter) | 2-4 hours | I/O | A single sequential scan |
| Stage 1 (2 services) | 2-5 days | CPU | ~347s at the million scale → 2-5 days at the hundreds-of-millions scale |
| Stage 2 (7 services) | 5-10 days | CPU + network | Full scoring, the heaviest round |
| Stage 3 (enumeration + scoring) | 1-2 days | CPU | Only for the Top N (tens of thousands) |
| Stage 4 (3D structure) | 3-10 days | GPU | Serial inference on a single GPU, 300-500 constructs |
| Stage 5 (PDB evaluation) | 0.5-1 day | CPU | Lightweight computation |
| **Overall** | **~2-4 weeks** | | |

Errors in the time estimate mainly come from the actual pass rates of Stage 1-2 and the number of constructs in Stage 4. It is recommended to record the actual elapsed time after each stage for planning subsequent rounds.

---

## 6. Output Plan

Results are output to `output3/`, following stages2's output style but extended to be database-driven:

```
output3/
├── STATUS.md              ← Global progress pointer (updated in real time)
├── README.md              ← Final report
├── final/                 ← Final output package
│   ├── top10.csv          ← Top 10 candidates
│   ├── top20.csv          ← Top 20 candidates
│   ├── score_distribution.json  ← Distribution statistics for all scores
│   └── weight_report.json ← Final assignment of variance-aware weights
├── pdb/                   ← 3D structure files
│   └── <construct_id>/
│       ├── construct.fasta
│       ├── <method>.pdb   ← Corresponding PDB file
│       └── scores.json
└── reports/               ← Detailed reports for each stage
    ├── stage0_report.md
    ├── stage1_report.md
    ├── ...
    └── stage6_report.md
```

The **database file** `output3/pipeline.db` (DuckDB format) contains all intermediate data and final results, accessed through the interfaces defined in db_schema.

---

## 7. Next Steps

1. Install CD-HIT, run sampling analysis on the two databases, and determine the best clustering parameters
2. Set up a DuckDB database instance and create the schema
3. Write the Stage 0 preprocessor (CD-HIT wrapper + length filter)
4. Refactor Stage 1-2 based on the existing stages2 scripts (database reads and writes + variance weight computation)
5. Advance Stage 3-6 in order
