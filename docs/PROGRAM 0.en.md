> English translation of [PROGRAM 0.md](PROGRAM 0.md). The Chinese original is kept unchanged as the source of truth.

# PROGRAM.md — Silk Fibroin Fusion Functional Peptide Design Platform (exploratory plan)

> **Version**: v0.2-exploratory  
> **Status**: direction-exploration stage; multiple paths are retained; not a final draft  
> **Background**: This document builds on the technical accumulation of the original OxidShield plan (AI-driven modular functional peptide design) and combines it with the current wet-lab pivot (silk fibroin scaffold + short functional peptides) to lay out the supporting directions and open questions for the Dry Lab.

---

## I. Project background and direction adjustment

### 1.1 Review of the original plan

The core logic of the original OxidShield plan was: use machine learning to predict the scores of short peptides across six efficacy dimensions (antioxidant, anti-glycation, collagen-promoting, antibacterial, anti-inflammatory, anti-melanin, transdermal delivery), then use a "fusion engine" to traverse the combinatorial space of `short peptide A + linker + short peptide B` and screen for the best chimera.

The core challenge of that approach was that simple connections between short peptides lack a stable three-dimensional scaffold, which affects activity exposure and in vivo stability.

### 1.2 The core shift of the new direction

The current wet-lab pivot provides a framework with more engineering significance:

> **Use a silk fibroin functional fragment as the structural scaffold, insert/fuse functional short peptides into it, exploit the self-assembly capability and biocompatibility of silk fibroin, and at the same time use the functional peptide to achieve a specific skincare efficacy (antioxidant / anti-melanin deposition).**

The significance of this shift is:
- Silk fibroin naturally has good **skin compatibility** and **the ability to self-assemble into films via β-sheets**, making it suitable for topical skincare scenarios
- A large body of literature confirms that silk fibroin functional fragments can be recombinantly expressed in E. coli (see Heidebrecht & Scheibel, 2013), providing an operable starting point for the wet lab
- The Dry Lab's task becomes: **help the wet lab make better-grounded primary-screening decisions on insertion site, insertion mode, and functional peptide choice**

---

## II. Core scientific questions

The project currently faces two interrelated core design questions, each discussed below.

---

### Question 1: How can a functional peptide be fused onto the silk backbone without disrupting β-sheets, while ensuring effective exposure of the functional peptide?

#### 2.1 Key constraints of silk fibroin structure

According to the known structure of spider dragline silk (MA silk) (Heidebrecht & Scheibel, 2013):

| Domain | Characteristics | Function |
|--------|------|------|
| Alanine-rich poly-alanine region (poly-Ala) | Forms crystalline β-sheets | Provides high tensile strength |
| GGX / GPGXX repeat sequences | Form an amorphous elastic matrix | Provide extensibility and flexibility |
| N-terminal domain (NTD) | α-helix pentamer, pH-sensitive | Controls protein storage and initiation of assembly |
| C-terminal domain (CTD) | α-helix, dimerization | Controls β-sheet orientation and assembly |

**The core contradiction of insertion sites**: if the peptide is inserted into the crystalline β-sheet region (polyAla), it is highly likely to interrupt β-sheet packing and cause the mechanical structure to collapse; if it is inserted into the amorphous region (GGX linker), the structural perturbation is smaller, but whether the functional peptide can be sufficiently exposed on the protein surface remains uncertain.

#### 2.2 Possible insertion site strategies (retaining multiple explorations)

**Strategy A: insertion into the GGX amorphous region**

Insert the functional peptide into the flexible GGX spacer between adjacent β-sheet crystalline regions. This strategy perturbs β-sheets the least, but the spatial exposure of the functional peptide must be evaluated.

```
[poly-Ala]...[GGX]...[functional peptide]...[GGX]...[poly-Ala]
```

Advantages: does not disrupt the crystalline region; drawback: the functional peptide may be buried in the amorphous matrix.

**Strategy B: terminal domain insertion (NTD/CTD engineering)**

Splice the functional peptide onto the outside of the NTD or CTD, exploiting the fact that the terminal domains themselves are exposed at the solution interface, thereby ensuring exposure of the functional peptide. This strategy has structural engineering precedents in the existing literature (for example, RGD-functionalized spider silk proteins, Wohlrab et al., 2012).

```
[functional peptide]---[NTD]---[repeat core]---[CTD]---[functional peptide]
```

Advantages: the termini are naturally exposed; drawback: the dimerization behavior of the NTD/CTD may be affected, which in turn affects protein assembly.

**Strategy C: fusion via independent linkers (short silk fragments as the scaffold)**

Instead of using the full silk fibroin protein, use only a few repeat modules (for example, 4–8 repeat units) as the backbone, with the functional peptide connected at either end of the sequence or internally through a flexible linker (such as GGGGS × n).

Advantages: molecular weight is controllable and expression difficulty is reduced; drawback: the self-assembly capability of short fragments may be insufficient.

#### 2.3 How to evaluate the exposure of the functional peptide

**Computational means (AI-assisted):**

- **AlphaFold2 / ESMFold structure prediction**: predict the structure of the proposed fusion protein and observe whether the functional peptide region lies in an exposed loop or surface region, or is buried inside the protein.
- **SASA (solvent-accessible surface area) calculation**: use PyMOL or FreeSASA to compute the SASA values of the functional peptide residues on the predicted structure and evaluate the degree of exposure.
- **Molecular dynamics simulation (optional)**: if conditions permit, use GROMACS to run a short MD simulation of the fusion protein and evaluate the dynamic stability of the functional peptide conformation.

> ⚠️ **Open question**: AlphaFold's prediction confidence for highly repetitive sequences (such as the silk fibroin repeat core) is questionable; prediction tools designed specifically for fibrous proteins, or truncated sequences, may be needed as substitutes for evaluation.

**Experimental validation ideas (Dry Lab provides predictions, wet lab validates):**

- Fluorescently label the end of the functional peptide and observe whether the fluorescence is detectable after the recombinant protein forms a film
- Protease accessibility assay: after the film-forming protein is treated with a protease, check whether the functional peptide is degraded (exposed means degraded, buried means protected)

---

### Question 2: Is function retained after inclusion body → refolding? How should peptides whose function can be retained be selected?

#### 2.3 Real-world constraints of E. coli expression

A large body of literature (Heidebrecht & Scheibel, 2013; Xia et al., 2010) confirms that silk fibroin very readily forms inclusion bodies (IBs) when expressed in E. coli, for reasons including:
- The sequence is highly repetitive, leading to depletion of the tRNA pool
- The protein is strongly hydrophobic and readily aggregates

The standard workflow is: lyse cells → wash IBs → dissolve (usually with 6M guanidine hydrochloride or 8M urea) → dialysis/dilution refolding → functional assessment.

**Key risks during refolding:**

- The silk fibroin β-sheet structure refolds during renaturation and may **bury the inserted functional peptide inside the β-sheet stack**
- If the functional peptide itself contains strongly hydrophobic residues, it may undergo **incorrect aggregation** during refolding and lose activity

#### 2.4 Functional peptide selection strategy (Which)

When selecting the functional peptide to insert, the following dimensions must be considered together:

| Dimension | Consideration |
|------|--------|
| Functional potency | Antioxidant activity (DPPH/ABTS IC50); tyrosinase inhibitory activity (anti-melanin) |
| Structural compatibility | Whether it contains proline-rich regions that disrupt β-sheets (Pro itself blocks β-sheets, which may be favorable, keeping the insertion site flexible)|
| Hydrophilicity | The functional peptide should be relatively hydrophilic so that it remains solvent-exposed after refolding |
| Length | 5–15 amino acids is recommended; excessively long peptides may interfere with backbone folding |
| Validated literature | Prefer functional peptide sequences that already have activity data, reducing unknown risk |

**Candidate functional peptide directions (pending further literature review):**

- **Antioxidant**: short peptides rich in His, Tyr, and Trp residues (such as YWDHINNPEVYF-like sequences); active fragments derived from collagen or soy hydrolysate
- **Anti-melanin**: sequences containing copper-chelating groups (His-His dipeptide) or competitive tyrosinase inhibition

#### 2.5 Evaluation of function retention after refolding and AI assistance (How)

**Support the Dry Lab can provide:**

1. **Hydrophilicity/hydrophobicity prediction for the functional peptide**: use Biopython to compute the Grand Average of Hydropathicity (GRAVY) value of the functional peptide; prefer hydrophilic peptides with GRAVY < 0

2. **Secondary structure prediction for the functional peptide within the fusion protein**: use PSIPRED or ESMFold to predict the secondary structure of the functional peptide region after fusion — if the functional peptide is predicted to be part of a β-sheet in the fusion protein, that design must be reconsidered

3. **Machine-learning-assisted screening (reusing the original OxidShield framework)**:
   - Train binary classification prediction models for the target functions (antioxidant, anti-melanin)
   - Feature engineering: amino acid composition + physicochemical properties (MW, PI, GRAVY, instability index) + ESM-2 embeddings
   - Score candidate functional peptide sequences and preferentially recommend sequences with high predicted activity and structural compatibility
   - This module directly reuses the data collection and model training workflow of the original OxidShield

4. **Heuristic rules for refolding friendliness (hard-coded pre-screening)**:
   - Exclude functional peptides with extreme net charge (< -3 or > +3) (this affects the overall PI of the protein and interferes with IB solubilization conditions)
   - Exclude peptides containing multiple adjacent Cys residues (unintended disulfide bond formation)
   - Prefer peptides containing a small number of Pro residues (creating a local β-sheet interruption at the insertion site, which helps expose the functional peptide)

---

## III. Dry Lab engineering architecture (after adjustment)

### 3.1 Overall workflow

```
[Data layer]
  ├── Functional peptide activity database (antioxidant / tyrosinase inhibition)
  └── Silk fibroin structure literature & validated expression sequences

[Prediction model layer]
  ├── Functional activity prediction (ML: XGBoost / MLP, continuing the original framework)
  └── Structural compatibility prediction (ESMFold + SASA calculation)

[Design decision layer]
  ├── Insertion site scorer (Which region: NTD / GGX loop / CTD)
  ├── Functional peptide candidate ranking (combining activity prediction + structural compatibility + refolding friendliness)
  └── Construct plan output (fusion protein sequence + insertion site annotation)

[Evaluation feedback layer]
  └── Wet-lab data flows back → model update (later stage)
```

### 3.2 Module priorities (current stage)

| Priority | Module | Explanation |
|--------|------|------|
| P0 | Functional peptide candidate screening | Use the existing OxidShield framework to output candidate sequences |
| P0 | Structural compatibility assessment | Preliminary AlphaFold/ESMFold predictions for 1–3 construct designs |
| P1 | Insertion site analysis | Analyze the effect of different insertion positions on the SASA of the functional peptide |
| P2 | Refolding condition prediction | Analyze the PI and hydrophobic region distribution of the fusion protein and recommend refolding buffer conditions |
| P3 | Full-stack platform development | Later stage; integrate the above functions into an interactive web tool |

---

## IV. Open questions and uncertainties (require ongoing discussion)

The following questions currently have no clear answers and must be progressively resolved through literature review, computational exploration, and wet-lab feedback:

1. **Choice of silk fibroin backbone**: use spider MA silk fragments (MaSp1/MaSp2) or silkworm silk fibroin (B. mori fibroin)? The two differ in validated expression systems and skin application data, and require further evaluation.

2. **Number of repeat modules**: how many (GAGAGAGX)n or (GGX)n repeat units should be used? The repeat number determines molecular weight and film-forming ability, but also affects expression difficulty (proteins with MW > 100 kDa are extremely difficult to fold correctly in E. coli).

3. **Number of functional peptide insertions (How many)**: should one or multiple functional peptides be inserted per protein chain? Multiple insertions may enhance efficacy but also increase the risk of structural perturbation. There is currently not enough computational or experimental evidence to make a judgment.

4. **Linker design**: how should the length and flexibility of the linker connecting the functional peptide to the silk fibroin backbone be chosen? The effect of rigid linkers (such as EAAAK) vs flexible linkers (such as GGGGS × 3) on functional peptide exposure.

5. **In vitro functional testing standards**: are the experimental conditions for the antioxidant activity assay (DPPH / ABTS) and the tyrosinase inhibition assay of the refolded protein comparable with literature data?

---

## V. Technical inheritance relationship with the original OxidShield framework

| Original framework module | Corresponding item in the current plan |
|-----------|-----------------|
| Antioxidant functional peptide ML prediction model | Reused directly, for primary screening of functional peptide candidates |
| ESM-2 embedding feature engineering | Reused, for functional peptide representation |
| Optuna hyperparameter optimization | Reused |
| Fusion engine (enumeration + scoring) | **Adjusted**: no longer enumerate `peptide A + linker + peptide B`, but instead enumerate combinations of `insertion site × functional peptide × linker type` |
| Full-stack platform (React + FastAPI) | **Deferred**; at the current stage computational analysis takes priority, and platform development proceeds after the validation stage |

---

## VI. Near-term action items (pending discussion and confirmation)

- [ ] Determine the silk fibroin backbone sequence (MaSp1 / MaSp2 / B. mori fibroin, how many repeat units)
- [ ] Search the literature on antioxidant & tyrosinase-inhibitory functional peptides and build a candidate sequence pool
- [ ] Run AlphaFold/ESMFold structure prediction on 2–3 representative design plans and evaluate functional peptide exposure
- [ ] Confirm the wet-lab refolding protocol so that the Dry Lab can use the corresponding conditions when computing PI / hydrophobic profiles
- [ ] Define the final form of the Dry Lab output: sequence file + insertion site annotation + structure prediction report

---

*This document is an exploratory draft; all design directions await further validation and convergence from experimental and computational results.*




# CONTEXT.md  (formal decision on the general direction)

Okay, so this is our plan now.

The single-function modules stay unchanged — mainly the microservices in tools.

As for the fusion engine, I have decided to use the super-enumeration method as the core logic.

Our target pigment protein is already confirmed to exist. After finding the functional peptide we want to insert, our core logic is as follows:

1. Insert at each position one by one (enumeration method)
   (a) Suppose the pigment protein has length 1000; then there are 1001 positions at which the functional peptide could be inserted.
   (b) We enumerate all 1001 schemes and observe the state of the fusion in each case.

2. Combined insertion of multiple functional peptides
   (a) Besides single-point insertion, we can also try inserting two functional peptides together.
   (b) Or insert the same functional peptide twice in a row.
   (c) This yields several thousand or even tens of thousands of combination schemes.

3. Subsequent screening optimization
   On top of enumeration, we can also add screening conditions, for example:
   (a) Avoid restriction enzyme cut sites
   (b) Avoid Beta sheets (β-sheets)

Overall, our core logic is to evaluate the specific behavior of the fusion state by enumerating all possible insertion positions and combination modes.

So how do I judge whether this fusion state is acceptable?

I also learned about a tool called SAS; the reference mentions that it can be used to check the degree of exposure.
