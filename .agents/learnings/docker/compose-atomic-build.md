---
name: Docker Compose 构建原子性缺陷
description: docker compose --build 在构建多个服务时一荣俱荣一损俱损——任一失败则全部取消；应分批构建或单独构建
created: 2026-05-13
version: 1.0.0
tags: [docker, docker-compose, build-strategy, atomicity, iGEM-silk]
validated: true
---

# Docker Compose 构建原子性缺陷

## Experience

- **问题类型**: Docker Compose 批量构建失败回滚
- **核心策略**: 分批次构建——按 profile 分组或单独构建失败的服务
- **关键参数**: `--profile` 分组、`docker compose build <service>`

`docker compose --profile gpu --profile cpu up -d --build` 在构建 15 个服务时，任意一个失败则**全部取消**。前面 10 个可能已构建成功，但因最后一个失败全部浪费。

### 错误模式

```bash
# ❌ 15 个服务一起构建，一个失败全军覆没
docker compose --profile gpu --profile cpu up -d --build
```

### 正确模式

```bash
# 分批次构建
docker compose --profile cpu build    # 先 CPU 服务
docker compose --profile gpu build    # 再 GPU 服务
docker compose --profile gpu --profile cpu up -d   # 最后启动全部
```

或单独构建失败的服务：

```bash
docker compose build anoxpepred bepipred3 toxinpred3
```

## Environment Fingerprint

- **任务域**: 多服务 Docker Compose 项目
- **输入特征**: 服务数量 ≥ 5，存在已知可能构建失败的服务
- **约束条件**: 使用 `--build` + `up` 组合命令
- **不适用**: 所有服务构建均稳定通过的项目

## Audit Record

- **验证方式**: iGEM-silk 全量构建中因一个服务失败导致之前成功的 10+ 个服务构建结果作废
- **失败案例**: `docker compose --profile gpu --profile cpu up -d --build` 在 15 个服务时触发原子性回滚
- **修复验证**: 分批构建后各自独立，互不影响

## Usage

- **触发条件**: 多服务项目中存在不稳定构建的服务
- **调用方式**: 先用 `docker compose --profile xxx build` 分批构建，全部通过后再 `up -d`
- **注意事项**: 分批不会改变服务间的网络依赖——`up -d` 阶段服务仍可互相访问
