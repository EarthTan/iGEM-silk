> **English** | [中文](README.zh.md)

# Aggrescan3D Microservice

Aggrescan3D is a tool for analyzing protein aggregation propensity from PDB structures. The
original tool is a Python 2.7 standalone/CLI; this service invokes the `aggrescan` command
through a conda environment.

## Type

- Microservice category: `pdb_service`
- Input: PDB text
- Output: overall structural aggregation risk score, chain-level statistics, per-residue A3D score
- Default port: `8102`

## Environment Setup

Aggrescan3D depends on Python 2.7. Create a dedicated environment with conda:

```bash
# Create a Python 2.7 environment and install aggrescan3d
conda create -n aggrescan3d python=2.7
conda install -n aggrescan3d -c lcbio aggrescan3d

# Install the API wrapper dependencies
cd tools/Aggrescan3D
uv sync
```

Start the service:

```bash
cd tools/Aggrescan3D
uv run python service.py
```

Environment variables:
- `AGGRESCAN_CONDA_ENV` — conda environment path (default: `/home/lenovo/miniconda3/envs/aggrescan3d`)

## Testing

Health check:

```bash
curl http://127.0.0.1:8102/health
```

Testing with an existing PDB file:

```bash
python - <<'PY'
import json
from pathlib import Path
import httpx

pdb = Path("references/result-kyxq0/model.pdb").read_text()
payload = {
    "pdb_content": pdb,
    "chain_id": "A",
    "peptide_id": "model_kyxq0",
}
r = httpx.post("http://127.0.0.1:8102/predict", json=payload, timeout=600)
print(json.dumps(r.json(), indent=2, ensure_ascii=False)[:4000])
PY
```

## Output Interpretation

`details.residues` keeps the original Aggrescan3D per-residue scores; `score` is a 0-1
aggregation risk score additionally computed by the service layer to unify the API, where a
higher value means a higher aggregation risk. The current algorithm combines the fraction of
positive-score residues, the mean of the positive scores, and the maximum hotspot score after
normalization; for formal ranking, it is recommended to treat it as an inverse metric.

The raw result file comes from Aggrescan3D's `A3D.csv`:

```text
protein,chain,residue,residue_name,score
```
