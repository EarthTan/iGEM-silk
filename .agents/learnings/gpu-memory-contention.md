---
name: GPU 显存争用
description: 多个 GPU 微服务同时运行时，48GB RTX 5880 显存会被耗尽，导致 CUDA OOM 和 JAX 初始化失败
type: reference
---

# GPU 显存争用

## 问题

该项目的 15 个微服务中有 11 个使用 GPU。当通过 Docker Compose 同时启动所有服务时，GPU 显存（48GB）被多个大模型共享，很快耗尽。

## 显存占用参考

| 服务 | 模型 | 近似显存 |
|------|------|----------|
| BepiPred3 | ESM-2 t33 | ~6 GB |
| pLM4CPPs | ESM-2 t6 | ~2.5 GB |
| HemoPI2 | ESM-2 t6 | ~2.5 GB |
| MHCflurry | Ensemble | ~2 GB |
| TemStaPro | ProtT5-XL | ~11 GB |
| GraphCPP | GraphSAGE-GNN | ~1 GB |
| AnOxPePred | CNN | ~1 GB |
| AlphaFold3 (6aa) | JAX | ~46 GB |
| AlphaFold3 (346aa) | JAX | ~46 GB |

AF3 本身几乎占满全部 48GB，无法和其他 GPU 服务共存。

## 症状

- **BepiPred3**: `CUDA error: out of memory` — ESM-2 模型加载时分配失败
- **AlphaFold3**: `Unable to initialize backend 'cuda': INTERNAL: no supported devices found for platform CUDA` — AF3 Docker 容器内 JAX 初始化时找不到 CUDA 设备，因为显存已被占满
- 即使 health check 通过（只检查环境，不分配显存），预测时仍可能失败

## 如何测试 GPU 服务

- **不要同时启动所有 GPU 服务**。逐个测试，或者只启动需要的服务
- 测试 AF3 之前确保其他 GPU 服务都已停止（`docker compose stop <service>`）
- 用 `nvidia-smi` 确认显存使用量后再提交预测
- 用 `docker compose --profile gpu up -d <service>` 启动单个服务

## 如何避免

- 生产环境中应考虑：GPU 服务独占 GPU，不要让多个大模型服务共享
- 如果必须共享，可以使用 `CUDA_VISIBLE_DEVICES` 或 MIG（Multi-Instance GPU）做显存隔离
- AF3 这种需要全卡的服务，应该单独部署或调度
