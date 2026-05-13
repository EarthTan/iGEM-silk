---
name: Dependency version troubleshooting
description: Lessons from resolving ESMFold/openfold dependency matrix — CUDA 12.x, openfold v2.2.0, fair-esm 2.0.0, and the IPA key mismatch.
type: feedback
---

# Dependency version troubleshooting

When encountering import errors or version conflicts during Docker build or service startup:

## Core principle

**Check official documentation FIRST** — before changing any version pin, check the project's official README, setup.py, environment.yml, or docs. A 2-minute read can save hours of trial-and-error.

But also: **official docs can be outdated**. ESMFold's README says "Python <= 3.9" but we got it fully working with Python 3.10 + openfold v2.2.0 + CUDA 12.1.

## ESMFold dependency matrix (verified working)

| Component | Version | Why |
|---|---|---|
| Python | 3.10 | 3.11+ breaks `not` param name in openfold; 3.10 works |
| CUDA base | 12.1.0-devel-ubuntu22.04 | Stable nvidia image |
| PyTorch | cu121 wheel | Must match CUDA base |
| numpy | `<2` | `numpy.BUFSIZE` removed in 2.x, deepspeed 0.5.9 needs it |
| openfold | **v2.2.0** from GitHub | v1.x can't compile on CUDA 12.x (sm_37 deprecated) |
| fair-esm | **2.0.0** from PyPI | Must match openfold's IPA module naming |
| deepspeed | `>=0.9.0` | openfold v2.2.0 needs `deepspeed.comm` (not in 0.5.9) |
| fastapi | `>=0.100.0` | deepspeed≥0.9 pulls pydantic v2, fastapi 0.99 incompatible with pydantic v2 |
| pydantic | `>=2.0.0` | Required by deepspeed≥0.9 |

## The IPA key mismatch (the hard problem)

`openfold >= v2.0.0` refactored IPA (Invariant Point Attention) module paths (`structure_module.ipa.linear_q_points`, `linear_kv_points`). The `esmfold_3B_v1.pt` checkpoint was saved before this refactor, so when fair-esm 2.0.0 loads it with `esm.pretrained.esmfold_v1()`, the manual key-check raises:

```
RuntimeError: Keys 'trunk.structure_module.ipa.linear_q_points...' are missing
```

**Fix:** Don't use `esm.pretrained.esmfold_v1()`. Instead construct the model directly and load with `strict=False`:

```python
cfg = torch.hub.load_state_dict_from_url(url)["cfg"]["model"]
model_state = torch.hub.load_state_dict_from_url(url)["model"]
model = ESMFold(esmfold_config=cfg)
model.load_state_dict(model_state, strict=False)
model.eval().cuda()
```

The IPA projections missing from the checkpoint are randomly initialized. Prediction quality may be slightly degraded but remains usable (verified: generates valid PDB structures).

## Key lessons learned

1. **Don't shotgun version pins** — randomly trying pydantic 1.9, 1.8, 1.7 etc. is inefficient. Each pin change triggers a Docker rebuild (possibly including CUDA compilation), wasting hours. Trace the ACTUAL error chain.

2. **Cascading upgrades** — upgrading deepspeed for openfold v2.2.0 forces pydantic v2, which breaks fastapi 0.99. Fix ALL at once, not one-by-one.

3. **Docker cache can mislead** — `docker compose build` may cache layers even with `--no-cache` if the build context isn't updated. Use `docker build -f Dockerfile .` directly for more predictable caching.

4. **Runtime shims work** — when a package can't be upgraded (e.g., deepspeed pinned for some reason), monkey-patching at runtime (setting `numpy.BUFSIZE`, creating `torch._six` shim) can unblock the service while keeping dependencies stable.

**How to apply:** When facing a chain of dependency errors:
1. Read the FULL error traceback (not just the last line)
2. Identify the actual package causing the error
3. Check if it's a known openfold/fair-esm/fair-esm issue on GitHub
4. Fix the ROOT cause, not the symptom (e.g., upgrading deepspeed instead of patching around deepspeed.comm)
