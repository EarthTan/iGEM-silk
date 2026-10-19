---
name: Dockerfile COPY Omission Audit v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, dockerfile, copy, import-error, audit, iGEM-silk]
validated: true
---

> English translation of [dockerfile-copy-audit.md](dockerfile-copy-audit.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Dockerfile COPY Omission Audit

## Experience

**Problem type**: The Dockerfile omits a COPY for a shared dependency file; the build passes but imports fail at runtime.

**Core strategy**: Use a script to batch-scan all Dockerfiles and ensure the key shared files are COPYed.

**Key parameters**: The shared file list (`tools/utils.py`, `tools/template/`)

Several Dockerfiles COPY only `tools/template/` and `tools/<service>/`, but miss `tools/utils.py`. At runtime `from tools.utils import detect_system` fails—and the build stage reports no error.

### Batch Audit Script

```bash
for f in tools/*/Dockerfile; do
  if ! grep -q 'COPY.*utils\.py' "$f" 2>/dev/null; then
    echo "MISS: $f"
  fi
done
```

### Extended Checks

```bash
# Check all key shared files
for f in tools/*/Dockerfile; do
  for dep in "utils.py" "template/" "__init__.py"; do
    if ! grep -q "COPY.*$dep" "$f" 2>/dev/null; then
      echo "MISS $dep in $f"
    fi
  done
done
```

## Environment Fingerprint

- **Task domain**: Multi-service Docker projects
- **Input characteristics**: Multiple services share framework code (`tools/template/`, `tools/utils.py`)
- **Constraints**: Most easily missed when configuring a newly added service for the first time
- **Not applicable**: Single-service projects, or projects without shared code

## Audit Record

- **Validation method**: Several iGEM-silk services built fine in Docker but raised `ModuleNotFoundError` at runtime
- **Failure case**: `from tools.utils import detect_system` → ModuleNotFoundError; the Dockerfile was missing `COPY tools/utils.py /app/tools/utils.py`
- **Fix validation**: After the script scanned all Dockerfiles and the missing COPY lines were added, everything ran normally

## Usage

- **Trigger conditions**: The Docker build passes but `import` raises ModuleNotFoundError at runtime
- **How to invoke**: Run the batch audit script → add the missing COPY lines → rebuild
- **Caveats**: The build stage reports no error because Python imports are resolved only at runtime—do not rely on a passing build to verify COPY completeness
