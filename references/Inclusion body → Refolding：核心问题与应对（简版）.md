> **English** | [中文](Inclusion%20body%20%E2%86%92%20Refolding%EF%BC%9A%E6%A0%B8%E5%BF%83%E9%97%AE%E9%A2%98%E4%B8%8E%E5%BA%94%E5%AF%B9%EF%BC%88%E7%AE%80%E7%89%88%EF%BC%89.zh.md)

## Inclusion Body → Refolding: Core Problems and Countermeasures (Brief Version)

### 1. Why Must Silk Fibroin Fusion Systems Deal with Refolding?

- Silk fibroin expressed in **E. coli** inevitably forms **inclusion bodies** (repetitive sequence, tRNA depletion, high hydrophobicity).
- Standard workflow: **wash → dissolve in high-concentration denaturant (urea/guanidine hydrochloride) → remove the denaturant and refold**.
- The refolding process determines whether the functional peptide can be **correctly exposed** and retain its activity.

### 2. Core Risks (Three)

1. **Low overall recovery**: silk fibroin has strong β-sheet propensity and readily aggregates irreversibly during refolding; recovery is often around 20%.
2. **The functional peptide gets buried by β-sheet**: during refolding, the natural β-sheet stacking forces may "pull" the functional peptide into the hydrophobic core, causing a complete loss of activity.
3. **The functional peptide itself aggregates incorrectly**: if the functional peptide is strongly hydrophobic, rich in Cys, or carries extreme charge, it can induce intermolecular cross-linking or disulfide bond mispairing.

### 3. Key Strategies for Preserving Activity

**Strategy A: Pre-screen compatible functional peptides** (the main entry point for Dry Lab)
- Choose **hydrophilic peptides** (GRAVY < 0)
- Length 5–15 aa, moderate net charge, avoid many Cys
- **Prefer peptides containing Pro residues** (naturally breaks β-sheet, helping the functional peptide stay exposed)
- Predict the fusion protein structure with ESMFold and compute the **solvent-accessible surface area (SASA)** of the functional peptide to avoid it being buried inside

**Strategy B: Optimize refolding conditions**
- Low temperature (4°C), low concentration (0.1–1 mg/mL)
- **L-arginine** (0.4–0.5 M) to suppress aggregation
- Remove the denaturant in stages (stepwise dilution/dialysis)
- Keep the pH away from the isoelectric point; alkaline (8.0–9.0) is preferred

**Strategy C (long term)**: bypass refolding — switch to a **NusA fusion tag** or **Pichia pastoris secretory expression** to achieve soluble/secreted expression and eliminate the uncertainty of inclusion body refolding at the root.

### 4. Refolding-Friendliness Assessment That Dry Lab Can Provide

- Compute GRAVY, pI, charge, and Cys count
- Predict the fusion protein secondary structure (the functional peptide should not be predicted as β-sheet)
- Compute SASA (to directly judge whether the functional peptide can be exposed on the surface)
- Output candidate peptide scores + recommended refolding pH/additives

---

**One-sentence summary**: refolding is the biggest bottleneck for silk fibroin–functional peptide fusions — by choosing hydrophilic, Pro-containing, structurally exposed functional peptides and combining L-arginine with slow, low-temperature refolding, the probability that the functional peptide retains its activity can be greatly increased.
