---
name: Docker 不可达时回退到宿主机原生执行 v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [docker, hybrid, china-network, conda, native, fallback]
validated: true
---

# Gene Capsule: Docker 不可达时回退到宿主机原生执行

## Experience

**问题类型**: 中国大陆网络环境下 Docker Hub 不可达导致某些微服务（Aggrescan3D）Docker 镜像无法构建，需要切换为宿主机原生 conda 环境直接调用。

**核心策略**:
1. **优先检查本地是否有替代运行方式**：Aggrescan3D 提供 conda 包（`conda install -c lcbio aggrescan3d`），可直接在宿主机安装运行
2. **环境变量驱动切换**：`AGGRESCAN_CONDA_ENV` 控制 conda env 路径，无需改代码即可从 Docker 切换到原生
3. **原生执行常常更快**：Aggrescan3D 原生 conda 环境下 ~4s/PDB，Docker-in-Docker 模式（挂载 docker.sock 启动临时容器）因嵌套开销更慢
4. **微服务封装不变**：即使是原生调用，也通过 FastAPI 微服务暴露相同接口，调用方完全感知不到底层差异

**关键参数**:

| 部署模式 | 优点 | 缺点 |
|----------|------|------|
| Docker-in-Docker | 环境完全隔离，可复现 | 镜像拉取依赖网络；嵌套 Docker 有性能开销 |
| 宿主机 conda 原生 | 无网络依赖；速度快 | 环境与宿主机耦合；需要预装依赖 |

**环境变量接口**:
```
AGGRESCAN_CONDA_ENV=/path/to/conda/env    # conda 环境路径
A3D_KEEP_WORKSPACE=1                       # 保留临时文件调试
A3D_WORKSPACE=/tmp/a3d_workspace           # 工作目录
A3D_TIMEOUT=900                            # 超时秒数
```

## Environment Fingerprint

- **任务域**: Docker 微服务部署到中国大陆服务器，网络受限环境
- **输入特征**: Dockerfile 使用 `FROM continuumio/miniconda2` 或类似从 Docker Hub 拉取基础镜像的服务
- **约束条件**: `registry-1.docker.io` 不可达；无 VPN/代理；基础镜像 > 100MB（无法通过小文件传输绕过）
- **不适用**:
  - 需要 GPU 的原生调用（conda 环境可能有 CUDA 版本冲突）
  - 服务有复杂系统依赖（apt 包、系统库）
  - 需要完全环境隔离的生产部署

## Audit Record

- **验证方式**: iGEM-silk Aggrescan3D 服务验证
- **测试用例**:
  1. Docker 构建 → `docker pull continuumio/miniconda2` 超时 → 构建失败
  2. 宿主机 conda 安装 → `conda install -c lcbio aggrescan3d` → 成功 (Python 2.7 环境)
  3. 原生运行 `main/stages/stage06_pdb_eval.py` → 90 PDB 全部成功，共耗时 ~360s (~4s/PDB)
  4. 通过 `AGGRESCAN_CONDA_ENV` 切换不同环境 → 无需改代码
- **成功率**: 100% (90/90 PDB 评分成功)
- **局限性**: conda 安装的 Aggrescan3D 依赖 Python 2.7，可能与其他服务产生环境冲突；某些工具只有 Docker 版本没有 conda 版本

## Usage

- **触发条件**: `docker compose build` 或 `docker pull` 因网络问题失败，或 Docker-in-Docker 性能不满足需求
- **调用方式**:
  1. 检查工具是否有 conda/pip/npm 等原生安装方式
  2. 确认原生环境的依赖兼容性（Python 版本、CUDA 版本、系统库）
  3. 在 service.py 中添加环境变量控制运行模式（conda env path / binary path）
  4. 所有路径参数化，方便切换而不改代码
  5. 微服务接口不变，调用方无感知
- **注意事项**: 混合模式需要宿主机预装环境，不适合自动化 CI/CD；conda 环境的 Python 版本可能与项目主环境不同，需要 `conda create -n <env> python=2.7` 隔离
