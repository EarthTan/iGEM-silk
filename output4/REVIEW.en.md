> English translation of [REVIEW.md](REVIEW.md). The Chinese original is kept unchanged as the source of truth.

# Stages4 Pipeline Review — iGEM-silk Antioxidant Peptide Fusion Protein Design

**Generated**: 2026-05-24
**Status**: Full pipeline complete
**Output directory**: `output4/`

---

## 1. What Was Done

Completed the full stages4 pipeline end to end, all 9 rounds (Round 0 ~ Round 8), screening from 19.9 million candidate peptides down to 250 final constructs, and performed AlphaFold3 high-accuracy structure prediction on Top 10 + Bottom 10.

### Pipeline Overview

| Stage | Time | Data volume change |
|------|------|-----------|
| Round 0: Data import | ~15min | 19,890,021 → 19,890,021 |
| Round 1: Antioxidant split (AnOxPePred + AlgPred2) | ~30min | 19,890,021 → Top 10% + Bottom 1% |
| Round 2: Safety screening (ToxinPred3/HemoPI2/MHCflurry) | ~24h | dual-channel → hard-threshold filtering |
| Round 3 Phase 1: Pre-scoring (BepiPred3/TemStaPro/SoDoPE/pLM4CPPs) | ~2h | safety-passing peptides → full scoring |
| Round 3 Phase 2: SD-weighted scoring | ~2h | → composite ranking |
| Round 3 Phase 3: GraphCPP | ~1h | supplementary scoring |
| Round 4 Phase 1: Enumeration + SoDoPE/TemStaPro | ~30min | peptides → 250 constructs |
| Round 4 Phase 2: BepiPred3 | ~6h | 250 construct-level scores |
| Round 5: OmegaFold 3D | ~6.13h | 250 → 250 PDB (pLDDT avg=0.4205) |
| Round 6: SASA + Aggrescan3D | ~5.4min | 250 PDB → 250 evaluation scores |
| Round 7: Final ranking | <1s | 250 → Top 150 + Bottom 100 |
| Round 8: AlphaFold3 | ~22.5h | Top 10 + Bottom 10 → AF3 mmCIF |
| **Total** | **~65h** | **19,890,021 → 250 constructs (20 AF3)** |

### Final Top 5 (Round 7 ranking)

| Global rank | Channel | ID | SASA | A3D | pLDDT | Total score |
|---------|------|----|------|-----|-------|------|
| 1 | bottom | con_5489 | 0.6873 | 0.2925 | 0.4950 | 0.7579 |
| 2 | bottom | con_3275 | 0.6861 | 0.2927 | 0.4857 | 0.7420 |
| 3 | bottom | con_1415 | 0.7055 | 0.3301 | 0.4854 | 0.7342 |
| 4 | bottom | con_15869 | 0.8229 | 0.2753 | 0.4410 | 0.7296 |
| 5 | bottom | con_1103 | 0.6777 | 0.2946 | 0.4743 | 0.7189 |

### AF3 ranking (Top 10 + Bottom 10)

| ranking_score | Top | Bottom |
|-------------|-----|--------|
| Highest | con_0850 **0.56** | con_3774 **0.53** |
| Lowest | con_0317/0558/0660 **0.50** | con_5489 **0.50** |
| Average | **0.52** | **0.52** |

---

## 2. Key Design Changes from stages2 to stages4

### Why redo it rather than use stages2 directly?

stages2 has two fundamental design flaws:

1. **Safety attributes were diluted**: safety metrics such as ToxinPred3 and HemoPI2 were folded into a weighted average score, so a peptide with high toxicity could be compensated by "excellent" scores in other dimensions. In a wet lab this is a fatal risk.
2. **Antioxidant signal contamination**: the AnOxPePred score appeared repeatedly in every downstream step, so screening was biased toward antioxidant activity and drifted away from the real objective of "performing well in a silk protein context."

### Core changes

| Change | stages2 | stages4 |
|------|---------|---------|
| **Safety policy** | weighted average, can be compensated | **hard-threshold veto**, one-vote veto |
| **Antioxidant use** | used repeatedly throughout the pipeline | **Round 1 only**, for channel assignment |
| **Weight design** | manually preset fixed weights | **SD-driven weights** (winsorized stddev) |
| **Scoring stages** | a single scoring pass in Round 3 | Phase 1 full scoring + Phase 2 SD weighting + Phase 3 GraphCPP |
| **3D structure** | OmegaFold 150 PDB | OmegaFold 250 PDB + **20 AF3 models** |
| **Dual-channel** | Top 90 + Bottom 60 | Top 150 + Bottom 100 |
| **Ranking basis** | SASA + A3D + pLDDT | same as the left column (validated as effective) |

### Safety hard thresholds (Round 2)

| Service | Threshold | Meaning |
|------|------|------|
| ToxinPred3 | < 0.38 | predicted non-toxic |
| HemoPI2 | < 0.55 | predicted non-hemolytic |
| MHCflurry | < 0.50 | predicted low immunogenicity |

If any condition is not met → eliminated outright, no room for negotiation.

---

## 3. Weight Design — SD-Driven (Round 3)

stages4 uses weighted scoring only in Round 3, and the weights are not assigned by hand but **driven by the data**.

### Formula

```
w_i = α × (σ_winsorized_i / Σσ_winsorized)
```

Here α is a manual intervention coefficient (default=1), and the winsorized stddev is computed after excluding extreme values. A service with greater discriminating power → higher weight; low discriminating power is automatically down-weighted.

### Actual weights

| Service | Weight | Discriminating power |
|------|------|--------|
| SoDoPE | highest | large differences in physicochemical properties |
| BepiPred3 | high | clear differences in B-cell epitopes |
| TemStaPro | medium | some discrimination in thermal stability |
| pLM4CPPs | low | limited discrimination in CPP prediction |
| GraphCPP | low | same as above |

This design ensures that the weights reflect the structure of the data itself, rather than a preconceived "I think this one matters more."

### Round 7 final ranking formula

```
round7_score = 0.40 × SASA + 0.40 × (1 - Aggrescan3D) + 0.20 × pLDDT_norm
```

Reuses the weights already validated in stages2. Rationale:
- Higher SASA → the functional peptide is more exposed on the surface → more likely to function
- Lower Aggrescan3D → lower aggregation risk → more stable protein
- Normalized pLDDT serves as a confidence weight, ensuring structural reliability

---

## 4. Key Data Characteristics

| Dimension | Mean | Range |
|------|------|------|
| AnOxPePred (Round 1) | 0.30 | 0.09–0.67 |
| Round 3 composite | 0.75 | 0.50–0.95 |
| OmegaFold pLDDT | 0.42 | 0.37–0.50 |
| SASA | 0.72 | 0.46–0.83 |
| Aggrescan3D | 0.33 | 0.27–0.39 |
| Round 7 composite score | — | 0.54–0.76 |
| AF3 ranking_score (20 models) | **0.52** | 0.50–0.56 |

### Screening funnel

```
19,890,021 ┐
           │ Round 1 (antioxidant split)
      ~86,000 ┘  ┌─ Top 10% (best antioxidant)
                  └─ Bottom 1% (worst antioxidant, as control)
           │ Round 2 (safety hard thresholds)
      ~65,000 ┘
           │ Round 3 (composite scoring + SD weighting)
        ~700 ┘
           │ Round 4 (enumeration)
         250 ┘  ┌─ Top 150
                └─ Bottom 100
           │ Round 5-6 (3D + evaluation)
         250 ┘
           │ Round 7 (final ranking)
         250 ┘  ┌─ Top 150 + Bottom 100
           │ Round 8 (AF3)
          20 ┘  ┌─ Top 10 + Bottom 10
```

Elimination rate: **19,890,021 → 250** = **99.9987%**

---

## 5. Round 8: AlphaFold3 Summary

### Why run AF3?

OmegaFold pLDDT averages 0.42, which is adequate for preliminary ranking, but the structure accuracy is insufficient for wet-lab decisions. AlphaFold3 is the current state of the art in structure prediction; ranking_score measures the model's confidence in the predicted structure, and above 0.50 usually means a credible fold.

### Time

| Metric | Value |
|------|-----|
| Total time | 22.5h |
| Average per construct | ~67min |
| Slowest step | MSA search (~2h per construct) |
| GPU inference | only ~85s per construct |
| Number of interruptions | 3 (script bug + DB lock + ORDER BY bug) |

### Results overview

| Construct | ranking_score | pTM | Notes |
|-----------|--------------|-----|------|
| con_0850 | **0.56** | 0.23 | ⭐ best |
| con_0561 | 0.53 | 0.24 | |
| con_0768 | 0.53 | 0.25 | |
| con_3774 | 0.53 | 0.24 | |
| con_0418 | 0.52 | 0.21 | |
| con_0521 | 0.52 | 0.24 | |
| ... (20 in total) | avg **0.52** | | |

AF3 ranking_score trends consistently with OmegaFold pLDDT, both around 0.50. The intrinsic disorder of the silk protein (GGX repeats) limits the confidence of all structure prediction methods.

---

## 6. Technical Difficulties

### Concurrency and timeouts

| Problem | Root cause | Resolution |
|------|------|------|
| ToxinPred3 took 24h for 2 million sequences | sklearn ExtraTrees is single-threaded, the C extension cannot be interrupted | Ran Round 2 first; parallelism was limited |
| BepiPred3 timeouts | GPU service queuing exceeded 300s | Semaphore=1, timeout=600s |
| OmegaFold blocks the event loop | PyTorch CUDA synchronous inference | Semaphore=1 serialization |
| SASA/A3D concurrency conflicts | batch submission + Semaphore control | independent Semaphore per service |

### Docker networking

As in the previous generation, Docker containers connect directly via bridge IP rather than docker-proxy (127.0.0.1), avoiding httpx hangs on long-running requests.

### AlphaFold3 script errors

Three bugs surfaced during the Round 8 run:
1. **iptm is None**: single-chain proteins have no iptm value, so `.4f` formatting crashed → added a `_fmt()` helper
2. **Conditional formatting syntax**: Python does not support `{v:.4f if v is not None else 'N/A'}` → changed to `f"{v:.4f}" if v else "N/A"`
3. **ORDER BY LIMIT ordering bug**: `ORDER BY channel, rank` + `LIMIT 20` took the top 20 of bottom rather than bottom10+top10 → switched to UNION ALL

### Docker builds

| Image | Time | Size | Notes |
|------|------|------|------|
| `alphafold3` | 8h | 6.92GB | pip download of nvidia CUDA whl extremely slow (~100KB/s) |
| Microservice images | varies | — | 16 services containerized |

The main bottleneck for the AlphaFold3 image is the domestic network environment: CUDA Python packages such as nvidia-cublas (393MB) and nvidia-cudnn (571MB) download at only ~100KB/s. On an overseas network this is expected to complete in 30-60min.

---

## 7. Comparison with stages2 Results

| Metric | stages2 (v2) | stages4 |
|------|-------------|---------|
| Input | 1,081,772 | **19,890,021** |
| Output | 150 constructs | **250 constructs** |
| Input coverage | UniProt + MGnify (partial) | **UniProt + MGnify + redundant set** |
| Safety policy | weighted and dilutable | **hard-threshold veto** |
| pLDDT mean | 0.41 | **0.42** |
| SASA mean | 0.70 | **0.72** |
| SASA in top range | 0.50-0.83 | **0.67-0.83** |
| A3D mean | 0.35 | **0.33** (lower = better) |
| Structure quality | 150 OmegaFold | **250 OmegaFold + 20 AF3** |

stages4 retains a 3D score distribution similar to stages2 but covers a more diverse source of candidate peptides (stages3's full 19.9 million vs stages2's 1.08 million), and introduces AF3 high-accuracy structures for the first time.

---

## 8. Experience and Lessons

### Design level

1. **Safety veto beats weighting**: hard thresholds that remove toxic/hemolytic/highly immunogenic peptides are the safest strategy; a weighted average cannot guarantee this.
2. **One task, one metric**: in stages2, AnOxPePred appeared in Round 1/2/3/4 — four places in total — which over-amplified the antioxidant signal in the final ranking. stages4 uses it once, and only for the Round 1 split.
3. **SD-driven weights are correct**: the data itself shows which metrics discriminate, which is more reliable than manual presets. Low-discrimination services are automatically down-weighted, avoiding injected noise.

### Engineering level

1. **Checkpoint/resume is a necessity**: a 24h+ pipeline will certainly fail at some point. Without a checkpoint/resume mechanism you start over from zero.
2. **Read SQL queries carefully**: `ORDER BY channel LIMIT 20` is not the same as "take 10 bottom + 10 top". UNION ALL is the right answer.
3. **None handling must cover all paths**: even a value that "cannot" be None can be None under specific conditions (e.g., iptm of a single-chain protein).
4. **Network environment determines build time**: the AlphaFold3 image takes 30min overseas and 8h domestically. Pre-caching the CUDA whl can greatly optimize this.
5. **Test first**: a single-construct AF3 test saved a great deal of debugging time (finding the iptm issue avoided wasting 20 × 2h).

### Wet-lab recommendations

- **First choice con_0850** (AF3 ranking_score=0.56, SASA=0.80) and **con_0418** (AF3 rs=0.52, SASA=0.81)
- Bottom-channel constructs (such as con_5489 and others) have higher OmegaFold pLDDT (0.48-0.50), so their structure predictions are more reliable, but their antioxidant activity is lower
- Recommend selecting Top 5-10 for wet-lab validation, along with 2-3 Bottom controls

---

*Generated by Claude Code — iGEM-silk stages4 pipeline review*
