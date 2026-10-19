> English translation of [PLAN.md](PLAN.md). The Chinese original is kept unchanged as the source of truth.

# Pipeline Design Plan

---

## 1. The Real Cost of the 15 Microservices

Before writing the plan, let's first get clear on what tools we have on hand and what each of them costs.

### Hard Filtering (a single veto rejects the candidate)

| Service | Model | Per-sequence time | Batch throughput | Memory | GPU | Model size | Elimination threshold |
|---------|-------|-------------------|------------------|--------|-----|------------|-----------------------|
| ToxinPred3 | ExtraTrees (CPU) | <5 ms | ~2000 seq/s | 300 MB | Not needed | 2 MB | score ≥ 0.38 |
| HemoPI2 | ESM-2 t6 fine-tuned | ~30 ms | ~100 seq/s | 1.5 GB | Optional | 600 MB | score ≥ 0.55 |
| AlgPred2 | Random Forest (CPU) | <5 ms | ~2000 seq/s | 200 MB | Not needed | 1 MB | score ≥ 0.30 |

Of the three hard filters, ToxinPred3 and AlgPred2 cost almost nothing (CPU, millisecond-level, a few hundred MB), while HemoPI2 is a bit heavier but still within an acceptable range (ESM-2 t6 has only 8M parameters).

### Scoring Services (participate in weighted composite scoring)

| Service | Model | Per-sequence time | Batch throughput | Memory | GPU | Model size | Scoring weight |
|---------|-------|-------------------|------------------|--------|-----|------------|----------------|
| AnOxPePred | CNN (TF) | <10 ms | ~200 seq/s | 500 MB | Optional | 1.3 MB | **0.50** |
| BepiPred-3.0 | ESM-2 650M + DenseNet | ~200 ms | ~50 seq/s | **4 GB** | Optional | **2.5 GB** | 0.20 |
| pLM4CPPs | ESM-2 t6 + 1D-CNN | ~50 ms | ~200 seq/s | 1.5 GB | Optional | 10 MB | 0.15 |
| MHCflurry | NN ensemble | ~50 ms | ~500 seq/s | 1 GB | Optional | 100 MB | 0.10 (inverted) |
| GraphCPP | GraphSAGE GNN | **~200 ms** | **~30 seq/s** | 1 GB | Optional | 200 KB | 0.05 |
| TemStaPro | **ProtT5-XL 3B** + 30×MLP | **~500 ms** | **~20 seq/s** | **6 GB** | **Recommended** | **3 GB** | Unassigned |

**Notes**:
- TIPred (tyrosinase inhibition) is a specific-function predictor; it is not an essential attribute of antioxidant peptides, so it does not participate in scoring.
- SoDoPE (solubility) is moved to construct-level evaluation (Stage 6); peptide-level solubility scores have no reference value for fusion proteins.

Key information:
- **AnOxPePred carries 50% of the weight**; it is the most direct predictor of antioxidant activity and is lightweight (<10 ms/sequence).
- **BepiPred-3.0 is a heavy service**: 4 GB memory, 50 seq/s throughput. Running 25000 sequences takes 8 minutes. It carries 20% of the weight.
- **TemStaPro is the heaviest**: 6 GB memory, 20 seq/s throughput, 3 GB download at startup. It is not in the current weight table. **Stage 2 does not necessarily need to run TemStaPro**.
- **GraphCPP's model is small (200 KB) but takes 200 ms per sequence**, because of the cost of RDKit converting the amino acid sequence into a molecular graph. Its 30 seq/s throughput is a bottleneck for large batches.

### 3D Structure Prediction

| Service | Environment | Per-sequence time | Concurrency | Sequence limit | Resource requirement |
|---------|-------------|-------------------|-------------|----------------|----------------------|
| **ESMFold** | Native GPU | **~1–3 minutes** | 3 | No limit | **~8 GB VRAM** (ESM-2 3B) + an extra 6 GB cache |
| AlphaFold3 | GPU Linux Docker | 30–120 minutes | 1 | No limit | **≥24 GB VRAM + TB-scale database** |
| PEP-FOLD4 | CPU Docker | 10–30 minutes | 1 | **5–40 aa** | ~2 GB |

ESMFold is the primary prediction tool: no Docker needed, no TB-scale database needed, and fast inference (about 60 times that of AF2). AlphaFold3 is available (48 GB VRAM); in practice a single 6 aa peptide took about 2 hours on its first run (including database download/installation), and subsequent predictions are expected to take 30–120 minutes. Given the team's limited capacity, only the ESMFold and AF3 routes are currently maintained. PEP-FOLD4 supports only 5–40 aa and cannot handle full-length fusion proteins.

**Waveflow (port 8205)**: a Tamarind.bio cloud API proxy that specifies the tool type via the URL path (`POST /predict/esmfold`) and needs neither a local GPU nor model weights. It is slower than local ESMFold due to network latency, but it gives access to all tools on the tamarind platform without consuming local GPU VRAM. It suits environments without a GPU or scenarios that need to switch between different tools.

### PDB Evaluation

| Service | Environment | Per-sequence time | Concurrency |
|---------|-------------|-------------------|-------------|
| SASA | CPU (FreeSASA) | **1–5 seconds** | 10 |
| SoDoPE | CPU (mathematical computation) | **<1 ms** | Extremely fast |
| Aggrescan3D | Docker CPU | **1–15 minutes** | 2 |

**SoDoPE (solubility) is applied at the construct level**: SoDoPE looks up dipeptide composition, and its predictions for full-length fusion proteins (350+ aa) are more reliable than for short peptides. It is therefore moved from peptide-level scoring to here, to evaluate the solubility of the final construct. SoDoPE is extremely fast (<1 ms/sequence) and is not a bottleneck.

SASA performs exposure analysis of the functional peptide: a peptide buried inside fails, while a peptide exposed on the surface can work. Aggrescan3D performs aggregation risk analysis. Together the three produce the final ranking of the constructs.

---

## 2. What These Numbers Tell Us

### Conclusion 1: Running the Cheap Ones Costs Nothing, the Expensive Ones Must Be Reserved for the Few

A throughput of 25 seq/s versus 2000 seq/s is an 80-fold difference. On 25000 sequences, that means the difference between under a minute and several hours. So the orchestration order must be determined by **how many sequences can be processed per unit time**, putting the high-throughput ones first.

### Conclusion 2: Some Services Can Be Omitted Entirely

TemStaPro is not in the weight table, which means it does not participate in the final weighted scoring. If it is only for reference information, it can be run on just the final few dozen constructs instead of all 25000 peptides. Likewise, although BepiPred-3.0 carries a weight of 0.15, running it on 25000 sequences takes 8 minutes, while running it on the top 2000 takes less than a minute.

### Conclusion 3: Hard Filtering Is the Biggest Source of Savings

ToxinPred3 + AlgPred2 together process 25000 sequences in under 10 seconds. According to the proportions in the papers, roughly 20-30% of peptides are toxic or allergenic. That means several thousand sequences can be eliminated in under 10 seconds, and every later step gets that saving for free.

### Conclusion 4: 3D Structure Prediction Is the Ceiling, and the Two Routes Differ Enormously

ESMFold takes 1-3 minutes per sequence, so 50 constructs take about 50 minutes to 2.5 hours (concurrency 3). AlphaFold3 takes 30-120 minutes per sequence, so 50 constructs take 25-100 hours. The two routes differ by a factor of 20-40. Use ESMFold whenever it can handle the job, and hand only what it cannot handle (ultra-long/complex sequences) to AF3.

### Conclusion 5: GPU VRAM Is Not the Problem (48 GB), but AF3 Needs Exclusive Access

48 GB of VRAM is enough for all GPU services in the FASTA scoring stage to be loaded at the same time (BepiPred 4 GB + TemStaPro 6 GB + other light services ≈ 15 GB). But AF3 must have the GPU to itself when it starts — not because there is not enough VRAM (it uses 20+ GB, leaving 20+ GB), but because AF3 locks the GPU device inside its Docker container. So other GPU services still need to be shut down before starting AF3. ESMFold does not require this — it needs ~8 GB of VRAM and can coexist with the remaining services.

---

## 3. Funnel Design: Four-Stage Orchestration

### Stage 1: Millisecond-Level Filtering

**Services involved**: ToxinPred3, AlgPred2

**Estimated time**: 25000 sequences ÷ 2000 seq/s × 2 services ≈ 25 seconds

**Explanation**: Both services are fully CPU-based, with millisecond-level inference and models of only 1-2 MB. Running them first imposes no burden but yields huge gains — an estimated 3000-5000 toxic/allergenic peptides are eliminated.

**Why not start with HemoPI2**: Loading ESM-2 t6 for HemoPI2 requires 1.5 GB and about 30 seconds of model loading time. Using ToxinPred3 and AlgPred2 to eliminate several thousand sequences first and then processing the remainder with HemoPI2 does not increase total time, yet within those few dozen seconds after Stage 1 finishes, the most important safety filtering is already done.

### Stage 2: Fast Scoring + Ranking

**Precondition**: after Stage 1, about 100-200 sequences remain (currently 107 measured)

**Services involved**: AnOxPePred, MHCflurry, pLM4CPPs (optional: BepiPred-3.0)

**Note**: The current Stage 1 output is already only 107 sequences, so Stage 2 does not need tiered screening — all optional services can be applied directly.

**Startup strategy**: 107 peptides is a tiny volume, so all services are called in parallel at once. Loading AnOxPePred (500 MB) + MHCflurry (1 GB) + pLM4CPPs (1.5 GB) + BepiPred-3.0 (4 GB) at the same time takes about 7 GB of VRAM, no strain in a 48 GB environment.

**Estimated time** (107 sequences):
- AnOxPePred: 107 ÷ 200 seq/s ≈ 1 second
- MHCflurry: 107 ÷ 500 seq/s ≈ 0.2 seconds
- pLM4CPPs: 107 ÷ 200 seq/s ≈ 0.5 seconds
- BepiPred-3.0: 107 ÷ 50 seq/s ≈ 2 seconds
- **About 5-10 seconds in total** (mostly network latency and cold start)

**Ranking strategy**: Compute a weighted score from AnOxPePred (weight 0.50) + BepiPred (0.20) + pLM4CPPs (0.15) + MHCflurry (inverted 0.10) + GraphCPP (0.05). Take the top 50-80 sequences by composite score into Stage 3.

**HemoPI2 has already finished running in Stage 1**, so it does not need to be repeated in Stage 2.

**Why TIPred and SoDoPE are not in Stage 2**:
- TIPred predicts tyrosinase inhibition — that is a specific function and not an essential attribute of antioxidant peptides, so it does not participate in scoring.
- SoDoPE predicts solubility — peptide-level solubility has no reference value for fusion proteins, so it is moved to Stage 6 for construct-level evaluation.

### Stage 3: Precise Scoring (Optional)

**Precondition**: after Stage 2, 107 sequences remain (currently measured)

**Services involved**: TemStaPro (ProtT5-XL, 6 GB VRAM, optional run)

**Explanation**: Stage 2 has already run all 5 scoring services, so Stage 3 only adds the TemStaPro thermostability prediction. Because TemStaPro must download the 3 GB ProtT5-XL model (HuggingFace network may be slow), this stage is optional.

**If TemStaPro is available**: Run it on the top 80 peptides with an additional weight of 0.05. After inclusion the weights are: AnOxPePred 0.50 / BepiPred 0.20 / pLM4CPPs 0.15 / MHCflurry 0.10 (inverted) / GraphCPP 0.05 / TemStaPro 0.05.

**If it is not available**: Skip it; the later flow is unaffected.

### Stage 4: Enumeration + Construct-Level FASTA Scoring

Enumeration logic: selected peptides × 6 linkers × 3 position schemes. The position schemes are:
- Functional peptide at the N-terminus: `[Func] + [Linker] + [Silk] + [His6]`
- Functional peptide at the C-terminus: `[Silk] + [Linker] + [Func] + [Linker] + [His6]`
- At both ends: `[Func] + [Linker] + [Silk] + [Linker] + [Func] + [Linker] + [His6]`

Enumeration involves no computation at all — pure string concatenation, done instantly.

**Construct-level FASTA scoring**: After enumeration, each construct receives two scores:
1. **Peptide composite score** (inherited from Stage 2): the weighted score of AnOxPePred + BepiPred + pLM4CPPs + MHCflurry + GraphCPP
2. **SoDoPE solubility score**: predicts the solubility of the full-length fusion protein (<1 ms/sequence, extremely fast)
3. **TemStaPro thermostability score** (optional): if Stage 3 has been run

**Ranking logic — grouping by functional peptide**: To align with the experimental design (once a functional peptide is chosen, it will be optimized regardless of which position it occupies), the ranking no longer treats the construct at each position as an independent individual, but groups by (peptide, linker):

1. Treat the 3 positions of the same peptide × the same linker as one group
2. Within the group, take the highest G-FASTA composite score to represent the group
3. Sort by group and select the Top K groups
4. Retain all 3 positions of each group → enter 3D structure prediction (K × 3 constructs)

**G-FASTA composite score formula**: peptide composite score × 0.60 + SoDoPE × 0.30 + TemStaPro × 0.10 (if available)

**Why it is designed this way**:
- After selecting a functional peptide, experiments need to test all three positions — N-terminus, C-terminus, and both ends — to form a control
- Group-based ranking ensures that a whole (peptide, linker) group is selected, rather than scattered individual positions
- 3D structure prediction uses ESMFold (fast enough), so predicting all three positions carries no cost burden

**Rationale for choosing SoDoPE**: SoDoPE looks up dipeptide composition and does not depend on sequence length (<1 ms/sequence); its predictions for full-length fusion proteins (380–438 aa) are more reliable than for short peptides. The other scoring services (AnOxPePred, BepiPred, etc.) were all trained on short peptides (5–50 aa) and are not suitable for running on full-length constructs.

**Optional linkers**: 6 selected from the 10 in linker.fasta (Flex_GGGGSx1/x2, Rigid_EAAAKx1/x2, Helix_AEAAAKEAAAKA, Silk_like_GS), covering flexible/rigid/helical/silk-derived types.

**Output**: Top K groups × 3 positions = K×3 constructs with FASTA + scoring details → Stage 5 (3D structure prediction).

### Stage 5: 3D Structure Prediction

This is the bottleneck. ESMFold pulled 3D prediction from “several days” down to “one hour”, but it is still the most expensive step in the pipeline.

**Tool selection**:

| Tool | Role | Rationale |
|------|------|-----------|
| **ESMFold** | **Primary** | ~8 GB VRAM, 1-3 minutes/sequence, no Docker, no database. The most practical choice for this project's fusion proteins (350+ aa) |
| AlphaFold3 | High-accuracy fallback | 48 GB VRAM available; first run takes about 2 hours (including database installation), then 30-120 minutes per sequence. Use only when ESMFold pLDDT is too low |
| PEP-FOLD4 | ❌ Not usable | Supports only 5–40 aa; cannot handle 350+ aa fusion proteins |

**Concurrency strategy**: The structure service template defaults to concurrency 3 (Semaphore(3)). Three concurrent ESMFold runs need about 8 GB × 3 = 24 GB of VRAM. A 48 GB environment is enough for 3 or even more. The actual safe concurrency is determined by stress testing.

**Resource conflict**: ESMFold is a native GPU service (no Docker needed), so it is enough to shut down the heavy services of Stages 2/3 to free VRAM. CPU services (ToxinPred3, AlgPred2, TIPred, SoDoPE) can be left running.

**Total time estimate** (48 GB GPU, ESMFold concurrency 3, assuming 2 minutes per sequence):
- 36 constructs (K=2): 36 × 2 minutes ÷ 3 concurrency ≈ **24 minutes**
- 54 constructs (K=3): 54 × 2 minutes ÷ 3 concurrency ≈ **36 minutes**
- If AF3 is involved (1-2 constructs): an additional 30-120 minutes each

**Confidence filtering**: The pLDDT score output by ESMFold serves as the quality metric. Structures with pLDDT < 70 are flagged as low quality and considered for final validation with AF3. Structures with pLDDT < 50 are excluded directly.

**Caching**: After each construct's structure is computed, cache the PDB file by the SHA256 hash of its sequence. The next run reads the cache directly for the same sequence.

**How AF3 is called**: The AlphaFold3 microservice invokes the AF3 container through the Docker CLI (see `tools/AlphaFold3/service.py`), submitting jobs in async job mode (`POST /predict/async`) and polling for results (the `predict_structure_async()` method of `client.py`). The pipeline only needs to send requests and wait for results; it does not need to manage Docker containers directly.

### Stage 6: PDB Evaluation

Once the 3D structures are ready, SASA (1-5 seconds each) and Aggrescan3D (1-15 minutes each) evaluate the protein-level properties of the constructs.

SASA performs exposure analysis of the functional peptide: a peptide buried inside fails, while a peptide exposed on the surface can work. Aggrescan3D performs aggregation risk analysis: high risk means the protein is unstable.

**VRAM**: SASA and Aggrescan3D are both CPU services and do not conflict with ESMFold from the previous stage. However, Aggrescan3D runs through a Docker container, so check whether the Docker service is available.

**Total time**: Assuming 50 constructs, SASA takes about 2-4 minutes (concurrency 10) and Aggrescan3D about 25 minutes to 12 hours (concurrency 2, 1-15 minutes per sequence). Aggrescan3D is the new bottleneck here — its runtime can be comparable to 3D prediction.

After that, the peptide scores (Stage 3) and PDB scores (Stage 6) are aggregated and weighted to produce the final ranking report.

---

## 4. GPU VRAM Management Plan

The current strategy depends on the GPU's VRAM capacity. We have only one GPU, so it must be time-shared.

### Stage Allocation

| Pipeline stage | Services running on the GPU | VRAM usage | Duration |
|----------------|-----------------------------|------------|----------|
| Stage 1 | None (all CPU) | 0 | <1 minute |
| Stage 2 | AnOxPePred, MHCflurry, HemoPI2 (optional) | ~3-4 GB | ~6 minutes |
| Stage 3 | BepiPred-3.0, pLM4CPPs, GraphCPP | ~6-7 GB | ~5 minutes |

(The reason Stages 2 and 3 load in two batches: BepiPred-3.0's ESM-2 650M + DenseNet needs 4 GB, and loading it together with Stage 2's services may overwhelm low- and mid-range GPUs. Splitting into two batches keeps the VRAM pressure of each batch low.)

| Pipeline stage | Services running on the GPU | VRAM usage | Duration |
|----------------|-----------------------------|------------|----------|
| Stage 5 | ESMFold (AF3 fallback) | **~8 GB × concurrency** | 24–36 minutes (+ optional AF3) |
| — Transition — | Shut down the heavy services of Stages 2/3; CPU services need not be shut down | — | — |
| Stage 6 | None (all CPU) | 0 | 1-12 hours |

**Key change**: There is no longer any need to clear the entire GPU for AF3. ESMFold's ~8 GB VRAM requirement means Stage 5 can coexist with Stage 6's CPU services (PDB evaluation can even start right after ESMFold finishes, wasting no waiting time).

### One Contradiction

TemStaPro (ProtT5-XL, 6 GB, 20 seq/s) is an awkward presence. It is not in the weight table and does not participate in scoring, yet it consumes 6 GB of VRAM. If it is only meant to provide thermostability reference information to end users, it can be run in CPU mode on the top 100 peptides for a few minutes without affecting VRAM planning. This decision is up to the user — if thermostability is not important for our fusion proteins, simply do not run it.

---

## 5. Adaptive Pipeline Logic

We do not know how many sequences will remain after each step. So the pipeline cannot be controlled by hard-coded numbers; instead it is given a “target range + adjustment strategy”.

### Example Flow (based on current measured data)

```
Initial: 1843 antioxidant peptides (function.csv + function_3.csv merged)

Stage 1 (hard filtering, completed):
  Input: 1843 sequences
  ToxinPred3 eliminates 656 sequences (toxicity)
  AlgPred2 eliminates 1077 sequences (allergenicity)
  HemoPI2 eliminates 3 sequences (hemolysis)
  Output: 107 sequences ✅

Stage 2 (fast scoring + ranking):
  Input: 107 sequences
  Call AnOxPePred + BepiPred + pLM4CPPs + MHCflurry + GraphCPP
  After weighted scoring, take the top 80 sequences

Stage 3 (precise scoring, optional):
  If the TemStaPro model is ready: add thermostability scores
  If not ready: skip

Stage 4 (enumeration + Construct FASTA scoring):
  Input: Top 20 peptides × 6 linkers × 3 positions = 360 constructs
  Call SoDoPE to score the solubility of each construct
  Group by (peptide, linker), rank by the highest score within each group → select Top K groups
  Output all 3 positions per group → K×3 constructs go to 3D

Stage 5 (3D structure prediction):
  30 constructs × ESMFold (concurrency 3, ~2 min/sequence) ≈ 20 minutes
```

The parameters of the adaptive logic can be configured by the user:
- Default: enumerate Top 20 peptides → SoDoPE scoring → take the top 30 constructs into 3D
- Aggressive mode: enumerate Top 80 peptides → 1440 constructs; SoDoPE handles this easily (<1 sec)
- Conservative mode: enumerate Top 10 peptides → 180 constructs, reducing computation

---

## 6. The “Run Only Some Stages” Design

Users may not need to run the full flow every time. For example, they may want only peptide-level screening (Stages 1 to 3) without 3D prediction. Or they may already have PDB files and want only PDB evaluation (Stage 6).

Each stage's output is written to the output directory in a self-describing format (including a parameter snapshot). On the next run, the pipeline checks the output directory and skips that stage directly if it exists and the parameters are unchanged.

This mechanism also makes debugging friendlier: if you find a configuration error after Stage 1 finishes, fix the configuration and rerun, and the pipeline automatically starts from Stage 2 without rerunning the filtering of several thousand sequences.

---

## 7. Configuration Item Design

Configuration items fall into two categories:

Screening-strategy type (affects pipeline behavior):
- Function type: which function of peptide to screen for (antioxidant, antimicrobial, anti-glycation, …)
- Retention targets per stage: what percentage to retain in Stage 2, how many sequences are expected to be retained in Stage 3
- Adaptive mode: conservative / balanced / aggressive
- Enumeration rules: whether the two ends may carry different peptides, whether the linker is unified
- Weights: the weight of each scoring service (defaults exist and can be overridden)

Run-mode type (does not affect screening results, only how it runs):
- Test mode: load only 100 or 1000 sequences to verify that the flow is correct
- Cache path, output path
- Which stages to skip (run from scratch, start from Stage 2, run only PDB evaluation, …)

These configurations live in a `.env` file and are read when the pipeline starts. All items have defaults, so users only need to override what they want to change. Switching function type (for example, from antioxidant to antimicrobial) requires changing only `FUNCTION_TYPE=antimicrobial`.

---

## 8. Implementation Strategy: One Step at a Time

Do not try to implement the whole pipeline at once. Instead build it step by step, producing usable intermediate results at each step, and adjust the next step based on actual conditions.

### Step 1: Stage 1 (Hard Filtering)

Implement the Stage 1 logic in `main/pipeline.py`: load data → call ToxinPred3 + AlgPred2 → output the filtered peptide list.

**Output**: a safe set of peptide candidates, written to `output/stage01/`.
**Verifiable**: check whether known toxic/allergenic peptides are excluded from the output.
**Time**: ~25 seconds (25000 sequences).

### Step 2: Stage 2 (Fast Scoring + Ranking)

Take Stage 1's output (107 sequences) → call AnOxPePred + MHCflurry + pLM4CPPs + BepiPred-3.0 + GraphCPP → weighted scoring → take the top 50-80 sequences.

**Note**: TIPred (tyrosinase inhibition) does not participate in antioxidant scoring. SoDoPE (solubility) is moved to construct-level evaluation.

**Output**: a list of the top 50-80 functional peptides, written to `output/stage02/`.
**Verifiable**: whether the top-ranked peptides are clearly superior in antioxidant activity to those ranked lower.
**Time**: ~5-10 seconds (107 sequences is a tiny volume).

### Step 3: Stage 3 (Precise Scoring, Optional)

Take Stage 2's top 80 → if a TemStaPro model is ready, add thermostability scores (weight 0.05); if not ready, skip.

**Output**: optional reranked results, written to `output/stage03/` (if skipped, Stage 4 reads directly from Stage 2).
**Time**: ~5 seconds (80 sequences, if TemStaPro is available).

### Step 4: Stage 4 (Enumeration + Construct FASTA Scoring)

Take Stage 2's top 80 → enumerate Top 20 peptides × 6 linkers × 3 positions = 360 constructs → call SoDoPE scoring → **group by (peptide, linker), take the highest score within each group** → select the Top K groups → output all positions.

Each group corresponds to 3 positions (N/C/Both), all of which enter 3D structure prediction.
Targets: K=10 → 30 constructs; or K=15 → 45 constructs (ESMFold can handle it).

**Output**: Top K groups × 3 positions = K×3 constructs (with composite scores and FASTA sequences), written to `output/stage04/`.
**Verifiable**: whether the score gaps between positions within the selected groups are reasonable (helps determine which position is optimal).
**Time**: enumeration < 0.1 seconds + SoDoPE < 1 second = instant.

**Note**: SoDoPE is moved to this point to do construct FASTA scoring, so Stage 6 no longer needs to run it again.

### Step 5: Stage 5 (3D Structure Prediction)

Take Stage 4's top 30 constructs → ESMFold predicts 3D structures → pLDDT confidence filtering → low-confidence constructs can optionally be submitted to AF3.

**Output**: a PDB file plus a confidence score for each construct, written to `output/stage05/`.
**Verifiable**: whether the PDB files open normally in PyMOL/VMD, and whether the pLDDT distribution is reasonable.
**Time**: ~20 minutes (ESMFold, 30 sequences, concurrency 3).

### Step 6: Stage 6 (PDB Evaluation + Report)

Take Stage 5's PDB files → SASA + Aggrescan3D → aggregate peptide scores + SoDoPE solubility + PDB scores → generate the final ranking report.
SoDoPE is already done in Stage 4, so it is not repeated here.

**Output**: the final ranking report (including peptide scores, SoDoPE, pLDDT, SASA, Aggrescan3D), written to `output/stage06/`.
**Verifiable**: whether the top-ranked constructs perform consistently across all aspects.
**Time**: ~1-12 hours (Aggrescan3D is the bottleneck).

### Fallback Strategy

If at any step the data quality, microservice availability, or time cost turns out to differ from expectations, you can:
- Stop at that step and accept the previous output as the final result
- Adjust parameters and rerun from that step (reading the previous step's cache)
- Skip that step (for example, skip 3D prediction)

This strategy ensures that every step produces output, so the situation never arises where you write half of it and then discover that everything must be overturned.

---

## 9. Context Management for the AI Executor

The main executor of this plan is Claude (an AI coding assistant), whose context window is limited. After each session ends, Claude's “memory” exists only in files on disk. The following mechanisms ensure that the executor can recover after an interruption.

### 9.1 External State Anchors

```
output/
├── STATUS.md              ← latest state pointer (open it anytime to see progress)
├── status/
│   ├── status_2026-05-13_2301.md   ← timestamped snapshot, archived on every change
│   ├── status_2026-05-13_2311.md
│   └── status_2026-05-13_2315.md
├── stage01_filter/        ← independent directory per stage
│   ├── README.md          ← full report for this stage (what was done, why, what the results were)
│   ├── run.log            ← raw run log
│   └── round1_toxinpred3/ ← detailed data per round
│       ├── passed.csv     ← passed data
│       └── failed.csv     ← eliminated data (the elimination reason for each entry is traceable)
└── stage02_score/
    └── ...
```

**Recovery protocol**:
1. Open `output/STATUS.md` → know the current progress, configuration, and next step
2. Open the latest stage's `README.md` → know the previous step's decisions and results
3. Read `passed.csv` (a few KB to a few tens of KB, far smaller than the raw data) → obtain the input data
4. Continue with the next stage

### 9.2 Why Standalone Scripts

Each stage is an independent Python script (`main/stages/stageXX_*.py`) rather than one giant `pipeline.py`:
- **A single script runs independently**: `python -m main.stages.stage01_filter`, with no dependency on an orchestrator
- **Script content is self-describing**: comments at the top explain the inputs, outputs, and usage
- **Failure isolation**: a Stage 1 failure does not affect Stage 2's code
- **Flexible parameters**: each script can adjust its parameters (thresholds, weights, etc.) independently without affecting other stages

### 9.3 Files as Memory

The executor does not remember data, only paths:
- The 1843 processed peptides → no need to remember any single sequence, just that they exist in `output/stage01_filter/`
- Microservice responses → written to JSON/CSV, occupying no conversation context
- Elimination reasons → written to failed.csv, where each row has the corresponding round's service name and score
- Decision rationale → written to README.md, read directly next time

### 9.4 Timestamped Audit Trail

Every key operation (stage completion, configuration change, decision adjustment) saves a timestamped snapshot of STATUS.md to `output/status/`. Anyone can trace the pipeline's full evolution: what results the first run produced, what parameters were changed, and what was different the second time.

---

## 9. Open Questions

**Actual inference speed of ESMFold**: The 1-3 minutes figure is an estimate for 350+ aa fusion proteins. The first cold start (loading the model onto the GPU) takes ~30-60 seconds. A real measurement is needed to confirm the true throughput.

**Safe concurrency for ESMFold**: 3 concurrent runs need ~24 GB of VRAM; a 48 GB environment could theoretically go to 4-5 concurrent runs. But if each ESMFold process peaks above 8 GB of VRAM, that must be lowered. Run a stress test on the actual GPU to determine it.

**Time gap between AF3's first run and later runs**: A 6 aa sequence took 2 hours — how much of that was database installation? How long does each subsequent 350+ aa construct actually take? This data determines whether “validating key constructs with AF3” is realistic.

**Whether to run TemStaPro**: It occupies 6 GB of VRAM, a 3 GB model, and 20 seq/s throughput, but it is not in the weight table. If it is only to add a thermostability reference to the final report, it can be run in CPU mode on the final few dozen sequences. If not needed, simply skip it and save a dozen-plus minutes and 6 GB.

**Aggrescan3D's per-sequence time (1-15 minutes) and concurrency limit (2)** may mean 4-6 hours on 50 constructs. This time may exceed ESMFold's structure prediction time. If time is tight, Aggrescan3D evaluation can be deferred until the final TOP 10 has been selected.

**Whether AlphaFold3 should still be kept**: The hardware is available (48 GB VRAM), but a 6 aa sequence took 2 hours (including the first database installation). If subsequent 350+ aa sequences stabilize at 30-60 minutes each, it is feasible to use AF3 only to validate the key constructs where ESMFold pLDDT < 70. If every run takes 2 hours, skip it.



---

---
