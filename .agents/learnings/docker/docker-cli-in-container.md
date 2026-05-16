---
name: 容器内 Docker CLI 安装 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, docker-socket, dind, docker-cli, iGEM-silk]
validated: true
---

# Gene Capsule: 容器内 Docker CLI 安装

## Experience

**问题类型**: 容器内需要 `docker` 命令行工具来调用宿主机 Docker 守护进程。

**核心策略**: 优先挂载宿主机 `/usr/bin/docker`，避免在容器内安装任何 Docker 包。

**关键参数**: docker.sock 挂载 + docker 二进制挂载

PEP-FOLD4、AlphaFold3、Aggrescan3D 需要在容器内运行 `docker` 命令访问宿主机 Docker 守护进程。

### 方案一（不推荐）：容器内安装

```dockerfile
# ❌ 增加镜像体积，且容器内 docker 版本可能与宿主机不匹配
RUN apt-get update && apt-get install -y docker.io
```

### 方案二（推荐）：挂载宿主机二进制

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - /usr/bin/docker:/usr/bin/docker
```

避免在容器内安装任何 Docker 包——减小镜像体积，消除网络依赖。

## Environment Fingerprint

- **任务域**: Docker-outside-of-Docker 架构
- **输入特征**: 服务需要执行 `docker run` 等命令
- **约束条件**: 宿主机已安装 Docker
- **不适用**: 不需要调用宿主机 Docker 的普通服务

## Audit Record

- **验证方式**: iGEM-silk PEP-FOLD4 / AlphaFold3 / Aggrescan3D 三个服务验证
- **失败案例**: Debian 源安装的 `docker.io` 包与宿主机 Docker 版本不兼容
- **修复验证**: 改为挂载宿主机 `/usr/bin/docker` 后命令正常执行

## Usage

- **触发条件**: 服务需要调用宿主机 Docker 守护进程
- **调用方式**: docker-compose.yml 中同时挂载 `docker.sock` 和 `/usr/bin/docker`
- **注意事项**: 宿主机 Docker 版本更新后容器内自动同步（因为是挂载）
