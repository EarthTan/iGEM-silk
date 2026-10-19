> English translation of [identify_the_embedded_sequence.md](identify_the_embedded_sequence.md). The Chinese original is kept unchanged as the source of truth.

This is a **sequence position → PDB residue number** mapping problem. The logic is very clear and the code is not complicated.

------

## Core Logic

```
Full-length FASTA sequence
  → find the start/end positions of the functional peptide (string matching) → get start_idx, end_idx
  → in the PDB file output by AlphaFold/ESMFold, residue numbering is simply the 1-indexed sequence position
  → filter the PDB by residue number → get the 3D coordinates corresponding to the functional peptide
```

Because the residue numbering in the PDB output by ESMFold/AlphaFold (columns 5/6 of the `ATOM` records) directly corresponds to FASTA positions, no extra alignment is needed: once you find the sequence position, you have found the structural position.

------

## Complete Code

```python
import re
from Bio import PDB
from Bio.PDB import PDBIO, Select
import numpy as np

# ─── Input ──────────────────────────────────────────────
FULL_SEQUENCE  = "MAAAAAGGAGAGAGAGAGAGAGAGYWDHINNPEVYFGGAGAGAGAGAGAGAGAGAAAAM"
PEPTIDE_SEQ    = "YWDHINNPEVYF"     # functional peptide sequence
PDB_FILE       = "predicted.pdb"   # ESMFold/AlphaFold output
CHAIN_ID       = "A"

# ─── Step 1: Locate the functional peptide in the full-length sequence ──
match = re.search(PEPTIDE_SEQ, FULL_SEQUENCE)
if not match:
    raise ValueError(f"Functional peptide {PEPTIDE_SEQ} not found in the sequence")

# Convert to 1-indexed (PDB residue numbering starts at 1)
pep_start = match.start() + 1
pep_end   = match.end()       # inclusive
pep_residue_ids = list(range(pep_start, pep_end + 1))

print(f"Functional peptide is at sequence positions {pep_start}–{pep_end}, {len(pep_residue_ids)} residues in total")

# ─── Step 2: Parse the PDB and extract the functional peptide residues ──
parser   = PDB.PDBParser(QUIET=True)
structure = parser.get_structure("fusion", PDB_FILE)
model    = structure[0]
chain    = model[CHAIN_ID]

peptide_residues = []
for res in chain:
    if res.id[1] in pep_residue_ids:
        peptide_residues.append(res)

print(f"Found {len(peptide_residues)} matching residues in the PDB")

# ─── Step 3: Compute Cα coordinates (for later SASA / visualization) ──
ca_coords = []
for res in peptide_residues:
    if "CA" in res:
        ca_coords.append(res["CA"].get_vector().get_array())
        print(f"  Residue {res.resname} {res.id[1]}: CA = {res['CA'].get_vector()}")

ca_coords = np.array(ca_coords)

# ─── Step 4: Save the functional peptide region as a separate PDB (for tools such as A3D)
class PeptideSelect(Select):
    def accept_residue(self, res):
        return res.id[1] in pep_residue_ids

io = PDBIO()
io.set_structure(structure)
io.save("peptide_region.pdb", PeptideSelect())
print("Functional peptide region saved as peptide_region.pdb")
```

------

## After Getting the Coordinates, Compute SASA (Exposure)

This is the metric you actually want, and the `freesasa` library computes it directly:

```python
import freesasa

# Compute SASA for the full-length fusion protein
struct_fs = freesasa.Structure(PDB_FILE)
result    = freesasa.calc(struct_fs)

# Look only at the SASA of the functional peptide residues
total_peptide_sasa = 0
per_residue = []

for res_id in pep_residue_ids:
    sel_str = f"resi {res_id} and chain {CHAIN_ID}"
    sel = freesasa.selectArea([("pep", sel_str)], struct_fs, result)
    sasa_val = sel.get("pep", 0)
    total_peptide_sasa += sasa_val
    per_residue.append((res_id, round(sasa_val, 2)))

print(f"\nTotal functional peptide SASA: {total_peptide_sasa:.2f} Å²")
print("Per-residue SASA:")
for rid, sval in per_residue:
    bar = "█" * int(sval / 10)
    print(f"  Residue {rid:3d}: {sval:7.2f} Å²  {bar}")
```

------

## Example Output

```
Functional peptide is at sequence positions 24–35, 12 residues in total
Found 12 matching residues in the PDB
  Residue TYR 24: CA = <Vector 12.3, 5.1, 8.9>
  Residue TRP 25: CA = <Vector 14.1, 5.8, 7.2>
  ...

Total functional peptide SASA: 847.32 Å²
Per-residue SASA:
  Residue  24:   92.10 Å²  █████████
  Residue  25:   43.50 Å²  ████
  Residue  26:  110.20 Å²  ███████████
  ...
```

------

## One Edge Case to Watch Out For

If your functional peptide sequence **occurs multiple times** in the full-length FASTA (for example, you designed a multi-copy insertion), `re.search` only finds the first one. Switch to `re.finditer` to get all positions:

```python
all_matches = [(m.start()+1, m.end()) for m in re.finditer(PEPTIDE_SEQ, FULL_SEQUENCE)]
print(f"Functional peptide occurs {len(all_matches)} times at positions: {all_matches}")
```

This logic can be dropped straight into your P0 workflow — after ESMFold finishes, automatically extract the SASA of the functional peptide region and output a single number for construct comparison.
