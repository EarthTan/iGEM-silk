---
name: sodope
description: Protein solubility prediction (Solubility-Weighted Index). Quickly assess whether a protein will be soluble when expressed in E. coli based on its amino acid sequence; suitable for iGEM team members screening high-solubility protein/peptide candidates.
created: 2026-05-11
version: 1.0
---

> **English** | [中文](SKILL.zh.md)

# SoDoPE — Solubility-Weighted Index

## What It Is

SoDoPE is a fast protein solubility prediction tool based on the SWI (Solubility-Weighted Index). It uses an empirical solubility weight table for the 20 standard amino acids and, through a simple weighted average + logistic regression, predicts protein solubility upon expression directly from the sequence.

Prediction results include:
- **SWI** (Solubility-Weighted Index): raw weighted score in the 0-1 range
- **Probability of Solubility**: solubility probability mapped through logistic regression (0-1)
- **Soluble / Insoluble**: binary classification label (threshold 0.5)

## When to Use (iGEM scenarios)

- You have several candidate proteins/peptides and are unsure which one can be expressed efficiently, so you need to pick out the most soluble one
- You have made mutations to a protein and want to quickly check whether the mutations might affect solubility
- When screening large numbers of sequences at high throughput (SWI is extremely fast), first filter out the insoluble sequences
- As a preliminary filtering step before experiments, when you need a fast scoring tool that requires no external dependencies

## Methodology

```
FASTA sequence → per-residue table lookup (20 aa weights) → take the mean = SWI → sigmoid(A·SWI + B) = solubility probability
```

- Each of the 20 standard amino acids has an empirical weight value (obtained by optimization on the log scale of the eSOL dataset)
- Larger value → the amino acid is more likely to occur in soluble proteins
- The arithmetic mean of all residue weights is the SWI
- Mapped to solubility probability through logistic regression constants A=81.0581, B=-62.7775
- The whole process involves no model loading and no GPU requirement; it is pure in-memory computation

## Inputs and Outputs

- **Input**: amino acid sequence (single-letter, upper or lower case, only the 20 standard amino acids ACDEFGHIKLMNPQRSTVWY supported)
- **Output**:
  | Field | Meaning |
  |------|------|
  | `score` | Solubility probability (0-1); ≥0.5 means predicted soluble |
  | `label` | `Soluble` or `Insoluble` |
  | `swi` | Raw SWI score |
  | `probability` | Solubility probability value, the same as score |
  | `sequence_length` | Sequence length |

## Requirements

### Software

- Python 3.11+
- numpy

### Hardware

- Any CPU. SWI needs no GPU, no graphics card, and no model file download.
- Speed: single-sequence prediction < 1ms

## Examples

**Example 1 — Pick the most soluble among candidate proteins**

You found 3 cellulase sequences from different species on NCBI and are unsure which one to use for E. coli expression. Send them all to `/predict/batch` and compare `score` and `swi`. Choose the one with the highest solubility probability for synthesis and expression.

**Example 2 — Verify whether a mutation improved solubility**

You made surface amino acid substitutions on a low-solubility protein (for example, introducing more Glu/Asp/Lys) and want to verify whether the engineering worked. Predict the wild-type and mutant sequences separately and compare the `swi` scores. If the mutant's SWI is clearly higher, the engineering direction is correct.

**Example 3 — High-throughput preliminary screening**

You have a library of 500 short peptides and need to filter out potentially insoluble sequences before synthesis. Use `/predict/batch` for batch prediction and filter out sequences with `label == "Insoluble"`, greatly reducing synthesis and testing costs.

## References

| File | Contents |
|------|------|
| `sodope_integration.py` | SWI algorithm implementation, including all weights and logistic regression constants |
| `service.py` | Microservice entry point, based on the FastaToolService template |
| `../../tools/template/fasta_service.py` | Microservice base class, defining the unified API interface |

## Citation

```
@article{10.1093/bioinformatics/btaa578,
    author = {Bhandari, Bikash K and Gardner, Paul P and Lim, Chun Shen},
    title = "{Solubility-Weighted Index: fast and accurate prediction of protein solubility}",
    journal = {Bioinformatics},
    volume = {36},
    number = {22-23},
    pages = {5531-5539},
    year = {2020},
    doi = {10.1093/bioinformatics/btaa578},
}
```
