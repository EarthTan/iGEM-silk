---
name: Impact of the Structure Prediction Confidence Cascade on Downstream PDB Evaluation v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [pipeline, confidence, esmfold, plddt, sasa, structure-prediction]
validated: true
---

> English translation of [gep-pipeline-confidence-cascade.md](gep-pipeline-confidence-cascade.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Impact of the Structure Prediction Confidence Cascade on Downstream PDB Evaluation

## Experience

**Problem type**: ESMFold's pLDDT confidence for long proteins rich in repetitive sequences (silk fibroin fusion constructs) is generally below 0.31, which directly makes downstream SASA/Aggrescan3D evaluation results unreliable — not because the tools compute incorrectly, but because the input structures are unreliable.

**Core strategy**:
1. **Confidence cascade effect**: The confidence of 3D prediction propagates downstream level by level — if ESMFold pLDDT is low, every analysis based on the PDB (SASA exposure, aggregation propensity, molecular dynamics) is built on an unstable structure, and the conclusions can only serve as reference rather than quantitative evidence
2. **pLDDT threshold check mechanism**: Evaluate confidence as early as Stage 5 (ESMFold) output; if everything is < 0.5, a warning should be issued noting that downstream evaluation reliability is limited. Introduce a "pLDDT confidence band" in Stage 6 — SASA scores come with a pLDDT range for reference
3. **Identify the root cause rather than a tool problem**: ESMFold is inherently unreliable for (a) lengths > 400 aa, (b) highly repetitive sequences (GAGAGS)n, and (c) intrinsically disordered regions — this is a property of the protein itself, not a problem with ESMFold
4. **Domain-splitting strategy**: Split long fusion proteins into independent domains (functional peptide + partial linker, <100 aa) and predict each separately, avoiding interference from long and repetitive sequences

**Key parameters**:

| Protein feature | ESMFold performance | Confidence threshold |
|----------|-------------|-----------|
| Globular protein < 400 aa | Good | pLDDT ≥ 0.7 trustworthy |
| Multi-domain protein | Moderate | pLDDT 0.5-0.7 for reference |
| Repetitive / intrinsically disordered | Poor | pLDDT < 0.5 unreliable |
| **Silk fusion (>380 aa, repetitive)** | **Poor** | **pLDDT ≤ 0.31** |

**Typical indicators**:
- ESMFold pLDDT < 0.5 → increased risk of false positives with overly high SASA exposure (unfolded regions are forced to be exposed in the calculation)
- ESMFold pLDDT < 0.5 → Aggrescan3D aggregation risk may be underestimated (loose structure leaves buried hotspots insufficiently exposed)

## Environment Fingerprint

- **Task domain**: Computational biology pipeline, structure prediction and downstream evaluation of fusion proteins / repetitive-sequence proteins
- **Input characteristics**: Silk-fibroin-grade fusion constructs containing highly repetitive (GAGAGS)n sequences, 380-440 aa in length
- **Constraints**: ESMFold used by default (fast, ~2min/construct); AlphaFold3 is more accurate but slower and requires an external API
- **Not applicable**:
  - Globular proteins/enzymes (ESMFold is highly accurate for them)
  - Independent prediction of short peptides (<100 aa, for which ESMFold pLDDT is higher)
  - Cases that only need relative ranking from SASA/A3D scores rather than absolute quantitation

## Audit Record

- **Validation method**: Full run of iGEM-silk Stage 5 (90 constructs, ESMFold) + Stage 6 (SASA + A3D)
- **Test cases**:
  1. ESMFold prediction of 90 constructs → pLDDT mean=0.281, max=0.307, all < 0.5
  2. SASA computed on low-confidence structures → 95.6% judged as "exposed" (insufficient discrimination)
  3. Aggrescan3D computed on low-confidence structures → all low-moderate (cannot confirm true or false)
  4. Rerun after fixing the ESMFold bug → pLDDT mean 0.2806 → 0.2810 (marginal improvement; the root cause is still the sequence properties)
- **Success rate**: Not applicable (this is not a "fix" but a revelation of the inherent limitations of the computational method)
- **Limitations**: Domain-splitting prediction requires redesigning the construct construction logic, and the choice of split points in linker regions affects the results

## Usage

- **Trigger conditions**: All pLDDT values in ESMFold prediction results are < 0.5; or downstream SASA/Aggrescan3D scores lack discrimination
- **How to invoke**:
  1. Add pLDDT quality gating in the Stage 5 script: `if mean_plddt < 0.5: logger.warning("low structure confidence; downstream evaluation is for reference only")`
  2. Annotate the pLDDT confidence range of SASA/A3D in the Stage 6 output
  3. If the protein sequence is repetitive, consider splitting it into domains and predicting them independently
- **Caveats**: Do not reject ESMFold just because pLDDT is low — this is a matter of using the right tool for the job, not of tool quality. The conformational flexibility of silk fibroin is its natural property, and experimentally its secondary structure also needs to be determined via CD/WAXS and similar characterization
