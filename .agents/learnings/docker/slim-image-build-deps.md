---
name: slim 镜像缺少 C 扩展编译依赖
description: python:slim 镜像不含 C 扩展编译所需的头文件和工具链，pip install 含原生扩展的包时失败
created: 2026-05-13
version: 1.0.0
tags: [docker, slim-image, build-deps, c-extensions, pip, iGEM-silk]
validated: true
---

# slim 镜像缺少 C 扩展编译依赖

## Experience

- **问题类型**: slim 基础镜像缺少编译工具链
- **核心策略**: 所有 slim 镜像 Dockerfile 中如涉及 pip 安装原生扩展，标准配置应包括编译依赖
- **关键参数**: `gcc`, `python3-dev`, `pkg-config`

`python:3.11-slim` 不含 C 扩展编译所需的头文件和工具链。`pip install freesasa` 需要 `python3-dev` 和 `pkg-config`。

### 错误模式

```dockerfile
FROM python:3.11-slim
RUN pip install freesasa    # ❌ 缺少编译依赖，报 fatal error: Python.h: No such file or directory
```

### 标准配置

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev pkg-config libxml2-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install freesasa    # ✅ 编译通过
```

## Environment Fingerprint

- **任务域**: Python Docker 镜像构建
- **输入特征**: 使用 `python:slim` 基础镜像 + pip 安装含 C 扩展的包
- **约束条件**: pip 包依赖原生 C 扩展（如 FreeSASA、numpy 从源码构建等）
- **不适用**: 纯 Python 包、使用 wheel 安装、或使用完整 `python:3.11` 镜像

## Audit Record

- **验证方式**: iGEM-silk SASA 服务 Docker 构建失败
- **失败案例**: `pip install freesasa` → `fatal error: Python.h: No such file or directory`
- **修复验证**: 添加 `gcc python3-dev pkg-config` 后编译通过

## Usage

- **触发条件**: pip install 报 `fatal error: Python.h: No such file or directory` 或 `error: command 'gcc' failed`
- **调用方式**: 在 `pip install` 之前添加 `apt-get install gcc python3-dev pkg-config`
- **注意事项**: 安装后清理 apt 缓存 (`rm -rf /var/lib/apt/lists/*`) 以减小镜像体积
