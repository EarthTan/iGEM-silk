---
title: MHCflurry Model Download Failure Handling
type: gep
created: 2026-05-17
status: verified
---

> English translation of [gep-mhcflurry-model-download.md](gep-mhcflurry-model-download.md). The Chinese original is kept unchanged as the source of truth.

## Problem

MHCflurry's model download fails during the Docker build, and at runtime `Class1AffinityPredictor.load()` reports an error:
```
RuntimeError: Missing MHCflurry downloadable file: /app/tools/MHCflurry/models/models_class1_pan/models.combined
```

## Cause

1. **The Dockerfile is missing the `--release` parameter**: after setting a custom path via `MHCFLURRY_DOWNLOADS_DIR`, `mhcflurry-downloads fetch` must include `--release 2.2.0`, otherwise it reports "No release defined"
2. **`|| exit 0` swallows the error**: the Dockerfile uses `|| exit 0` so the build reports no error, but the model is not actually downloaded
3. **GitHub is unreachable from China**: the model URL `https://github.com/openvax/mhcflurry/releases/download/pre-2.0/models_class1_pan.selected.20200610.tar.bz2` times out on a direct connection from China

## Fix Methods

### Method 1: download via ghproxy (recommended, suitable for China networks)

```bash
# Download the model from the ghproxy mirror (156MB)
curl -L -o /tmp/mhcflurry_models.tar.bz2 \
  "https://ghproxy.net/https://github.com/openvax/mhcflurry/releases/download/pre-2.0/models_class1_pan.selected.20200610.tar.bz2"

# Extract
mkdir -p /tmp/mhcflurry_models
cd /tmp/mhcflurry_models
tar xjf /tmp/mhcflurry_models.tar.bz2

# Directory structure inside the container
# /app/tools/MHCflurry/models/models_class1_pan/
#   ├── models.combined/       ← the weight files are in this directory
#   ├── additional_alleles.txt
#   └── ...

# Copy into the container
docker cp /tmp/mhcflurry_models/. mhcflurry:/app/tools/MHCflurry/models/models_class1_pan/
```

### Method 2: use COPY in the Dockerfile

```dockerfile
# Replaces RUN mhcflurry-downloads fetch because of network restrictions
COPY models/ /app/tools/MHCflurry/models/
```

Note that a complete local `models/` directory structure is required.

### Method 3: online download (when GitHub is accessible)

```dockerfile
RUN mkdir -p /app/tools/MHCflurry/models && \
    MHCFLURRY_DOWNLOADS_DIR=/app/tools/MHCflurry/models \
    mhcflurry-downloads fetch models_class1_pan --release 2.2.0
```

## Verification

```bash
# Check the health status
curl http://127.0.0.1:8005/health
# Should return: model_loaded=true, alleles=14883

# Test prediction
curl -X POST http://127.0.0.1:8005/predict/batch \
  -H "Content-Type: application/json" \
  -d '{"sequences": [{"sequence": "ACGTKLMN", "peptide_id": "test001"}]}'
```

## References

- MHCflurry version: 2.2.1
- Model file: `models_class1_pan.selected.20200610.tar.bz2` (156MB)
- Model path: `/app/tools/MHCflurry/models/models_class1_pan/models.combined/`
- Number of alleles: 14,883
