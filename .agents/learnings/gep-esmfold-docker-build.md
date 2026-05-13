---
name: ESMFold Docker 三层构建模式 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [esmfold, docker, buildkit, cuda, dockerfile]
validated: true
---

# Gene Capsule: ESMFold Docker 三层构建模式

## Experience

**问题类型**: ESMFold 微服务 Docker 镜像构建——在 CUDA 12.1 + Python 3.10 环境下优化构建速度和缓存复用。

**核心策略**:
1. 三层 Dockerfile 结构，按变更频率分离：apt+torch（几乎不变）→ openfold CUDA 编译（~12min，少变）→ pip 依赖（常变）
2. base image 用 `nvidia/cuda:12.1.0-devel-ubuntu22.04`（devel 标签含 nvcc，runtime 标签不含，openfold CUDA 编译需要 nvcc）
3. numpy 版本必须在 Layer 1 与 torch 一起 pin（`numpy<2`），不要在 Layer 3 里加——deepspeed 在 import 时加载 numpy，装晚了会炸
4. 永远不合并 Layer 2 和 Layer 3——openfold 编译是主要耗时，pip 依赖经常改，合并后每次改依赖都要重编 openfold
5. 构建体积预期 ~12.7GB，做好心理准备

**关键参数**:

| 层 | 内容 | 变更频率 | 构建时间 |
|---|---|---|---|
| Layer 1 | apt (python3.10, build-essential, ninja, git) + pip install torch + `numpy<2` | 极低 | ~2min |
| Layer 2 | pip install openfold v2.2.0 from GitHub (CUDA 编译) | 低 | ~12min |
| Layer 3 | pip install (biotite, deepspeed≥0.9, fastapi≥0.100, fair-esm==2.0.0) | 高 | ~1min |

构建命令: `docker build -f tools/ESMFold/Dockerfile -t igem-silk/esmfold:latest .`

## Environment Fingerprint

- **任务域**: Python Docker 微服务构建，GPU/CUDA 环境，蛋白质结构预测
- **输入特征**: 多层 Dockerfile，包含 CUDA 编译步骤（openfold），依赖链长
- **约束条件**: CUDA 12.1 + Python 3.10 + Ubuntu 22.04 基础镜像；必须用 devel 标签（含 nvcc）；镜像大小 ~12.7GB
- **不适用**:
  - CPU-only 环境（ESMFold 强制 GPU）
  - 用 `docker compose build` 时缓存行为不一致，直接用 `docker build -f Dockerfile`
  - Python 3.11+（openfold 有 `not` 参数名冲突）
  - 需要小镜像的场景（基础镜像 ~3GB，openfold 编译产物 ~5GB）
  - 使用 `nvidia/cuda:runtime` 标签（缺少 nvcc）
- **注意**: `docker compose build` 的缓存行为可能和 `docker build` 不一致。CI 中建议直接用 `docker build -f Dockerfile .`

## Audit Record

- **验证方式**: Docker 构建 + 容器内启动 + 结构预测验证
- **测试用例**:
  1. 构建: `docker build -f tools/ESMFold/Dockerfile -t igem-silk/esmfold:latest .` → 成功 (12.7GB)
  2. 启动: `docker run --gpus all igem-silk/esmfold:latest` → uvicorn 启动, 模型 75s 加载完毕
  3. 预测: 6 残基肽 YDFYTP → 2.3s 返回 PDB, `confidence=0.556`
- **成功率**: 100% (3/3 验证通过)
- **局限性**: 首次构建需 ~15min（openfold CUDA 编译占 12min）；镜像 ~12.7GB；不适合 CI 高频触发

## Usage

- **触发条件**: 任何 ESMFold 相关微服务的 Dockerfile 修改、依赖版本变更、基础镜像升级
- **调用方式**: 参考 `tools/ESMFold/Dockerfile` 的三层结构
- **注意事项**:
  - 升级 CUDA 版本时同步更新 PyTorch wheel URL（`--index-url https://download.pytorch.org/whl/cu121`）
  - openfold 版本变更时要同步检查 fair-esm 兼容性（见 gep-esmfold-dependency-matrix.md）
  - 模型权重通过 volume 挂载 `tools/models/`，不 baked 进镜像
  - 如果 `docker compose build` 行为异常，回退到 `docker build -f Dockerfile .` 直接构建
