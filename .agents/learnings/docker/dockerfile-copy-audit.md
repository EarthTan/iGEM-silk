---
name: Dockerfile COPY 遗漏审计
description: 多个微服务 Dockerfile 容易遗漏共享文件（如 tools/utils.py）的 COPY 语句，运行时 import 失败；应用脚本批量扫描
created: 2026-05-13
version: 1.0.0
tags: [docker, dockerfile, copy, import-error, audit, iGEM-silk]
validated: true
---

# Dockerfile COPY 遗漏审计

## Experience

- **问题类型**: Dockerfile 遗漏共享依赖文件的 COPY
- **核心策略**: 用脚本批量扫描所有 Dockerfile 确保关键共享文件均被 COPY
- **关键参数**: 共享文件列表（`tools/utils.py`, `tools/template/`）

多个 Dockerfile 只 COPY 了 `tools/template/` 和 `tools/<service>/`，但漏了 `tools/utils.py`。运行时 `from tools.utils import detect_system` 失败——且构建阶段不报错。

### 批量审计脚本

```bash
for f in tools/*/Dockerfile; do
  if ! grep -q 'COPY.*utils\.py' "$f" 2>/dev/null; then
    echo "MISS: $f"
  fi
done
```

### 扩展检查项

```bash
# 检查所有关键共享文件
for f in tools/*/Dockerfile; do
  for dep in "utils.py" "template/" "__init__.py"; do
    if ! grep -q "COPY.*$dep" "$f" 2>/dev/null; then
      echo "MISS $dep in $f"
    fi
  done
done
```

## Environment Fingerprint

- **任务域**: 多服务 Docker 项目
- **输入特征**: 多个服务共享框架代码（`tools/template/`, `tools/utils.py`）
- **约束条件**: 首次配置新增服务时最容易遗漏
- **不适用**: 单服务或无共享代码的项目

## Audit Record

- **验证方式**: iGEM-silk 多个服务 Docker 构建通过但运行时 `ModuleNotFoundError`
- **失败案例**: `from tools.utils import detect_system` → ModuleNotFoundError，Dockerfile 中缺少 `COPY tools/utils.py /app/tools/utils.py`
- **修复验证**: 脚本扫描所有 Dockerfile 补全缺失的 COPY 后运行正常

## Usage

- **触发条件**: Docker 构建通过但运行时 `import` 报 ModuleNotFoundError
- **调用方式**: 运行批量审计脚本 → 补全缺失的 COPY → 重新构建
- **注意事项**: 构建阶段不报错是因为 Python 的 import 在运行时才解析——不要依赖构建通过来验证 COPY 完整性
