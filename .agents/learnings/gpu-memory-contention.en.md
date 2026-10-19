---
name: Diagnosing and Avoiding GPU Memory Contention v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [gpu, memory, cuda, docker, oom, troubleshooting]
validated: true
---

> English translation of [gpu-memory-contention.md](gpu-memory-contention.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Diagnosing and Avoiding GPU Memory Contention

## Experience

**Problem type**: When multiple GPU microservices are started at the same time via Docker Compose, the 48GB of a single card is exhausted by several large models, causing CUDA OOM and JAX initialization failures.

**Core strategy**:
1. **Test GPU services one at a time** — do not start all GPU services at once; test only the one needed. Use `docker compose --profile gpu up -d <service>` to start a single service
2. **Free GPU memory before testing AF3** — AlphaFold3 (JAX) takes up almost all 48GB and cannot coexist with other GPU services. Before starting AF3, `docker compose stop <service>` the other GPU services
3. **Confirm memory with `nvidia-smi`** — run `nvidia-smi` to check memory usage before submitting a prediction and confirm there is enough free memory
4. **Memory isolation (production)** — in production, GPU services should own the GPU exclusively, or use `CUDA_VISIBLE_DEVICES` or MIG (Multi-Instance GPU) for memory isolation

**Key parameters**:

| Service | Model | Approximate GPU memory |
|------|------|----------|
| BepiPred3 | ESM-2 t33 | ~6 GB |
| pLM4CPPs | ESM-2 t6 | ~2.5 GB |
| HemoPI2 | ESM-2 t6 | ~2.5 GB |
| MHCflurry | Ensemble | ~2 GB |
| TemStaPro | ProtT5-XL | ~11 GB |
| GraphCPP | GraphSAGE-GNN | ~1 GB |
| AnOxPePred | CNN | ~1 GB |
| AlphaFold3 | JAX | ~46 GB |

AF3 alone takes up almost all 48GB and cannot coexist with other GPU services.

**Typical symptoms**:
- `CUDA error: out of memory` — allocation fails while loading an ESM-2 model
- `Unable to initialize backend 'cuda': INTERNAL: no supported devices found` — JAX cannot find a CUDA device during initialization because GPU memory is already exhausted
- Health check passes but prediction fails — the health check only checks the environment and does not allocate GPU memory

## Environment Fingerprint

- **Task domain**: GPU microservice Docker deployment, protein structure prediction / ML inference
- **Input characteristics**: Multiple large models (ranging from 1-46 GB) sharing a single GPU in a Docker Compose environment
- **Constraints**: Single card with 48 GB (RTX 5880), 11 GPU services; JAX initialization requires the device to be visible, otherwise it errors out instead of degrading gracefully
- **Not applicable**:
  - Multi-card environments (each card can host different services)
  - CPU-only inference services
  - GPUs partitioned with MIG (extra configuration required)
  - Production deployments where a single service owns the GPU

## Audit Record

- **Validation method**: iGEM-silk full Docker Compose startup validation
- **Test cases**:
  1. Start 3+ GPU services simultaneously → BepiPred3 reports `CUDA error: out of memory`
  2. AF3 coexisting with other GPU services → AF3 reports `Unable to initialize backend 'cuda'`
  3. Start one at a time + confirm with `nvidia-smi` → enough memory, prediction succeeds
- **Success rate**: 100% (OOM is predictably avoided when following the strategy)
- **Limitations**: Does not cover how to configure MIG partitioning; does not cover concrete `CUDA_VISIBLE_DEVICES` examples

## Usage

- **Trigger conditions**: Encountering CUDA OOM or JAX initialization failures when starting GPU services in Docker Compose
- **How to invoke**:
  1. `nvidia-smi` to check current memory usage
  2. `docker compose stop <other-gpu-services>` to free memory
  3. `docker compose --profile gpu up -d <target-service>` to start the target service
  4. `nvidia-smi` again to confirm enough memory
  5. Submit the prediction request
- **Caveats**:
  - A passing health check does not mean predictions will succeed — the health check does not allocate GPU memory
  - Testing one at a time is not the same as `docker compose up` one at a time — switch with stop/start rather than bringing everything up
  - JAX's CUDA initialization happens at container startup, not at model load
