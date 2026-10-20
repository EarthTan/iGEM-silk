> **English** | [中文](README.zh.md)

# Microservices

The microservices fall into three categories:

- **Fasta scoring service** (`fasta_service`): takes FASTA sequences and outputs scoring results
- **3D structure generation** (`structure_service`): takes FASTA sequences and outputs 3D structure models (PDB)
- **PDB scoring service** (`pdb_service`): takes PDB structures and outputs scoring results

### Service Design Principles

1. **Original work first**. Prefer the original authors' code, design ideas, models and implementation methods, staying as faithful as possible. This represents the project's academic grounding and avoids AI hallucination and hand-waving.

2. **Environment compatibility**. The main development environment for this project is the latest macOS; actual deployment uses Ubuntu + RTX5880.
- To make API testing convenient on the development machine: for tools that can be CUDA-accelerated, configure the Dockerfile for easy GPU-environment deployment; code automatically detects GPU availability and falls back to CPU; services that can run only on GPU report an explicit error in a CPU environment.
- For actual production deployment on Ubuntu, all microservices **must** be started with `docker`.

3. **Centralized model file management**. Model files live in `tools/<name>/models/` (service-specific) or `tools/models/` (shared across services). The four source types (Git-tracked with the repository / first-run download / pip package / no model needed) are detailed in the "Model Management" section below.

4. **Unified interface**. Use a unified API contract, interlocking with the `main/` core framework.

5. **Concurrency and high throughput**. Aim for high-performance, high-speed prediction to raise the range of processable scales.

### How to Start

Starting a single service:

```bash
# Take MHCflurry (8005) as an example
cd tools/MHCflurry
source .venv/bin/activate
python service.py
```

Script startup:

```bash
./tools/start_all.sh           # Start everything with one command
./tools/start_all.sh status    # Check status
./tools/start_all.sh stop      # Stop everything
# Logs: tools/logs/<name>.log
```

Docker startup:

```bash
cd tools && docker compose --profile gpu --profile cpu up -d
```

### Port Allocation Table

##### Fasta Service (8001+)

| Service | Port | Range | Purpose | Environment | Model |
|------|------|------|------|------|------|
| AnOxPePred | 8001 | Short peptides 2~30 (CNN) / medium peptides 31~50 (truncated) | Antioxidant activity prediction | GPU/CPU | [Git] CNN · 1.3 MB |
| BepiPred-3.0 | 8002 | Short peptides ≥5 / proteins ≤5000 | B-cell epitope prediction | GPU/CPU | [Shared] ESM-2 t33 · 2.5 GB |
| ToxinPred3 | 8003 | Short peptides ≥2 / proteins (no upper limit) | Toxicity prediction | CPU | [pip] ExtraTrees · 2 MB |
| HemoPI2 | 8004 | Short peptides ≤40 (truncated beyond that) | Hemolysis prediction | GPU/CPU | [pip] ESM-2 t6 fine-tuned · 30 MB |
| MHCflurry | 8005 | MHC-I peptides 8~15 | MHC-I binding affinity prediction | GPU/CPU | [Download] MHCflurry · 100 MB |
| pLM4CPPs | 8006 | Short peptides ≥5 / proteins (no upper limit) | Cell-penetrating peptide prediction | GPU/CPU | [Shared] ESM-2 t6 · 30 MB + [Git] CNN+scaler · 2 MB |
| TIPred | 8007 | Short peptides ≥3 / proteins (no upper limit) | Tyrosinase inhibitory peptide prediction | CPU | [—] Synthesized and trained at startup |
| AlgPred2 | 8008 | Medium peptides ~ proteins (optimized for long sequences) | Allergenicity prediction | CPU | [pip] RandomForest · 1 MB |
| GraphCPP | 8009 | Short peptides 5~40 (>100 accuracy degrades) | Cell-penetrating peptide prediction (GNN) | GPU/CPU | [Git] GraphSAGE ckpt · 200 KB |
| TemStaPro | 8010 | Full range | Thermal stability prediction (40–65°C) | GPU/CPU | [Download] ProtT5-XL · 2.3 GB + MLP×30 · 80 MB |
| SoDoPE | 8012 | Full range | Solubility prediction (SWI) | CPU | [—] Pure table lookup + arithmetic |

##### PDB Service (8101+)

| Service | Port | Range | Purpose | Environment | Model |
|------|------|------|------|------|------|
| SASA | 8101 | Proteins/peptides (no upper limit) | Solvent-accessible surface area analysis | CPU | [—] FreeSASA algorithm |
| Aggrescan3D | 8102 | PDB structures | Structural aggregation propensity analysis | CPU (Docker) | [Docker] Built into the A3D image |

##### Structure Service (8201+)

| Service | Port | Range | Purpose | Environment | Model |
|------|------|------|------|------|------|
| AlphaFold3 | 8201 | Proteins/peptides/DNA/RNA/ligands | 3D biomolecular structure prediction | GPU required (Docker, Ubuntu only) | [Docker] AF3 parameters + genetic databases · TB scale |
| PEP-FOLD4 | 8202 | Short peptides 5~40 aa | De novo peptide structure prediction | CPU (Docker) | [Docker] Built-in sOPEP force field |
| ESMFold | 8203 | Short peptides ~ proteins (no upper limit) | Fast 3D structure prediction (ESM-2 3B, ~60x AF2) | GPU required | [Download][Shared] ESMFold 3B · 8 GB + ESM-2 t36 · 6 GB |
| OmegaFold | 8204 | Short peptides ~ proteins (no upper limit) | PLM + geometric transformer structure prediction | GPU/CPU/MPS | [Download] OmegaFold ~1.5 GB (auto-downloaded from S3) |
| **Waveflow** | **8205** | **Full range** | **Tamarind.bio cloud proxy: the URL specifies the tool type (esmfold/omegafold/alphafold, etc.), no local GPU/model needed** | **CPU** | **[—] Pure remote API, no local model needed** |

### Model Management

The model files for each service are obtained in one of the following five ways:

| Source | Tag | Location | Example |
|------|------|------|------|
| **Git-tracked with the repository** | `[Git]` | Under `tools/<name>/`, tracked directly by git (< 50 MB) | AnOxPePred CNN, GraphCPP GCN |
| **Downloaded on first startup** | `[Download]` | `tools/<name>/models/`, downloaded automatically by `load_model()` and gitignored | MHCflurry, TemStaPro |
| **Bundled with the pip package** | `[pip]` | Inside `.venv/`, installed along with pip install | ToxinPred3, HemoPI2, AlgPred2 |
| **No model needed** | `[—]` | Pure algorithm or synthesized and trained at startup | TIPred, SoDoPE, SASA |
| **Built into Docker** | `[Docker]` | Inside the Docker image, not exposed to the host machine | PEP-FOLD4, Aggrescan3D, AlphaFold3 |

**Shared model cache:** `tools/models/` holds models shared by multiple services to avoid duplicate downloads. Currently shared:

```
tools/models/
  fair-esm/                     ← ESM-2 checkpoints (torch.hub cache)
    hub/checkpoints/
      esm2_t6_8M_UR50D.pt       ← pLM4CPPs + future other services (Git-tracked, ~29 MB)
      esm2_t33_650M_UR50D.pt    ← BepiPred-3.0 + future other services (auto-downloaded on first run, ~2.5 GB)
      esm2_t36_3B_UR50D.pt      ← ESMFold (ESM-2 3B backbone, auto-downloaded on first run, ~5.3 GB)
      esmfold_3B_v1.pt          ← ESMFold structure head (auto-downloaded on first run, ~2.6 GB)
  omegafold/
    model.pt                    ← OmegaFold weights (auto-downloaded on first run, ~1.5 GB)
```

BepiPred-3.0, pLM4CPPs and ESMFold all set `TORCH_HOME=tools/models/fair-esm/`, so models are downloaded only once. For first-time deployment, `./tools/migrate_models.sh` can migrate existing files.

The shared pool **stores only models used by ≥2 services** or **large models**. Models that are unique and small stay in their own `models/` directory and are not moved in ahead of time — scale up on demand.

Docker deployment mounts `tools/models/` into the container at the corresponding path via a volume, so models do not enter the image.

### Model Downloads and Mirror Source Configuration

The following models are downloaded automatically from overseas CDNs on first startup and may fail on networks in mainland China.
The download address can be overridden by setting environment variables (pointing to a mirror or a local path):

| Service | Auto-downloaded model | Size | Default source | Override environment variable |
|------|---------------|------|--------|-------------|
| ESMFold | esmfold_3B_v1.pt | ~2.6 GB | `dl.fbaipublicfiles.com/fair-esm/` (Meta CDN) | `ESMFOLD_MODEL_URL` |
| BepiPred-3.0 | esm2_t33_650M_UR50D.pt | ~2.5 GB | Same as above | `ESM2_URL` |
| TemStaPro | ProtT5-XL | ~3 GB | HuggingFace `Rostlab/prot_t5_xl_half_uniref50-enc` | `HF_ENDPOINT=https://hf-mirror.com` |
| OmegaFold | release1.pt | ~1.5 GB | `helixon.s3.amazonaws.com` (AWS S3) | `OMEGAFOLD_WEIGHTS_URL` |
| HemoPI2 | ESM-2 t6 (via pip) | ~29 MB | HuggingFace | `HF_ENDPOINT=https://hf-mirror.com` |

Mirror source configuration example:

```bash
# Use the HuggingFace mirror (for ProtT5-XL and HemoPI2's ESM-2)
export HF_ENDPOINT=https://hf-mirror.com

# Use a custom model URL (for the fair-esm models of ESMFold and BepiPred-3.0)
export ESMFOLD_MODEL_URL=https://internal-mirror.example.com/models/esmfold_3B_v1.pt
export ESM2_URL=https://internal-mirror.example.com/models/esm2_t33_650M_UR50D.pt

# Use a custom OmegaFold weights URL
export OMEGAFOLD_WEIGHTS_URL=https://internal-mirror.example.com/omegafold/release1.pt

# Pre-download approach: download manually, then place into the shared cache
# wget -P tools/models/fair-esm/hub/checkpoints/ \
#   https://dl.fbaipublicfiles.com/fair-esm/models/esmfold_3B_v1.pt
```

### Runtime Environment Notes

**GPU vs CPU:** The following services are marked with the `gpu` profile in docker-compose but actually support degraded CPU operation:

- AnOxPePred (TensorFlow automatic device selection, degrades to rules when the model is missing)
- HemoPI2 / MHCflurry / pLM4CPPs / GraphCPP / TemStaPro (PyTorch automatic device selection)

**Services that run only in Docker:**
- AlphaFold3 — requires NVIDIA Docker + a Linux host machine, invoked via the Docker CLI
- PEP-FOLD4 — invoked via the Docker CLI, CPU is sufficient
- Aggrescan3D — depends on a conda Python 2.7 environment, Docker Compose recommended

**Services with external dependencies:**
- Waveflow — requires a tamarind.bio API key (`TAMARIND_API_KEY`), no local GPU/model needed
