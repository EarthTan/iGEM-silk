> English translation of [DryLab-Progress-Report.md](DryLab-Progress-Report.md). The Chinese original is kept unchanged as the source of truth.

# Dry Lab Progress Report

**Project**: iGEM-silk silk fibroin fusion functional peptide design platform
**Date written**: 2026-05-20
**Audience**: project supervisor (biology background)

---

## I. Project background and objectives

### 1.1 Scientific question

Silk fibroin is the main protein component of silk and has excellent self-assembly capability and film-forming properties. Our goal is to fuse short peptides with specific biological activity (functional peptides) to silk fibroin, so that the recombinant protein combines the advantages of both — silk fibroin provides structural support and delivery capability, while the functional peptide exerts biological activities such as antioxidant and whitening effects.

Such fusion proteins have broad application prospects in topical medical-aesthetics scenarios (such as skincare products and functional dressings).

### 1.2 Core challenges

Screening the functional peptide candidates most suitable for fusion from biological sequence databases (for example, UniProt contains 225 million sequences) faces the following challenges:

- **Enormous candidate scale**: the raw sequences number in the hundreds of millions, so experimental validation one by one is impossible
- **Multi-dimensional evaluation needs**: antioxidant activity, safety (toxicity, hemolysis, allergenicity), structural stability, and peptide exposure must all be considered at the same time
- **Trade-offs among multiple metrics**: different metrics trade off against each other and must be evaluated in a scientifically sound, integrated way

### 1.3 Our approach

We designed a computational screening pipeline that, through multiple rounds of funnel screening, gradually converges from hundreds of millions of candidates to a hundred top candidates, which are then submitted for wet-lab validation.

---

## II. Technical approach

### 2.1 Pipeline architecture: funnel-style multi-round screening

Our screening system is divided into 8 rounds, each progressively tightening the number of candidates:

```
Round 0 (data preprocessing): 850 million → 19.9 million
    ├── Length filter (3-30 amino acids)
    ├── Standard amino acid filter
    └── Deduplication

Round 1 (antioxidant sorting): 19.9 million → ~2 million
    ├── Antioxidant activity prediction
    └── Dual-channel sorting (Top 10% with the best antioxidant activity + Bottom 1% with the worst antioxidant activity as negative controls)

Round 2 (safety screening): ~2 million → ~1.5 million
    ├── Toxicity prediction: ≥ 0.38 eliminated
    ├── Hemolysis prediction: ≥ 0.55 eliminated
    └── Immunogenicity prediction: ≥ 0.50 eliminated

Round 3 (deep scoring): ~1.5 million → ~75 thousand
    ├── B-cell epitope prediction
    ├── Thermal stability prediction
    ├── Solubility prediction
    ├── Cell-penetrating peptide prediction
    └── Composite scoring (variance-driven weighting)

Round 4 (construct enumeration): ~75 thousand → ~22.5 thousand fusion constructs
    ├── Fusion position enumeration (N-terminus / C-terminus / both ends)
    ├── Linker enumeration (flexible / rigid)
    └── Assembly of full-length sequences

Round 5 (3D structure prediction): ~22.5 thousand → all pass through
    ├── OmegaFold deep learning structure prediction (workhorse, run on the full set)
    └── AlphaFold3 high-precision validation (only Top 10 + Bottom 10)

Round 6 (structure evaluation): ~22.5 thousand → scored in full
    ├── Solvent-accessible surface area (SASA): degree of peptide exposure
    └── Aggregation propensity analysis: protein aggregation risk

Round 7 (final ranking): Top 100 + Bottom 100
```

**Overall elimination rate**: > 99.99% (from 19.9 million candidates to 100 final candidates)

### 2.2 Sixteen microservices

We built 16 microservices to support pipeline operation, divided into three categories:

#### (1) Functional activity prediction services

| Service | Port | Function | Plain-language explanation |
|------|------|------|---------|
| **AnOxPePred** | 8001 | Antioxidant activity prediction | How strong is this peptide's ability to scavenge free radicals |
| **BepiPred-3.0** | 8002 | B-cell epitope prediction | Is this peptide easily recognized by the immune system |
| **pLM4CPPs** | 8006 | Cell-penetrating peptide prediction | Can this peptide enter cells |
| **GraphCPP** | 8009 | Cell-penetration prediction (GNN, graph neural network) | Another method for predicting cell-penetration ability |
| **TemStaPro** | 8010 | Thermal stability prediction | Is this peptide stable at high temperature |
| **SoDoPE** | 8012 | Solubility prediction | How well this peptide dissolves in water |

#### (2) Safety assessment services

| Service | Port | Function | Plain-language explanation |
|------|------|------|---------|
| **ToxinPred3** | 8003 | Toxicity prediction | Is this peptide toxic |
| **HemoPI2** | 8004 | Hemolysis prediction | Does this peptide cause red blood cells to rupture |
| **MHCflurry** | 8005 | Immunogenicity prediction | Does this peptide trigger an immune response |
| **AlgPred2** | 8008 | Allergen prediction | Does this peptide cause allergies |

#### (3) Structure prediction and evaluation services

| Service | Port | Function | Plain-language explanation |
|------|------|------|---------|
| **AlphaFold3** | 8201 | 3D structure prediction (high precision) | The state-of-the-art structure prediction model developed by DeepMind; highest accuracy but high computational cost |
| **OmegaFold** | 8204 | 3D structure prediction (workhorse) | Our main structure prediction tool, balancing speed and accuracy |
| **SASA** | 8101 | Solvent-accessible surface area | The degree to which the peptide is exposed on the protein surface (higher is better, meaning the functional peptide can act more easily) |
| **Aggrescan3D** | 8102 | Aggregation propensity analysis | Whether this protein will aggregate abnormally (lower is better) |

> **Note**: AlphaFold3 is the state-of-the-art protein structure prediction model released by DeepMind in 2024 and enjoys very high international recognition. Because its computational cost is high, we use it to perform high-precision structure validation on the final Top 10 and Bottom 10 candidates, strengthening the credibility and academic recognition of the results. OmegaFold serves as the workhorse tool and is responsible for structure prediction across the full screening set.

### 2.3 Docker microservice architecture

All 16 services are encapsulated and run in Docker containers, which brings the following benefits:

- **Environment consistency**: avoids inconsistent run results caused by configuration differences between servers
- **On-demand startup**: there is no need to run all services at once; only the 3-5 services required by the current round are started, saving computing resources
- **GPU resource management**: some services (such as OmegaFold) require a GPU, and on-demand startup avoids contention for GPU memory

```bash
# Example of starting all services
cd tools && docker compose --profile gpu up -d          # GPU services
docker compose --profile cpu up -d                          # CPU services

# Start a single service on demand
docker compose --profile cpu up -d anoxpepred algpred2
```

### 2.4 Dual-channel design

To ensure the scientific rigor of the screening, we designed dual-channel parallel screening:

- **Top channel**: the candidate peptides with the best antioxidant activity
- **Bottom channel**: the candidate peptides with the worst antioxidant activity (as negative controls)

Both groups of candidates go through the same safety screening and structure evaluation process. In the end, the two groups are ranked independently and output together. This verifies that if a peptide has "poor antioxidant activity but good values on all other metrics", it should also show corresponding characteristics in the negative controls, thereby ruling out false positives.

---

## III. Technical difficulties and innovations

### 3.1 Variance-aware weighting: let the data decide which metric matters more

The traditional weighted scoring approach presets weights by hand (for example, antioxidant 50%, toxicity 13%, hemolysis 9%, etc.). The problem with this is that the discriminative power of different metrics varies across batches of data — if all candidates in the current pool are similar on some metric (poor discriminative power), giving it an even higher weight is meaningless.

**Our innovation**: first let all candidates finish scoring, then analyze the score distribution (standard deviation) of each metric; metrics with good discriminative power automatically receive higher weights.

```
The larger the standard deviation σ_i → the better the discriminative power of that metric → the higher the weight
```

This avoids setting weights "by gut feeling" and lets the data speak for itself.

### 3.2 Hard thresholds on safety attributes: not a "compensable" scoring item

In stages2 (the old pipeline), we mixed safety metrics (toxicity, hemolysis, allergenicity) into the composite score with low weights. This meant that a peptide with extremely poor hemolytic properties could still rank near the top on the composite score as long as its antioxidant score was high enough.

**The flaw we found**: safety attributes became scoring items that "could be compensated for by the antioxidant score", which violates the basic principles of drug safety.

**The fix in stages4 (the new version)**: safety attributes use hard thresholds — pass/eliminate, and they do not participate in any score mixing. As long as hemolysis exceeds the threshold, the candidate is eliminated directly no matter how excellent its other metrics are.

### 3.3 Antioxidant used only once: avoiding dual-channel contamination

In stages2, although pure antioxidant scores were used during dual-channel sorting, the antioxidant weight remained implicitly embedded in the composite score in later rounds, so the Bottom channel (poor antioxidant activity) was in fact still affected by residual antioxidant weight.

**The fix in stages4**: the antioxidant score is used only once, during the Round 1 sorting; once the channel is determined, no later round uses the antioxidant score for ranking. The two channels are truly independent.

### 3.4 The OmegaFold blocking problem and its solution

OmegaFold's deep learning inference is a synchronous operation that blocks the computer's asynchronous event-processing framework. We use a semaphore (Semaphore) to limit concurrency to 1, ensuring that only one inference task runs at a time and avoiding blocking.

### 3.5 Docker network optimization

Early on we accessed services in Docker containers through the local port (127.0.0.1) and found that long-running requests would intermittently hang. After switching to direct connections via the Docker internal bridge network IP, the problem was resolved.

---

## IV. Results achieved

### 4.1 stages2 completion status

| Metric | Value |
|------|------|
| Input candidates | 1,081,772 |
| Final output | 90 Top candidates + 60 Bottom controls |
| Elimination rate | 99.986% |
| Total runtime | ~6.5 hours |
| 3D structure prediction | 150 PDB files |
| Mean pLDDT | 0.41 (structure confidence) |
| Mean SASA | 0.70 (degree of peptide exposure) |
| Mean Aggrescan3D | 0.35 (aggregation risk, lower is better) |

**Top 5 candidates (ranked by final score)**:

| Rank | Fusion construct | Functional peptide sequence | Final score |
|------|---------|-----------|---------|
| #1 | con_0215 | ERELPYYPGAHPMHPPK | 0.779 |
| #2 | con_0199 | GTHWHPEHF | 0.768 |
| #3 | con_0226 | EPTMYGEILSPNYPQAYPSEV | 0.735 |
| #4 | con_0201 | GTHWHPEHF (dual-site fusion) | 0.722 |
| #5 | con_0095 | PAFELHYPHMVER | 0.714 |

### 4.2 stages3 Stage 0 completion status

| Metric | Value |
|------|------|
| Sequences scanned | 849 million |
| Passed preprocessing | 19.9 million candidates |
| Processing time | 98.7 minutes |
| Database size | 2.6 GB |
| UniProt pass rate | 0.33% |
| MGnify pass rate | 3.07% |

Data sources:
- **UniProt**: annotated protein database (225 million entries, 102 GB)
- **MGnify**: metagenomic protein cluster database (~624 million entries, 120 GB)

### 4.3 stages4 design completed

The complete stages4 code has been written (8 round scripts + database interface + Docker utility functions + weighting engine) and awaits an actual run.

**Core improvements over stages2**:
- Safety attributes use independent hard thresholds and are no longer mixed into the weighted average
- The antioxidant score is used only in the first round of sorting
- The two channels are truly isolated and ranked independently
- A two-layer mechanism combining variance-aware weighting with manual adjustment coefficients
- Unified DuckDB state management with support for checkpoint and resume

### 4.4 AlphaFold3 high-precision structure validation plan

We plan, after the stages4 final ranking, to use AlphaFold3 to perform high-precision 3D structure prediction on the Top 10 and Bottom 10 candidates.

**Why choose AlphaFold3**:

| Consideration | Explanation |
|------|------|
| **Academic recognition** | AlphaFold3 is the state-of-the-art model released by DeepMind in 2024, with extremely high citations and recognition in top journals such as Nature and Science |
| **Accuracy assurance** | Compared with OmegaFold, AlphaFold3 is more reliable in protein structure prediction accuracy |
| **Validation value** | Validating our computational screening results with the most authoritative tool recognized by the field enhances academic credibility |

**Execution strategy**:
- OmegaFold full-set prediction (22.5 thousand constructs, for screening)
- AlphaFold3 refinement validation (Top 10 + Bottom 10, high-confidence validation)

---

## V. Current progress and future plans

### 5.1 Current progress overview

| Pipeline | Status | Input data | Current output |
|----------|------|---------|---------|
| **stages2** | ✅ Complete (has design flaws) | 1.08 million | 90 Top + 60 Bottom |
| **stages3 Stage 0** | ✅ Complete | 850 million | 19.9 million candidates |
| **stages4** | 🚧 Code ready, awaiting run | 19.9 million | Top/Bottom 100 |

### 5.2 Next steps

#### Short term (1-2 months)

1. **Complete the actual stages4 run**: execute the full 8 rounds of screening on the 19.9 million candidates and output Top 100 + Bottom 100
2. **AlphaFold3 high-precision validation**: perform AlphaFold3 structure prediction on the Top 10 + Bottom 10 candidates to strengthen academic recognition
3. **Wet-lab validation**: select the Top 5-10 candidates for in vitro antioxidant activity assays, cytotoxicity tests, etc.

#### Medium term (3-6 months)

3. **Build a web platform**: develop a visual web interface for medical-aesthetics companies to query and use

### 5.3 Future platform plan

**Platform positioning**: a functional peptide candidate query and assisted design platform for medical-aesthetics enterprises

**Usage scenario**:

```
Medical-aesthetics company researcher
    │
    ▼
Log in to the platform web page
    │
    ▼
Enter requirements:
- Target function (antioxidant / whitening / anti-aging ...)
- Administration route preference
    │
    ▼
Platform queries the database
    │
    ▼
Output:
- List of matching candidate peptides (with scores)
- Whether wet-lab validation results are available
- Structure display (SASA distribution plot)
- Safety assessment report
```

**Core features**:

| Feature | Explanation |
|------|------|
| **Candidate peptide search** | Filter candidates by function type, score range, and safety |
| **Validation status query** | Which candidates already have wet-lab validation and what the results were |
| **Structure visualization** | Display the 3D structure of the fusion protein |
| **Assessment report generation** | One-click generation of a PDF on the safety and function of a candidate peptide |
| **Candidate peptide customization** | Provide a sequence and the platform returns fusion position and linker recommendations |

**Technical architecture**:

- **Frontend**: responsive web pages, supporting PC and tablet access
- **Backend**: FastAPI microservice architecture
- **Database**: DuckDB storing candidate peptide data and assessment results
- **Deployment**: Docker containerization with support for horizontal scaling

---

## VI. Summary

We have built a complete computational screening platform for silk fibroin fusion functional peptides, with the following characteristics:

1. **Scale**: round-by-round screening from hundreds of millions of candidate sequences, converging to a hundred top candidates
2. **Multi-dimensional evaluation**: integrating 16 specialized prediction services, covering the full range of functional activity, safety, and structural properties
3. **Scientific rigor**: dual-channel design, double-blind controls, and hard thresholds on safety attributes ensure reliable results
4. **Iterative improvement**: from stages2 to stages4, design flaws were continually found and optimized, reflecting an engineering mindset

At present, stages2 has completed the full workflow, stages3 Stage 0 has completed data preprocessing, and the stages4 code is ready and awaiting a run. We plan, after completing the stages4 run, to advance wet-lab validation and gradually build a web platform for medical-aesthetics enterprises.

---

**Contact and collaboration**: If you have any questions or need further technical explanation, please feel free to reach out at any time.
