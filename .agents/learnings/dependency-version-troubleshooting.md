---
name: Dependency version troubleshooting
description: When facing dependency conflicts, always check official docs first before randomly trying version combinations. ESMFold requires Python <= 3.9.
type: feedback
---

# Dependency version troubleshooting

When encountering import errors or version conflicts during Docker build or service startup:

1. **Check official documentation FIRST** — before changing any version pin, check the project's official README, setup.py, environment.yml, or docs. A 2-minute read can save hours of trial-and-error.

2. **Don't shotgun version pins** — randomly trying pydantic 1.9, 1.8, 1.7 etc. is inefficient. Each pin change triggers a Docker rebuild (possibly including CUDA compilation), wasting hours.

3. **Understand the root cause** — the `'not' is not a valid parameter name` error in ESMFold was caused by Python 3.11+ restricting `not` as a function parameter name. This had nothing to do with pydantic version. The fix was switching to Python 3.10 (or <=3.9 as officially documented).

4. **Docker cache can mislead** — when the base layer (e.g., apt-get) changes, all subsequent cached layers are invalidated, triggering a full rebuild. Be aware of what layers will be invalidated before changing a Dockerfile.

**Why:** This was learned after spending an entire day iterating on pydantic/fastapi version combinations, when the official ESMFold docs clearly state "python <= 3.9" as a requirement.

**How to apply:** Before any version-related fix, search the official project docs (README, setup.py, environment.yml) for Python version requirements, dependency specifications, and known compatibility issues.
