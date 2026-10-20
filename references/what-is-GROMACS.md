> **English** | [中文](what-is-GROMACS.zh.md)

# GRAMACS 

The official git repo URL: https://github.com/gromacs/gromacs

## First, What GROMACS MD Does, Explained Through Inputs and Outputs

**One-sentence definition**: GROMACS is a tool that "puts a static 3D molecular structure into water, soaks it for a while, and records a video."

---

### Input

```
1. A PDB file (the 3D coordinates of your fusion protein: the x,y,z position of every atom)
   ↑ usually from AlphaFold / ESMFold prediction, or a crystal structure

2. Force field parameters (tell the program the stiffness of each chemical bond and the electrostatic/van der Waals interaction between each pair of atoms)
   Common choices: CHARMM36m, AMBER ff19SB

3. Simulation parameters (temperature 300K, pressure 1 bar, how long to simulate, e.g. 100 nanoseconds)
```

### Output

```
1. Trajectory file (.xtc)
   → every N picoseconds, the coordinates of all atoms are recorded
   → a 100 ns simulation has roughly 10,000 "snapshot" frames, which together form a video of molecular motion

2. Statistics analyzed from the trajectory:
   - RMSD: is the overall structure stable (how far has it deviated from the initial structure?)
   - RMSF: which residues are wiggling? which are rigid?
   - SASA over time: how much surface area of the functional peptide is on average exposed to water?
   - Secondary structure fractions over time: after the functional peptide is inserted, has the β-sheet been disrupted?
```

**Key insight**: AlphaFold/ESMFold give you a **photograph** (a static structure). GROMACS gives you a **video** (how the molecule behaves dynamically in a real solution environment).

---

## For Your Project, Is GROMACS MD Useful?

**The conclusion up front: you don't need it in the main workflow, but you can use it once or twice in the final validation stage.**

The reason is determined by the scale of your design:

Your core logic is **massive enumeration** — for a 1000 aa silk fibroin, single-point insertion alone gives 1001 options, and combining two functional peptides puts you in the millions. GROMACS takes **at least hours to days** to simulate one fusion protein (depending on sequence length and simulation length). That is completely infeasible during your screening stage.

What you actually need is the following pipeline:

```
1001 insertion sites
      ↓
  Batch structure prediction with ESMFold (~1–10 seconds per sequence)
      ↓
  Static SASA calculation (FreeSASA or PyMOL, seconds)
      ↓
  Secondary structure check (is the functional peptide region predicted as β-sheet?)
      ↓
  Sequence-level hard filtering (avoid protease cleavage sites, Pro content, charge, etc.)
      ↓
  Output the Top 5–10 candidate designs
      ↓
  [Optional] Run GROMACS on these few designs to verify that SASA is really stable in solution
```

---

## The SASA You Mentioned: You Don't Need MD to Compute It

This is an important distinction. SASA has two uses:

| Use | Tool | Computed on | Meaning |
|---|---|---|---|
| **Static SASA** | FreeSASA, PyMOL `get_sasa` | A single PDB structure | How much area of the functional peptide is exposed in this structure |
| **Dynamic average SASA** | GROMACS trajectory analysis | Mean over 10,000 snapshot frames | Average exposed area of the functional peptide in solution |

For your enumeration and screening stage, **static SASA is entirely sufficient**, and it can be batch-automated.

**In practice**: predict structures with ESMFold → save PDBs → batch-compute with the FreeSASA command line → compare the functional peptide residue SASA values across insertion sites and take the design with the highest value.

```bash
# Install
pip install freesasa

# Batch computation in Python
import freesasa
structure = freesasa.Structure("fusion_pos42.pdb")
result = freesasa.calc(structure)
# Sum over the functional peptide residues to get the exposed area
```

---

## The Reasonable Role of GROMACS in Your Project

It belongs in the project's **final validation stage**, not the screening stage:

- After enumeration + static SASA + ML scoring, you settle on 2–3 optimal constructs (insertion site × functional peptide × linker type)
- Run GROMACS on these 2–3 constructs with a 50–100 ns simulation to verify the dynamic exposure behavior of the functional peptide in solution
- These results can serve as the computational evidence for the wiki, and they also support your recommendation to the wet-lab team of "which design is most worth synthesizing and validating first"

For iGEM, this part has an extra benefit: **MD trajectory visualization (VMD animations) is itself great presentation material** — judges understand it, and it has strong visual impact.

In one sentence: for you, GROMACS is not a pipeline tool; it is a **stress-testing tool for the final candidates**. The enumeration screening in the main workflow relies on ESMFold + static SASA + sequence-level rules — all three can be batch-automated, which is the only way to handle your thousands-to-tens-of-thousands of candidate designs.
