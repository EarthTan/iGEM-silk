---
name: freesasa 2.2.1 selectArea API Incompatible v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [freesasa, sasa, api, python, open-source]
validated: true
---

> English translation of [gep-freesasa-selectarea-api.md](gep-freesasa-selectarea-api.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: freesasa 2.2.1 selectArea API Incompatible

## Experience

**Problem type**: The `selectArea()` API signature changed in version 2.2.1 of the freesasa Python library, causing existing code to crash.

**Core strategy**:
1. When you see `expected bytes, tuple found` or a `TypeError`, immediately locate the `freesasa.selectArea()` call
2. Check the installed version: `python -c "import freesasa; print(freesasa.__version__)"`
3. Versions < 2.2.0 use the `[(name, expression)]` list-of-tuples format; versions ≥ 2.2.1 use the `["name, expression"]` single-string format
4. Try both formats directly in the virtual environment to confirm compatibility

**Key parameters**:

| Version | selectArea format | Example |
|------|----------------|------|
| ≤ 2.2.0 | `[(name, expr)]` list of tuples | `freesasa.selectArea([("residue", "resi 1 and chain A")], ...)` |
| ≥ 2.2.1 | `["name, expr"]` list of single strings | `freesasa.selectArea(["residue, resi 1 and chain A"], ...)` |

**Typical error messages**:
- `TypeError: expected bytes, tuple found` — 2.2.1 no longer accepts tuples
- An implicit, silent return of an empty `{}` can also occur (passing the old format to 2.2.1 makes the internal parsing fail)

## Environment Fingerprint

- **Task domain**: Calling an open-source Python bioinformatics library, FreeSASA solvent-accessible surface area computation
- **Input characteristics**: `pip install freesasa` automatically installs the latest version; the project may not pin the version
- **Constraints**: pip installs the latest version by default; without a version pin it upgrades to 2.2.1+ automatically
- **Not applicable**: Projects that already pin `freesasa<2.2.1`; environments installed via conda where conda has not yet pushed 2.2.1

## Audit Record

- **Validation method**: Runtime crash inside the iGEM-silk SASA microservice Docker container, plus post-fix validation
- **Test cases**:
  1. Old format `[("residue", "resi 1 and chain A")]` → `TypeError: expected bytes, tuple found`
  2. New format `["residue, resi 1 and chain A"]` → returns normally `{'residue': 85.3}`
  3. After the fix, batch scoring of 90 PDBs → all succeeded, SASA mean=0.742
- **Success rate**: 100%
- **Limitations**: If freesasa changes the API format again in the future, this fix will break again

## Usage

- **Trigger conditions**: The SASA service's `POST /predict` returns 500 and the `selectArea` call reports `TypeError: expected bytes`
- **How to invoke**: Find the `freesasa.selectArea()` calls and change all tuple arguments to the single-string `"name, expression"` format
- **Caveats**: Docker builds pull the latest freesasa version, so the next build may change again. It is recommended to pin `freesasa>=2.2.1` in `pyproject.toml` and support both formats in the code, or fix the exact version number
