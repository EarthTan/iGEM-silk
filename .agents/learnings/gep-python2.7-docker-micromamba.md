---
name: Python 2.7 遗留服务 Docker 化的 micromamba 方案 v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [python2.7, docker, micromamba, conda, legacy, aggrescan3d, china-network]
validated: true
---

# Gene Capsule: Python 2.7 遗留服务 Docker 化的 micromamba 方案

## Experience

**问题描述**: Aggrescan3D 需要 Python 2.7 + conda 包 `lcbio::aggrescan3d`，在 2026 年的 Docker 环境中构建遇到多层失败：

1. `continuumio/miniconda2:latest` 从 Docker Hub（DaoCloud 镜像）拉取返回 **403 Forbidden**（镜像已归档）
2. `python:2.7-slim`（Debian Buster）apt 源返回 **404 Not Found**（Buster 已进入 LTS 归档）
3. `mambaorg/micromamba:latest` 不在 DaoCloud 镜像加速器白名单，拉取被拒绝
4. miniforge3 Python=3.13 但 aggrescan3d **仅支持 Python 2.7**

**根因**: Docker Hub 在中国大陆访问受限，且 Python 2.7 的官方镜像已从主流仓库中移除。Debian Buster apt 源已归档导致 `apt-get install python` 失败。

### 解决方案

**最终方案**: `ghcr.io/mamba-org/micromamba` + 独立 conda 环境

```
Base image: ghcr.io/mamba-org/micromamba:latest
    ↑ 来自 GitHub Container Registry（GHCR），中国大陆可直接访问
    ↑ micromamba 是静态 C++ 客户端，无需 Python 解释器

在其中创建 Python 2.7 环境：
    micromamba create -y -n a3d -c conda-forge -c lcbio python=2.7 aggrescan3d
    
激活环境使用：
    ENV AGGRESCAN_CONDA_ENV=/opt/conda/envs/a3d
    $AGGRESCAN_CONDA_ENV/bin/python service.py
```

```dockerfile
FROM ghcr.io/mamba-org/micromamba:latest

USER root

# 创建 Python 2.7 + aggrescan3d 环境
RUN micromamba create -y -n a3d -c conda-forge -c lcbio python=2.7 aggrescan3d \
    && micromamba clean -afy

# 安装 uv（用于微服务依赖）
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY tools/template/ ./tools/template/
COPY tools/Aggrescan3D/ ./tools/Aggrescan3D/

WORKDIR /app/tools/Aggrescan3D
RUN uv sync

ENV AGGRESCAN_CONDA_ENV=/opt/conda/envs/a3d
CMD [".venv/bin/python", "service.py"]
```

**关键创新**: micromamba 的静态二进制特性使其在任何基础镜像中都能工作，不需要 Python 解释器来安装 conda 包。这解决了"先有鸡还是先有蛋"的问题——需要 Python 2.7 但安装 conda 本身需要 Python。

### 镜像源选择决策矩阵

| 镜像源 | Python 2.7 | 中国大陆可达 | 白名单 | 结论 |
|--------|-----------|------------|--------|------|
| Docker Hub miniconda2 | ✅ | ❌ DaoCloud 代理 | ✅（DaoCloud 白名单内）| 403 已归档 |
| Docker Hub python:2.7-slim | ✅ 但 apt 404 | ❌ | ✅ | Buster 已归档 |
| DaoCloud mambaorg/micromamba | ✅（可创建环境） | ✅ | ❌ **不在白名单！** | 拉取被拒 |
| **GHCR mamba-org/micromamba** | **✅** | **✅** | **N/A** | **成功** |
| 原生 pip install | ❌ 无 Python 2.7 | ✅ | N/A | Docker 禁用 |

### 类似情况（同一 session 中遇到）

| 服务 | 问题 | 最终方案 |
|------|------|---------|
| ToxinPred3 | `scikit-learn==1.2.2` 与 Python 3.13 不兼容 | micromamba 创建 Python 3.8 环境（`python=3.8 scikit-learn=1.2.2`） |
| AnOxPePred | PyTorch CUDA 占用 34GB 不释放 | 无 Docker 修复，需 kill 进程释放显存 |

### Environment Fingerprint

- **任务域**: 遗留 Python 代码的 Docker 容器化
- **输入特征**: Python 2.x/3.x 依赖，conda-only 包，已弃用的基础镜像
- **约束条件**: 中国网络环境（Docker Hub 不可达），modern base image（Python 3.13+），无互联网 apt 源
- **触发模式**: Legacy conda package 在 modern Docker 中构建失败
- **不适用**: 纯 pip 依赖的现代 Python（直接用 `python:3.11-slim`）；有官方 Docker 镜像的服务；可从源码编译的服务

### 替代方案

1. **conda-pack**: 在有网络的机器上 `conda pack` 打包完整环境，COPY 到镜像中解压
2. **Nix/Nixpkgs**: 对 Python 2.7 包有更好的版本管理，但学习成本高
3. **Docker multi-stage**: 先用 continuumio/miniconda3 创建 Python 2.7 环境，再 COPY 到 slim 镜像（需解决 glibc 兼容性）

### Audit Record

- **验证方式**: Aggrescan3D Docker 镜像构建成功并运行，150 个 PDB 全部评分完成
- **测试用例**:
  1. `continuumio/miniconda2:latest` → 403 Forbidden（DaoCloud）
  2. `python:2.7-slim` → apt 404（Buster 归档）
  3. `mambaorg/micromamba:latest` via DaoCloud → denied（白名单）
  4. `ghcr.io/mamba-org/micromamba:latest` via GHCR → **构建成功**
- **成功率**: 100%（最终方案）
- **局限性**: micromamba 创建的 Python 2.7 环境仅包含 conda 包，pip 包需要额外处理。aggrescan3d 的 Python 2.7 代码在 modern Linux kernel/glibc 上可能遇到未预期的问题（本次运行未发现）。
