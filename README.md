> **English** | [中文](README.zh.md)

# iGEM-silk: Silk Fibroin–Functional Peptide Fusion Design Platform

**iGEM competition project** — a computational screening platform for designing recombinant silk fibroin proteins fused with functional peptides.
It progressively screens the best functional peptides from hundreds of millions of candidate sequences through 16 microservices (ML predictors + structure tools + remote API proxies).

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Quick Start](#2-quick-start)
3. [Pipeline Versions Overview](#3-pipeline-versions-overview)
4. [Microservice Inventory](#4-microservice-inventory)
5. [Core Documentation Index](#5-core-documentation-index)
6. [Knowledge Base and Learning Notes](#6-knowledge-base-and-learning-notes)
7. [References](#7-references)

---

## 1. Project Overview

### Scientific Goal

Using silk fibroin as the scaffold, short peptides with specific functions (antioxidant, anti-melanin, etc.) are inserted into or attached to the scaffold by genetic fusion, so that the recombinant protein combines silk fibroin's self-assembly/film-forming ability with the biological activity of the functional peptide. This makes it suitable for topical applications such as skincare.

### Core Pipeline Philosophy

- **Funnel screening**: tighten round by round, starting from a massive pool of candidate sequences (850 million → final Top 100)
- **Light services first**: high-throughput services run first, while heavy services are reserved for a small number of candidates
- **Safety first**: safety attributes such as toxicity/hemolysis/allergenicity are eliminated independently using hard thresholds
- **Data-driven weights**: weights are computed from the standard deviation of score distributions; metrics with good discrimination automatically receive high weights

### Tech Stack

- **Language**: Python 3.11+ (`from __future__ import annotations`)
- **Package management**: `uv` + `pyproject.toml` (root project + an independent environment per microservice)
- **Microservices**: FastAPI, deployed with Docker Compose (dual GPU + CPU profiles)
- **State management**: DuckDB (stages3/4), CSV relay (stages2)
- **3D structure**: OmegaFold (primary), ESMFold, AlphaFold3

---

## 2. Quick Start

```bash
# Install root project dependencies
uv sync

# Start all microservices (Docker)
cd tools
docker compose --profile gpu --profile cpu up -d

# Or start individual services on demand
docker compose --profile cpu up -d anoxpepred algpred2

# Run a pipeline stage
uv run python -m main.stages2.round01_lightweight   # stages2
uv run python -m main.stages3.stage00_preprocess     # stages3

# Check microservice health
uv run python -c "from main.client import ServiceClient; import asyncio; print(asyncio.run(ServiceClient().check_health()))"
```

---

## 3. Pipeline Versions Overview

The project has gone through four pipeline iterations, each with different design goals and data scales.

### stages (first version)

| Item | Details |
|------|---------|
| **Data volume** | 1,843 antioxidant peptides |
| **Status** | All 7 stages written, partially run |
| **Core documentation** | [`main/stages/PLAN.md`](main/stages/PLAN.md) — funnel design philosophy, microservice cost analysis, GPU memory management |

### stages2 (production version, complete ✅)

**1,081,772 → 90 Top + 60 Bottom candidates**, full 8-round flow in about 6.5 hours.

| Round | Script | Description | Time |
|------|------|------|------|
| 0 | `step00_integrate.py` | Data cleaning (3-30aa filter, deduplication) | ~30s |
| 1 | `round01_lightweight.py` | Full-set scoring with AnOxPePred + AlgPred2 | ~15min |
| 2 | `round02_scoring.py` | Pure AnOxPePred ranking to select Top 25K + Bottom 25K, plus ToxinPred3/HemoPI2/MHCflurry | ~63min |
| 3 | `round03_heavy.py` | +BepiPred3/TemStaPro → Top 80 + Bottom 10 | ~65min |
| 4 | `round04_enumerate.py` | Dual-channel enumeration + 360 constructs → 150 | ~13min |
| 5 | `round05_3d.py` | OmegaFold 3D prediction (150 PDBs) | ~210min |
| 6 | `round06_pdb_eval.py` | SASA + Aggrescan3D evaluation | ~6min |
| 7 | `round07_final.py` | Independent dual-channel ranking → 90 Top + 60 Bottom | ~1min |

**Retrospective document**: [`output2/REVIEW.md`](output2/REVIEW.md) — full retrospective, weight configuration, technical difficulties, Docker issue fixes

**Design documents**:
- [`main/stages2/PLAN.md`](main/stages2/PLAN.md) — three-round progressive scoring, safety labeling system, construct-level re-scoring
- [`main/stages2/PLAN2.md`](main/stages2/PLAN2.md) — alternative plan

### stages3 (billion-scale extended version, in development 🚧)

**849M → 19.9M candidates**, using DuckDB + variance-aware weights.

| Stage | Script | Description | Status |
|------|------|------|------|
| 0 | `stage00_preprocess.py` | FASTA streaming scan → 3-30aa filter → AA filter → DuckDB | ✅ complete |
| 1 | `stage01_lightweight.py` | Batch scoring with AnOxPePred + AlgPred2 | ✅ code ready |
| 2 | To be implemented | Full scoring with 9 services + variance-aware weighting | ⏳ |
| 3-6 | To be implemented | Enumeration → 3D → PDB evaluation → final ranking | ⏳ |

**Key innovations**:
- **Variance-aware weights**: weights are computed from winsorized standard deviations; metrics with good discrimination automatically receive high weights
- **On-demand Docker startup**: each stage starts only the microservices it actually depends on
- **Unified DuckDB state**: 14 tables manage all intermediate data

**Planning documents** (`main/stages3/plan/`):
| Document | Contents |
|------|------|
| [`PLAN.md`](main/stages3/plan/PLAN.md) | Overall roadmap: six-stage funnel, variance-aware weighting workflow, time estimates |
| [`ARCHITECTURE.md`](main/stages3/plan/ARCHITECTURE.md) | Three-layer architecture (orchestration layer/execution layer/service layer) |
| [`DB_SCHEMA.md`](main/stages3/plan/DB_SCHEMA.md) | Design of 15 tables, rationale for choosing DuckDB |
| [`DATA_PREP.md`](main/stages3/plan/DATA_PREP.md) | Data source analysis (UniProt 225M + MGnify 624M), preprocessing strategy |
| [`TECH_REQUIREMENTS.md`](main/stages3/plan/TECH_REQUIREMENTS.md) | Mandatory Docker specifications, asyncio safety, concurrency control |

**Architecture as built**: [`main/stages3/ARCHITECTURE_AS_BUILT.md`](main/stages3/ARCHITECTURE_AS_BUILT.md) — records every deviation between the implementation and the plan

**Completion record**: [`main/stages3/DONE.md`](main/stages3/DONE.md) — Stage 0 full-run report (19.9M candidates written, 98.7 min)

### stages4 (hierarchical filtering version, in development 🚧)

**19.9M → Top 100 + Bottom 100**, a targeted fix for the issues found in stages2.

**Four core principle changes**:
1. **Hierarchical filtering, never cross-attribute weighted averaging** — each round uses a single criterion
2. **Hard thresholds for safety attributes** — toxicity/hemolysis/allergenicity are vetoes
3. **Antioxidant used only once** — used only for the Round 1 split; later rounds do not use it
4. **Variable weights (SD-driven + manual coefficient α)** — the only weighted step is in Round 3

| Round | Script | Description |
|------|------|------|
| 0 | `s4_round00_preprocess.py` | Data preprocessing (reuses stages3) |
| 1 | `s4_round01_antioxidant_split.py` | AnOxPePred ranking → Top 10% + Bottom 1% |
| 2 | `s4_round02_safety_screen.py` | Hard thresholds for ToxinPred3/HemoPI2/MHCflurry |
| 3 | `s4_round03_deep_scoring.py` | SD-driven + manual coefficient α (the only weighted step) |
| 4 | `s4_round04_enumerate.py` | Construct enumeration + SoDoPE/TemStaPro |
| 5 | `s4_round05_3d.py` | OmegaFold 3D prediction |
| 6 | `s4_round06_pdb_eval.py` | SASA + Aggrescan3D |
| 7 | `s4_round07_final.py` | Independent dual-channel ranking |

**Design document**: [`main/stages4/PLAN.md`](main/stages4/PLAN.md) — comparison with stages2, eight-round funnel design, detailed explanation of variable weights

---

## 4. Microservice Inventory

16 microservices + 3 auxiliary services, across three template types (FASTA scoring / Structure prediction / PDB scoring).

### FASTA scoring services (ports 8001-8012)

| Service | Port | Function | Environment | Model source | Model size |
|------|------|------|------|---------|---------|
| **AnOxPePred** | 8001 | Antioxidant activity prediction | GPU/CPU | Git-tracked | 1.3 MB |
| **BepiPred-3.0** | 8002 | B-cell epitope prediction | GPU/CPU | First-run download | 2.5 GB |
| **ToxinPred3** | 8003 | Toxicity prediction | CPU | pip package | 2 MB |
| **HemoPI2** | 8004 | Hemolytic activity prediction | GPU/CPU | pip package | 30 MB |
| **MHCflurry** | 8005 | MHC-I binding affinity | GPU/CPU | First-run download | 100 MB |
| **pLM4CPPs** | 8006 | Cell-penetrating peptide prediction | GPU/CPU | Shared ESM-2 + Git | 30 MB |
| **TIPred** | 8007 | Tyrosinase-inhibitory peptide prediction | CPU | Synthesized training at startup | — |
| **AlgPred2** | 8008 | Allergen prediction | CPU | pip package | 1 MB |
| **GraphCPP** | 8009 | Cell-penetrating peptide GNN | GPU/CPU | Git-tracked | 200 KB |
| **TemStaPro** | 8010 | Thermal stability prediction | GPU/CPU | First-run download | 2.3 GB |
| **SoDoPE** | 8012 | Solubility prediction | CPU | Pure algorithm | — |

### PDB scoring services (ports 8101-8102)

| Service | Port | Function | Environment |
|------|------|------|------|
| **SASA** | 8101 | Solvent-accessible surface area (FreeSASA) | CPU |
| **Aggrescan3D** | 8102 | Aggregation propensity analysis | CPU Docker |

### Structure prediction services (ports 8201-8205)

| Service | Port | Function | Environment |
|------|------|------|------|
| **AlphaFold3** | 8201 | High-accuracy structure prediction | GPU Docker |
| **PEP-FOLD4** | 8202 | De novo structure prediction for short peptides (5-40 aa) | CPU Docker |
| **ESMFold** | 8203 | Fast structure prediction (~60x AF2) | GPU |
| **OmegaFold** | 8204 | PLM + geometric transformer structure prediction | GPU/CPU |
| **Waveflow** | 8205 | Tamarind.bio cloud API proxy | CPU |

### Microservice reference documentation

| Service | Documentation |
|------|------|
| AnOxPePred | [`tools/AnOxPePred/references/anoxpepred_guide.md`](tools/AnOxPePred/references/anoxpepred_guide.md) |
| BepiPred-3.0 | [`tools/BepiPred-3.0/references/`](tools/BepiPred-3.0/references/) (4 documents) |
| ToxinPred3 | [`tools/ToxinPred3/references/`](tools/ToxinPred3/references/) (3 documents) |
| HemoPI2 | [`tools/HemoPI2/SKILL.md`](tools/HemoPI2/SKILL.md) |
| MHCflurry | [`tools/MHCflurry/references/`](tools/MHCflurry/references/) (3 documents) |
| GraphCPP | [`tools/GraphCPP/references/`](tools/GraphCPP/references/) (3 documents) |
| pLM4CPPs | [`tools/pLM4CPPs/references/SKILL.md`](tools/pLM4CPPs/references/SKILL.md) |
| AlgPred2 | [`tools/algpred2/references/`](tools/algpred2/references/) (4 documents) |
| TIPred | [`tools/Tipred/references/SKILL.md`](tools/Tipred/references/SKILL.md) |
| SoDoPE | [`tools/SoDoPE_paper_2020/references/SKILL.md`](tools/SoDoPE_paper_2020/references/SKILL.md) |
| TemStaPro | — |
| SASA | [`references/how-to-use-saas.md`](references/how-to-use-saas.md) |
| Aggrescan3D | [`tools/Aggrescan3D/README.md`](tools/Aggrescan3D/README.md) |

---

## 5. Core Documentation Index

### Project-level documentation

| File | Description |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | Project instructions: development commands, microservice deployment, architecture, pipeline status |
| [`AGENTS.md`](AGENTS.md) | **Production safety rules**: prohibited Git operations (`git clean`/`checkout`/`reset --hard` are absolutely forbidden) |

### Design philosophy

| File | Description |
|------|------|
| [`main/docs/IDEA.md`](main/docs/IDEA.md) | Pipeline design philosophy: funnel screening, three-step strategy, microservice lifecycle, caching mechanisms |
| [`docs/PROGRAM 0.md`](docs/PROGRAM 0.md) | Exploratory plan: scientific background (silk fibroin structure, insertion-site strategies), dry lab engineering architecture |
| [`main/stages/PLAN.md`](main/stages/PLAN.md) | First pipeline design: cost table for 15 microservices, four-stage orchestration, GPU memory management, adaptive logic |

### API specifications

| File | Description |
|------|------|
| [`main/docs/api/conventions.md`](main/docs/api/conventions.md) | API conventions manual: endpoints and response formats for the three templates (FASTA/PDB/Structure), label reference table, concurrency parameter quick reference |
| [`main/docs/api/quirks.md`](main/docs/api/quirks.md) | Known API pitfalls: SASA batch response-format differences, OmegaFold blocking the event loop, ToxinPred3 thread unsafety |
| [`main/docs/threshold.md`](main/docs/threshold.md) | Safety thresholds: ToxinPred3 ≥0.38, AlgPred2 ≥0.30, HemoPI2 HC50 ≤100μM, TemStaPro |

### Docker operations

| File | Description |
|------|------|
| [`tools/Docker.md`](tools/Docker.md) | Complete Docker operations guide: integration of 23 experience capsules; the full build/deploy/monitor/troubleshoot workflow |
| [`tools/README.md`](tools/README.md) | Microservice directory: service inventory, port allocation table, model management strategy, model download and image-mirror configuration |

### Human-operated analysis tools (for wet-lab researchers)

| File | Description |
|------|------|
| [`docs/HUMAN.md`](docs/HUMAN.md) | Human-operated analysis tools: Binding ddG scanning of key functional-peptide residues, GROMACS MD simulation |
| [`references/how-to-use-saas.md`](references/how-to-use-saas.md) | SASA service user guide: FastAPI + FreeSASA + Biopython |
| [`references/identify_the_embedded_sequence.md`](references/identify_the_embedded_sequence.md) | Method for mapping sequence positions to PDB residue numbers |
| [`references/what-is-GROMACS.md`](references/what-is-GROMACS.md) | Introduction to GROMACS molecular dynamics simulation |
| [`references/Inclusion body → Refolding.md`](references/Inclusion%20body%20%E2%86%92%20Refolding%EF%BC%9A%E6%A0%B8%E5%BF%83%E9%97%AE%E9%A2%98%E4%B8%8E%E5%BA%94%E5%AF%B9%EF%BC%88%E7%AE%80%E7%89%88%EF%BC%89.md) | Core issues in inclusion-body refolding |

### Other academic references

| File | Description |
|------|------|
| [`references/how_to_use_esm.md`](references/how_to_use_esm.md) | ESM model user guide |
| [`references/how-to-use-Alphafolw.md`](references/how-to-use-Alphafolw.md) | AlphaFlow user guide |
| [`references/PROGRAM Old.md`](references/PROGRAM%20Old.md) | Archived original OxidShield plan |

### Pipeline output reports

| File | Description |
|------|------|
| [`output2/REVIEW.md`](output2/REVIEW.md) | stages2 full retrospective: weight configuration, data funnel, technical difficulties, Docker issue fixes |
| [`output2/STATUS.md`](output2/STATUS.md) | stages2 progress pointer |
| [`output3/STATUS.md`](output3/STATUS.md) | stages3 environment status |
| [`output3/reports/stage0_report.md`](output3/reports/stage0_report.md) | stages3 Stage 0 processing report |

---

## 6. Knowledge Base and Learning Notes

### Experience capsules (`.agents/learnings/`)

**Index file**: [`.agents/learnings/MEMORY.md`](.agents/learnings/MEMORY.md) — index of all 30+ experience records

**Docker-specific** ([`.agents/learnings/docker/`](.agents/learnings/docker/)):

| Topic | File |
|------|------|
| Docker Hub unreachable in China (DaoCloud mirror acceleration) | `docker/docker-hub-china-mirror.md` |
| Compose build atomicity flaw | `docker/compose-atomic-build.md` |
| Installing the Docker CLI inside a container | `docker/docker-cli-in-container.md` |
| Docker-outside-of-Docker path issues | `docker/docker-outside-docker-paths.md` |
| Python namespace shadowing | `docker/python-namespace-shadowing.md` |
| Missing C build dependencies in slim images | `docker/slim-image-build-deps.md` |
| Linux case sensitivity | `docker/linux-case-sensitivity.md` |
| Version uncertainty of the `latest` tag | `docker/latest-tag-pinning.md` |
| Auditing Dockerfile COPY omissions | `docker/dockerfile-copy-audit.md` |
| Dockerfile path consistency | `docker/dockerfile-path-compose.md` |
| Batch failure audit | `docker/batch-failure-audit.md` |

**Pipeline engineering**:

| Topic | File |
|------|------|
| asyncio.gather exception propagation | `gep-asyncio-gather-exception-safety.md` |
| Dual-channel Top/Bottom design | `gep-dual-channel-top-bottom-pipeline.md` |
| Pipeline stage orchestration and checkpoints | `gep-pipeline-stage-orchestration.md` |
| Structure-prediction confidence cascade | `gep-pipeline-confidence-cascade.md` |
| Weight iteration and data-driven decisions | `gep-weight-iteration-data-driven.md` |
| Direct connection via Docker bridge IP | `gep-docker-container-bridge-ip.md` |
| Microservice network-binding strategy | `microservice-host-binding.md` |

**GPU and performance**:

| Topic | File |
|------|------|
| GPU memory contention | `gpu-memory-contention.md` |
| Residual PyTorch CUDA cache | `gep-pytorch-cuda-cache-gpu-memory-leak.md` |
| BepiPred3 GPU timeout tuning | `gep-bepipred3-gpu-timeout-tuning.md` |
| OmegaFold synchronous inference blocking | `gep-omegafold-sync-inference-blocking.md` |
| ESMFold dependency version matrix | `gep-esmfold-dependency-matrix.md` |
| ToxinPred3 single-threaded hang | `gep-toxinpred3-concurrency-limit.md` |
| Reducing the GPU bottleneck with TemStaPro pre-screening | `gep-temstapro-prescreen-gpu-bottleneck.md` |

**Structure prediction**:

| Topic | File |
|------|------|
| Three-layer ESMFold Docker build | `gep-esmfold-docker-build.md` |
| Waveflow remote API proxy | `gep-waveflow-remote-api-service.md` |
| Structure Service pattern | `structure-service-pattern.md` |

---

## 7. References

### Academic papers (tool citations)

The academic sources for each microservice can be found in the corresponding `tools/<name>/references/` directory:

- **ToxinPred3**: Rathore et al., 2024, *Computers in Biology and Medicine*
- **HemoPI2**: Rathore et al., 2025, *Communications Biology*
- **AlgPred2**: Sharma et al., 2021, *Briefings in Bioinformatics*
- **TemStaPro**: Pudžiuvelytė et al., 2024, *Bioinformatics*
- **SoDoPE**: solubility prediction (SWI method)

### Silk fibroin background

- Heidebrecht & Scheibel, 2013 — recombinant silk fibroin expression
- Wohlrab et al., 2012 — RGD-functionalized spider silk protein
- Xia et al., 2010 — silk fibroin expression in E. coli
