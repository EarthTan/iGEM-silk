---
name: Docker-outside-Docker 路径解析 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, docker-socket, volume-mount, path-resolution, iGEM-silk]
validated: true
---

# Gene Capsule: Docker-outside-Docker 路径解析

## Experience

**问题类型**: Docker socket 嵌套调用时的路径解析错误——`docker run --volume` 的源路径由宿主机 Docker 守护进程解析，而非 API 容器内部路径。

**核心策略**: 区分"容器内路径"（health check 用）和"宿主机路径"（Docker socket `--volume` 用），通过独立环境变量分别传递。

**关键参数**: `AF3_MODEL_DIR`（容器内）、`AF3_MODEL_HOST_DIR`（宿主机绝对路径）

当 API 容器通过挂载 `/var/run/docker.sock` 调用宿主机 Docker 守护进程运行其他容器时，`docker run --volume` 的源路径由**宿主机 Docker 守护进程**解析，不是 API 容器内部路径。

### 错误模式

```yaml
# docker-compose.yml
environment:
  - AF3_MODEL_DIR=/root/models           # ❌ 传给 service.py 当作 --volume 源路径
volumes:
  - /home/lenovo/af_models:/root/models
```

```python
# service.py
cmd = ["docker", "run", "--volume", f"{self._model_dir}:/root/models", ...]
# self._model_dir = "/root/models" → 宿主机上不存在此路径
```

### 正确模式

```yaml
environment:
  - AF3_MODEL_DIR=/root/models                    # 容器内路径（health check 用）
  - AF3_MODEL_HOST_DIR=${AF3_MODEL_DIR}            # 宿主机路径（Docker socket 用）
volumes:
  - ${AF3_MODEL_DIR:-/tmp/af3_models}:/root/models
```

```python
self._model_host_dir = os.environ.get("AF3_MODEL_HOST_DIR", self._model_dir)
cmd = ["docker", "run", "--volume", f"{self._model_host_dir}:/root/models", ...]
```

## Environment Fingerprint

- **任务域**: Docker 容器化部署
- **输入特征**: 使用 `docker.sock` 挂载 + `docker run --volume` 的服务
- **约束条件**: Docker-outside-of-Docker 架构
- **适用场景**:
  - `tools/AlphaFold3/` — 挂载模型参数和数据库目录
  - `tools/PEP-FOLD4/` — 挂载 workspace 目录
  - `tools/Aggrescan3D/` — 挂载 workspace 目录
- **不适用**: 纯容器内路径操作、不涉及 docker.sock 的服务

## Audit Record

- **验证方式**: AlphaFold3 服务在 Ubuntu 部署环境下通过健康检查 + 实际预测任务验证
- **已知局限**: `/health` 端点只验证容器内路径存在（docker-compose volume mount 会创建挂载点），但**不验证 Docker socket 路径在宿主机上是否可解析**。健康检查通过不代表预测能跑通
- **排查链路**: 宿主机真实路径 → docker-compose volumes 映射 → 环境变量传递 → service.py 使用 → 宿主机路径存在性

## Usage

- **触发条件**: 服务通过 docker.sock 运行子容器且需要 volume 挂载
- **调用方式**: 在 docker-compose.yml 中同时设置容器内路径和宿主机路径两个环境变量
- **注意事项**: 不要假设容器内路径和宿主机路径相同；健康检查通过不等于路径正确
