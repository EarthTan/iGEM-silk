---
name: Linux 文件系统大小写敏感
description: macOS 开发时大小写不敏感，Linux 严格区分大小写，Dockerfile 中的 COPY、WORKDIR 和 compose 的 dockerfile 路径三处都可能不一致
created: 2026-05-13
version: 1.0.0
tags: [linux, macos, case-sensitivity, filesystem, docker, iGEM-silk]
validated: true
---

# Linux 文件系统大小写敏感

## Experience

- **问题类型**: 跨平台（macOS → Linux）文件路径不一致
- **核心策略**: 用 `ls` 逐字符确认实际目录名，不要"目测一致"就认为正确
- **关键参数**: 目录名的大小写必须与实际文件系统完全匹配

macOS 默认文件系统（APFS）大小写不敏感，Linux（ext4/xfs）严格区分。`Tipred` vs `TIPred`、`algpred2` vs `AlgPred2` 是不同的路径。

### 影响三处

1. Dockerfile 的 `COPY` 语句
2. docker-compose.yml 的 `dockerfile` 路径
3. Dockerfile 的 `WORKDIR` 指令

任一处不一致都会导致构建失败，且错误信息不会直接指向"大小写问题"。

## Environment Fingerprint

- **任务域**: 跨平台 Docker 项目
- **输入特征**: macOS 开发 + Linux 部署
- **约束条件**: 涉及文件路径的 Docker 配置
- **不适用**: 纯 macOS 或纯 Linux 单一环境开发

## Audit Record

- **验证方式**: iGEM-silk Docker 构建在 Ubuntu 部署环境验证
- **失败案例**: 多个服务因目录名大小写不匹配导致 `COPY` 失败
- **修复验证**: `ls tools/` 确认实际目录名后统一修正

## Usage

- **触发条件**: macOS 上构建通过但 Linux 上 COPY 报 `file not found`
- **调用方式**: `ls -1 tools/` 列出实际目录名，逐一比对 Dockerfile 和 compose 文件中的引用
- **注意事项**: 不仅仅是目录名——文件名同理（如 `service.py` vs `Service.py`）
