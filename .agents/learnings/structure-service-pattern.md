---
name: 结构预测微服务 Docker 与模型模式 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, cuda, pytorch, structure-prediction, microservice, esmfold, omegafold]
validated: true
---

# Gene Capsule: 结构预测微服务 Docker 与模型模式

## Experience

**问题类型**: 为原生 Python 蛋白质结构预测微服务（ESMFold / OmegaFold 等）配置 Docker 镜像、CUDA 环境、模型缓存和 Python 包管理的一系列标准化决策。

**核心策略**（一组相关的最佳实践）:

1. **Docker 基础镜像选型**: GPU 结构预测服务统一用 `nvidia/cuda:12.1.0-runtime-ubuntu22.04`，同时安装 `curl` 用于 health check。需要 nvcc 编译的服务（如 openfold）改用 `devel` 标签
2. **PyTorch CUDA wheel**: 始终指定 `--index-url https://download.pytorch.org/whl/cu121`（或匹配的 CUDA 版本），否则 pip 会安装 CPU-only 的 torch
3. **pip 解释器路径**: 在多 Python 版本 Docker 镜像中，用 `python3.11 -m pip install` 而非 `pip install`，避免解释器版本不匹配
4. **`torch.cuda.empty_cache()` 守卫**: 始终用 `if torch.cuda.is_available():` 包裹，否则在 CPU/MPS 环境下崩溃
5. **pLDDT 置信度归一化**: ESMFold 原始 b_factor 范围 0-100，但 `StructureResult.confidence` 约束是 `le=1.0`，必须除以 100
6. **pyproject.toml 包名遮蔽**: 包名不能和上游 pip 包名相同（如 "omegafold" → "omegafold-service"），否则 `pip install` 上游包会静默失败
7. **共享模型缓存**: 通过 `TORCH_HOME` 指向 `tools/models/fair-esm/`，跨服务复用（ESMFold、BepiPred、pLM4CPPs）。Docker volume 挂载
8. **OmegaFold 缓存环境变量**: `OMEGAFOLD_CACHE` 默认 `~/.cache/omegafold_ckpt/`，Docker 内设为 `/app/tools/models/omegafold`
9. **异步任务端点**: `StructureService` 模板支持 `enable_async=True` 启用异步 job 端点。使用前确认本地/目标分支是否包含此特性

**关键参数**:
- 基础镜像: `nvidia/cuda:12.1.0-runtime-ubuntu22.04`（runtime）/ `nvidia/cuda:12.1.0-devel-ubuntu22.04`（devel，含 nvcc）
- Torch index: `https://download.pytorch.org/whl/cu121`
- 模型缓存: `TORCH_HOME` → `tools/models/fair-esm/`（volume 挂载）
- pLDDT 归一化: `b_factor / 100.0` → confidence

## Environment Fingerprint

- **任务域**: 蛋白质结构预测微服务的 Docker 容器化 + GPU 部署
- **输入特征**: 使用 `StructureService` 模板的 Python 微服务，依赖 PyTorch CUDA + 蛋白质大模型
- **约束条件**: CUDA 12.1；多 Python 版本共存于同一镜像；服务间共享模型缓存；包名可能和 pip 上游冲突
- **不适用**:
  - CPU-only 推理的服务（不需要 CUDA 相关配置）
  - FASTA 评分类服务（`FastaToolService` 模板，不同模式）
  - Docker-in-Docker 服务（如 AF3、PEP-FOLD4 有自身的 DinD 模式）

## Audit Record

- **验证方式**: iGEM-silk ESMFold、OmegaFold、BepiPred-3.0 等服务的 Docker 构建 + 运行验证
- **测试用例**:
  1. `nvidia/cuda:runtime` 构建 ESMFold → uvicorn 启动 + 模型加载 + 结构预测 OK
  2. `omegafold` 包名冲突未修复时 `pip install omegafold` → 本地包遮蔽上游 → 修复为 `omegafold-service` 后 OK
  3. 未归一化的 pLDDT 分数被 `pydantic` 校验拦截 → 除以 100 后通过
- **成功率**: 100%（所有结构预测服务均采用此模式并稳定运行）
- **局限性**: 不覆盖 Docker-in-DinD 服务的特殊配置；CUDA 版本升级时需要同步更新 --index-url；`enable_async` 的可用性取决于分支版本

## Usage

- **触发条件**: 新增结构预测微服务（ESMFold、OmegaFold 等使用 `StructureService` 模板的服务）
- **调用方式**: 参考已有 Dockerfile（如 `tools/ESMFold/Dockerfile`）复制模式；设置对应的环境变量和 volume 挂载
- **注意事项**:
  - 多 Python 版本混合时务必用 `python3.11 -m pip` 而非 `pip`
  - `pyproject.toml` 的 `[project] name` 使用 `-service` 后缀避免包名冲突
  - `curl` 必须安装（health check 依赖）——slim 镜像默认不含 curl
  - 共享模型缓存目录必须在所有服务中保持一致，通过 Docker Compose volume 挂载
