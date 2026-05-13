---
name: Docker Hub 国内不可达
description: registry-1.docker.io 在中国大陆大部分网络环境不可达，必须配置镜像加速器
created: 2026-05-13
version: 1.0.0
tags: [docker, china, network, registry-mirror, iGEM-silk]
validated: true
---

# Docker Hub 国内不可达

## Experience

- **问题类型**: 网络不可达导致 Docker 镜像拉取失败
- **核心策略**: 配置 Docker Hub 镜像加速器
- **关键参数**: registry-mirrors 配置

`registry-1.docker.io` 在中国大陆大部分网络环境不可达。`docker pull`、`docker compose build`（拉取基础镜像）均会超时。

### 配置

```json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```

写入 `/etc/docker/daemon.json` 并重启 Docker：

```bash
sudo systemctl restart docker
```

### 注意

修改 daemon.json 需要 sudo 权限，应在部署前告知用户准备。

## Environment Fingerprint

- **任务域**: Docker 镜像拉取
- **输入特征**: 位于中国大陆网络环境
- **约束条件**: 需要 sudo 权限修改 daemon.json
- **不适用**: 海外网络环境或已配置其他代理/VPN

## Audit Record

- **验证方式**: iGEM-silk 15 个服务全量构建，DaoCloud 镜像加速器可用
- **失败案例**: 未配置镜像加速器时 `docker compose build` 全部因 `registry-1.docker.io` 不可达而超时
- **修复验证**: 配置后 `docker pull python:3.11-slim` 成功

## Usage

- **触发条件**: `docker pull` 或 `docker compose build` 报 `dial tcp: connect: connection timed out` 到 `registry-1.docker.io`
- **调用方式**: 写入 daemon.json → 重启 Docker → 重试拉取
- **注意事项**: 镜像加速器可能有延迟，最新 tag 可能未同步
