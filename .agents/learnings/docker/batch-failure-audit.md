---
name: 构建失败时的批量审计策略 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [debugging, methodology, efficiency, docker, ci, iGEM-silk]
validated: true
---

# Gene Capsule: 构建失败时的批量审计策略

## Experience

**问题类型**: 多服务 Docker 构建失败后，逐个修复等待 CI 重试的低效循环。

**核心策略**: 第一次构建失败后立即做全量审计扫描，而非等 CI 逐轮报错——每次只修一个的渐进式方法在多服务场景下极低效。

**关键参数**: 审计检查项清单

15 个服务的全量 Docker 构建，每个服务构建需 2-10 分钟。每次只修一个失败 → 修复一个 → 等下一轮构建 → 发现新问题 → 循环 7-8 轮，耗时数小时。

### 审计检查清单

首次失败后，立即用脚本扫描：

1. 所有 `dockerfile:` 路径 → `grep 'dockerfile:' docker-compose.yml`
2. 所有 Dockerfile 的 `COPY` 语句 → `grep '^COPY' tools/*/Dockerfile`
3. 所有 `WORKDIR` 和 `CMD` → `grep 'WORKDIR\|^CMD' tools/*/Dockerfile`
4. 所有基础镜像的 Python 环境差异 → 检查 `FROM` 行
5. 所有 pip/uv 依赖安装方式 → 检查 `RUN pip` vs `RUN uv`
6. 所有 COPY 是否遗漏共享文件 → `tools/utils.py`, `tools/template/`

## Environment Fingerprint

- **任务域**: 多服务 Docker 项目构建
- **输入特征**: 首次构建或大面积配置变更
- **约束条件**: 构建耗时长（每个服务 > 1 分钟）
- **不适用**: 单服务项目或已知根因的单一错误

## Audit Record

- **验证方式**: iGEM-silk 15 服务全量 Docker 构建经历 7-8 轮 CI 失败后总结
- **效率对比**: 渐进式修复 ~3 小时 vs. 全量审计后批量修复 ~30 分钟
- **修复验证**: 后续新建服务时使用审计清单，一轮通过

## Usage

- **触发条件**: 多服务 Docker 构建出现 ≥2 个失败
- **调用方式**: 运行审计清单脚本 → 收集所有问题 → 一次性修复 → 重新构建
- **注意事项**: 清单应随新问题发现持续更新
