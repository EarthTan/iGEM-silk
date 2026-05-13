---
name: docker-compose dockerfile 路径一致性 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, docker-compose, build-context, path-resolution, iGEM-silk]
validated: true
---

# Gene Capsule: docker-compose dockerfile 路径一致性

## Experience

**问题类型**: Docker Compose 中 `dockerfile` 路径相对于 `context` 而非 compose 文件位置，导致找不到 Dockerfile。

**核心策略**: `dockerfile` 路径相对于 `context`。当 `context: ..` 而 Dockerfile 在 `tools/<name>/` 下时，必须写 `dockerfile: tools/<name>/Dockerfile`。

**关键参数**: `context` 和 `dockerfile` 的相对关系

### 错误模式

```yaml
# tools/docker-compose.yml
services:
  anoxpepred:
    build:
      context: ..
      dockerfile: Dockerfile    # ❌ 相对于 context (项目根)，实际在 tools/AnOxPePred/Dockerfile
```

### 正确模式

```yaml
services:
  anoxpepred:
    build:
      context: ..
      dockerfile: tools/AnOxPePred/Dockerfile
```

### 批量校验

```bash
grep 'dockerfile:' docker-compose.yml
# 逐一与 ls tools/*/Dockerfile 比对
```

## Environment Fingerprint

- **任务域**: Docker 多服务项目构建
- **输入特征**: docker-compose.yml 中 `context` 与 `dockerfile` 不在同一目录
- **约束条件**: 首次配置或新增服务时最容易出错
- **不适用**: `context` 和 `dockerfile` 在同一目录的简单场景

## Audit Record

- **验证方式**: iGEM-silk 15 个服务全量 docker compose build 验证
- **失败案例**: 多个服务的 dockerfile 路径指向项目根目录而非 `tools/<name>/` 子目录，导致 `docker compose build` 找不到 Dockerfile
- **修复验证**: 全量 `grep` + `ls` 比对后修复，再次 build 通过

## Usage

- **触发条件**: 新增微服务、修改 docker-compose.yml 的 build 配置
- **调用方式**: 首次配置后立即用脚本比对所有 dockerfile 路径
- **注意事项**: 不要凭记忆逐个修复——一次性全量 grep 扫描效率远高于等待 CI 逐个报错
