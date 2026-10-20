> **English** | [中文](how-to-use-saas.zh.md)

## Overall Design

```
Input: FASTA sequence + functional peptide sequence
  → ESMFold API (or local) → PDB file
  → FreeSASA → per-residue SASA values
  → Output: JSON report
```

Tech stack: **FastAPI + FreeSASA + Biopython**, packaged with Docker, single-container microservice.

------

## Directory Structure

```
sasa-service/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py          # FastAPI entry point
│   ├── esm_fold.py      # Structure prediction module
│   ├── sasa_calc.py     # SASA calculation core
│   └── models.py        # Pydantic data models
```

------

## Code Implementation

### `models.py`

```python
from pydantic import BaseModel
from typing import List, Optional

class SASARequest(BaseModel):
    full_sequence: str          # Full-length fusion protein FASTA sequence
    peptide_sequence: str       # Functional peptide sequence
    chain_id: str = "A"
    pdb_content: Optional[str] = None  # Optional: pass PDB text directly to skip structure prediction

class ResidueSASA(BaseModel):
    residue_id: int
    residue_name: str
    sasa: float                 # Å²
    relative_sasa: float        # 0~1, ratio relative to the standard exposure value
    is_exposed: bool            # relative SASA > 0.25 is considered exposed

class SASAResponse(BaseModel):
    peptide_sequence: str
    peptide_start: int
    peptide_end: int
    total_sasa: float           # Total SASA of the functional peptide region, Å²
    mean_relative_sasa: float   # Mean relative exposure
    exposure_ratio: float       # Fraction of exposed residues
    residues: List[ResidueSASA]
    pdb_content: str            # The PDB that was used (for frontend visualization)
    warning: Optional[str] = None
```

------

### `esm_fold.py`

```python
import httpx
import tempfile, os

ESMFOLD_API = "https://api.esmatlas.com/foldSequence/v1/pdb/"

async def predict_structure(sequence: str) -> str:
    """
    Call the public ESMFold API and return the PDB text string.
    For local deployment, just replace the URL with localhost:8080.
    """
    if len(sequence) > 400:
        raise ValueError("Sequence too long (>400 aa); this is a limit of the public ESMFold API — truncate the sequence or deploy locally")
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            ESMFOLD_API,
            content=sequence,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.text  # PDB format string
```

> For a local ESMFold deployment, just switch to the docker service at `http://localhost:8080`; the interface format is the same.

------

### `sasa_calc.py`

```python
import re
import tempfile
import numpy as np
import freesasa
from Bio import PDB
from Bio.PDB import PDBIO, Select
from io import StringIO

# Standard maximum SASA reference values (Å²), used to compute relative exposure
MAX_SASA = {
    "ALA": 121, "ARG": 265, "ASN": 187, "ASP": 187, "CYS": 148,
    "GLN": 214, "GLU": 214, "GLY": 97,  "HIS": 216, "ILE": 195,
    "LEU": 191, "LYS": 230, "MET": 203, "PHE": 228, "PRO": 154,
    "SER": 143, "THR": 163, "TRP": 264, "TYR": 255, "VAL": 165,
}

class _PeptideSelect(Select):
    def __init__(self, residue_ids):
        self.ids = set(residue_ids)
    def accept_residue(self, res):
        return res.id[1] in self.ids

def locate_peptide(full_seq: str, peptide_seq: str):
    """Return all match positions (1-indexed); supports multiple copies"""
    return [(m.start() + 1, m.end()) for m in re.finditer(peptide_seq, full_seq)]

def calc_sasa(pdb_text: str, full_sequence: str, peptide_sequence: str, chain_id: str):
    # ── 1. Locate the functional peptide ───────────────────
    positions = locate_peptide(full_sequence, peptide_sequence)
    if not positions:
        raise ValueError(f"Functional peptide '{peptide_sequence}' not found in the sequence")
    
    # Take the first position (extend to a loop when there are multiple copies)
    pep_start, pep_end = positions[0]
    pep_residue_ids = list(range(pep_start, pep_end + 1))
    warning = f"Functional peptide occurs {len(positions)} times; analyzing the first one" if len(positions) > 1 else None

    # ── 2. Parse the PDB ──────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".pdb", mode="w", delete=False) as f:
        f.write(pdb_text)
        tmp_path = f.name

    try:
        parser = PDB.PDBParser(QUIET=True)
        structure = parser.get_structure("fusion", tmp_path)
        chain = structure[0][chain_id]

        # ── 3. Compute whole-protein SASA with FreeSASA ─────
        fs_struct = freesasa.Structure(tmp_path)
        fs_result = freesasa.calc(fs_struct)

        # ── 4. Extract functional peptide SASA per residue ──
        residues_out = []
        total_sasa = 0.0

        for res in chain:
            rid = res.id[1]
            if rid not in pep_residue_ids:
                continue

            sel = freesasa.selectArea(
                [("r", f"resi {rid} and chain {chain_id}")],
                fs_struct, fs_result
            )
            sasa_val = sel.get("r", 0.0)
            total_sasa += sasa_val

            resname = res.resname.upper()
            max_ref = MAX_SASA.get(resname, 200)
            rel_sasa = min(sasa_val / max_ref, 1.0)

            residues_out.append({
                "residue_id": rid,
                "residue_name": resname,
                "sasa": round(sasa_val, 3),
                "relative_sasa": round(rel_sasa, 3),
                "is_exposed": rel_sasa > 0.25,
            })

    finally:
        import os; os.unlink(tmp_path)

    # ── 5. Aggregate statistics ───────────────────────────
    rel_sasas = [r["relative_sasa"] for r in residues_out]
    mean_rel  = float(np.mean(rel_sasas)) if rel_sasas else 0.0
    exp_ratio = sum(r["is_exposed"] for r in residues_out) / len(residues_out) if residues_out else 0.0

    return {
        "peptide_sequence": peptide_sequence,
        "peptide_start": pep_start,
        "peptide_end": pep_end,
        "total_sasa": round(total_sasa, 3),
        "mean_relative_sasa": round(mean_rel, 3),
        "exposure_ratio": round(exp_ratio, 3),
        "residues": residues_out,
        "pdb_content": pdb_text,
        "warning": warning,
    }
```

------

### `main.py`

```python
from fastapi import FastAPI, HTTPException
from .models import SASARequest, SASAResponse
from .esm_fold import predict_structure
from .sasa_calc import calc_sasa

app = FastAPI(title="SASA Microservice", version="1.0")

@app.post("/analyze", response_model=SASAResponse)
async def analyze(req: SASARequest):
    try:
        # If no PDB was passed in, run structure prediction first
        pdb_text = req.pdb_content or await predict_structure(req.full_sequence)
        result   = calc_sasa(pdb_text, req.full_sequence, req.peptide_sequence, req.chain_id)
        return SASAResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
```

------

### `requirements.txt`

```
fastapi
uvicorn[standard]
httpx
biopython
freesasa
numpy
pydantic
```

------

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

# freesasa needs build dependencies
RUN apt-get update && apt-get install -y gcc libxml2-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

------

## Startup and Invocation

```bash
# Build and start
docker build -t sasa-service .
docker run -p 8000:8000 sasa-service

# Example call
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "full_sequence": "MAAAAAGGAGAGAGAGYWDHINNPEVYFGGAGAGAGAGAAAAM",
    "peptide_sequence": "YWDHINNPEVYF"
  }'
```

Returns:

```json
{
  "peptide_sequence": "YWDHINNPEVYF",
  "peptide_start": 17,
  "peptide_end": 28,
  "total_sasa": 847.32,
  "mean_relative_sasa": 0.61,
  "exposure_ratio": 0.83,
  "residues": [
    {"residue_id": 17, "residue_name": "TYR", "sasa": 92.1, "relative_sasa": 0.36, "is_exposed": true},
    ...
  ],
  "pdb_content": "ATOM  ...",
  "warning": null
}
```

------

## How to Interpret the Key Metrics

| Metric               | Meaning                                        | Your decision logic                          |
| -------------------- | ---------------------------------------------- | -------------------------------------------- |
| `mean_relative_sasa` | Mean exposure of the functional peptide (0~1)  | > 0.3 is considered good exposure            |
| `exposure_ratio`     | Fraction of exposed residues                   | > 0.6 means most residues are on the surface |
| `total_sasa`         | Absolute exposed area in Å²                    | Used to compare different designs side by side |

These three numbers can go straight into your construct comparison table as the quantitative basis for a "structural compatibility score".
