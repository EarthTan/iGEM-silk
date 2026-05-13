---
name: GPU 显存争用排查与避免 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [gpu, memory, cuda, docker, oom, troubleshooting]
validated: true
---

# Gene Capsule: GPU 显存争用排查与避免

## Experience

**问题类型**: 多个 GPU 微服务通过 Docker Compose 同时启动时，单卡 48GB 显存被多个大模型耗尽，导致 CUDA OOM 和 JAX 初始化失败。

**核心策略**:
1. **逐个测试 GPU 服务** — 不同时启动所有 GPU 服务，每次只测试需要的那个。用 `docker compose --profile gpu up -d <service>` 启动单个服务
2. **测试 AF3 前释放显存** — AlphaFold3 (JAX) 几乎占满全部 48GB，无法与其他 GPU 服务共存。在启动 AF3 之前 `docker compose stop <service>` 停掉其他 GPU 服务
3. **用 `nvidia-smi` 确认显存** — 在提交预测前先 `nvidia-smi` 查看显存使用量，确认有足够空闲
4. **显存隔离（生产环境）** — 生产环境中 GPU 服务应独占 GPU，或用 `CUDA_VISIBLE_DEVICES` 或 MIG（Multi-Instance GPU）做显存隔离

**关键参数**:

| 服务 | 模型 | 近似显存 |
|------|------|----------|
| BepiPred3 | ESM-2 t33 | ~6 GB |
| pLM4CPPs | ESM-2 t6 | ~2.5 GB |
| HemoPI2 | ESM-2 t6 | ~2.5 GB |
| MHCflurry | Ensemble | ~2 GB |
| TemStaPro | ProtT5-XL | ~11 GB |
| GraphCPP | GraphSAGE-GNN | ~1 GB |
| AnOxPePred | CNN | ~1 GB |
| AlphaFold3 | JAX | ~46 GB |

AF3 本身几乎占满全部 48GB，无法和其他 GPU 服务共存。

**典型症状**:
- `CUDA error: out of memory` — ESM-2 模型加载时分配失败
- `Unable to initialize backend 'cuda': INTERNAL: no supported devices found` — JAX 初始化时找不到 CUDA 设备，因为显存已被占满
- health check 通过但预测失败 — health check 只检查环境，不分配显存

## Environment Fingerprint

- **任务域**: GPU 微服务 Docker 部署，蛋白质结构预测/ML 推理
- **输入特征**: 多个大模型（1-46 GB 不等）共享单张 GPU 的 Docker Compose 环境
- **约束条件**: 单卡 48 GB（RTX 5880），11 个 GPU 服务；JAX 初始化时要求设备可见，否则直接报错而非优雅降级
- **不适用**:
  - 多卡环境（每张卡可分配不同服务）
  - CPU-only 推理的服务
  - 使用 MIG 切分后的 GPU（需额外配置）
  - 单服务独占 GPU 的生产部署

## Audit Record

- **验证方式**: iGEM-silk 全量 Docker Compose 启动验证
- **测试用例**:
  1. 同时启动 3+ 个 GPU 服务 → BepiPred3 报 `CUDA error: out of memory`
  2. AF3 与其他 GPU 服务共存 → AF3 报 `Unable to initialize backend 'cuda'`
  3. 逐个启动 + `nvidia-smi` 确认 → 显存足够，预测成功
- **成功率**: 100%（按策略操作后可预测地避免 OOM）
- **局限性**: 未覆盖 MIG 切分的配置方法；未覆盖 `CUDA_VISIBLE_DEVICES` 的具体示例

## Usage

- **触发条件**: 在 Docker Compose 中启动 GPU 服务时遇到 CUDA OOM 或 JAX 初始化失败
- **调用方式**:
  1. `nvidia-smi` 查看当前显存占用
  2. `docker compose stop <other-gpu-services>` 释放显存
  3. `docker compose --profile gpu up -d <target-service>` 启动目标服务
  4. 再次 `nvidia-smi` 确认显存足够
  5. 提交预测请求
- **注意事项**:
  - health check 通过不代表预测能成功——health check 不分配显存
  - 逐个测试不等于逐个 `docker compose up`——用 stop/start 切换而非全部 up
  - JAX 的 CUDA 初始化在容器启动时发生，不是模型加载时
