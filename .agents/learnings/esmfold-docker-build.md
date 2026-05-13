---
name: ESMFold Docker build patterns
description: Proven Dockerfile structure and version matrix for ESMFold microservice on CUDA 12.1 + Python 3.10.
type: reference
---

# ESMFold Docker build patterns

## Verified working Dockerfile structure

Three-layer build to optimize cache reuse:

```
Layer 1: apt + torch + numpy<2     (rarely changes)
Layer 2: openfold v2.2.0 from git  (~12min CUDA compile, changes rarely)
Layer 3: pip deps (fastapi, fair-esm, deepspeed)  (changes most often)
```

Never merge Layer 2 and Layer 3 — openfold CUDA compilation takes ~12 minutes; pip deps change much more often.

## Version matrix (verified 2026-05-13)

| Component | Version | Notes |
|---|---|---|
| Base image | `nvidia/cuda:12.1.0-devel-ubuntu22.04` | Don't use `runtime` tag, need nvcc |
| Python | 3.10 (apt) | 3.11+ breaks openfold `not` param |
| PyTorch | cu121 wheel | `--index-url https://download.pytorch.org/whl/cu121` |
| numpy | `<2` | Pin WITH torch install, not in Layer 3 |
| openfold | v2.2.0 from GitHub | v1.x can't compile on CUDA 12 (sm_37 deprecated) |
| fair-esm | 2.0.0 from PyPI | GitHub HEAD has IPA changes incompatible with checkpoint |
| deepspeed | `>=0.9.0` | 0.5.9 lacks `deepspeed.comm` module |
| fastapi | `>=0.100.0` | deepspeed≥0.9 forces pydantic v2, fastapi 0.99 incompatible |

## Critical: ESMFold model loading

Do NOT use `esm.pretrained.esmfold_v1()`. Its manual key check rejects IPA module
keys missing from the checkpoint (openfold v2.2.0 refactored IPA paths):

```python
# Wrong — raises RuntimeError on key mismatch
self.model = esm.pretrained.esmfold_v1()

# Correct — skip the key check
model_data = torch.hub.load_state_dict_from_url(url, map_location="cpu")
self.model = ESMFold(esmfold_config=model_data["cfg"]["model"])
self.model.load_state_dict(model_data["model"], strict=False)
self.model = self.model.eval().cuda()
```

Missing IPA projections (linear_q_points, linear_kv_points) are randomly
initialized. Verified to produce valid PDB structures despite this.
