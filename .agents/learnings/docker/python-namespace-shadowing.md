---
name: Python 命名空间遮蔽 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [python, namespace, import, package, docker, iGEM-silk]
validated: true
---

# Gene Capsule: Python 命名空间遮蔽

## Experience

**问题类型**: Python 导入系统中，微服务内部的 `tools/` 子目录遮蔽项目级 `tools/` 命名空间包，导致 `ModuleNotFoundError`。

**核心策略**: 将微服务内部 SDK 目录重命名为唯一名称（如 `anoxpepred_sdk/`），避免与项目级 `tools/` 冲突。

**关键参数**: `sys.path[0]`（CWD）、`__init__.py` 的存在

### 现象

`from tools.template.fasta_service import ...` 在 A 服务正常，在 B 服务报 `ModuleNotFoundError`。

### 根因

1. 项目结构：`/app/tools/` 下有 `template/`（框架代码，无 `__init__.py`——命名空间包）和 `AnOxPePred/`（微服务代码）
2. AnOxPePred 内部有 `tools/AnOxPePred/tools/` 子目录（自带 SDK），其中包含 `__init__.py`（正规包）
3. Docker 的 `WORKDIR /app/tools/AnOxPePred` 将 CWD 加入 `sys.path[0]`
4. Python 解析 `import tools` 时**优先找到本地 `tools/`**（有 `__init__.py`），遮蔽项目级 `tools/`

### 修复

```bash
# 将内部 tools/ 重命名为唯一名称
mv tools/AnOxPePred/tools tools/AnOxPePred/anoxpepred_sdk
mv tools/SoDoPE_paper_2020/tools tools/SoDoPE_paper_2020/sodope_sdk
```

### 预防

顶层 `tools/` 是项目框架命名空间包。各微服务的内部代码目录**不得使用 `tools/`** 作为目录名。

## Environment Fingerprint

- **任务域**: Python 多包项目
- **输入特征**: 项目使用命名空间包（无 `__init__.py`）+ 子目录有 `__init__.py` 的正规包
- **约束条件**: WORKDIR 设在子目录内
- **不适用**: 所有包都有 `__init__.py` 的标准 Python 项目

## Audit Record

- **验证方式**: iGEM-silk Docker 构建中 AnOxPePred 和 SoDoPE 两个服务复现并修复
- **失败案例**: `from tools.template.fasta_service import FastaToolService` → `ModuleNotFoundError: No module named 'tools.template'`
- **修复验证**: 重命名内部 SDK 目录后导入正常

## Usage

- **触发条件**: Docker 构建通过但运行时 `import tools.xxx` 报 ModuleNotFoundError，且本地开发正常
- **调用方式**: 检查 `sys.path[0]` 下是否有同名目录含 `__init__.py`；用 `python -c "import tools; print(tools.__path__)"` 确认实际加载的包
- **注意事项**: 这是最隐蔽的 Docker 构建问题——构建通过（COPY 成功），运行时才报错；且只在特定 WORKDIR 下触发
