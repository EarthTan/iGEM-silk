---
name: freesasa 2.2.1 selectArea API 不兼容 v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [freesasa, sasa, api, python, open-source]
validated: true
---

# Gene Capsule: freesasa 2.2.1 selectArea API 不兼容

## Experience

**问题类型**: freesasa Python 库 2.2.1 版本 `selectArea()` API 签名变更导致现有代码崩溃。

**核心策略**:
1. 看到 `expected bytes, tuple found` 或 `TypeError` 错误时，立即定位到 `freesasa.selectArea()` 调用
2. 检查安装版本：`python -c "import freesasa; print(freesasa.__version__)"`
3. 版本 < 2.2.0 使用 `[(name, expression)]` 元组列表格式，版本 ≥ 2.2.1 使用 `["name, expression"]` 单字符串格式
4. 直接在虚环境中试验两种格式确认兼容性

**关键参数**:

| 版本 | selectArea 格式 | 示例 |
|------|----------------|------|
| ≤ 2.2.0 | `[(name, expr)]` 元组列表 | `freesasa.selectArea([("residue", "resi 1 and chain A")], ...)` |
| ≥ 2.2.1 | `["name, expr"]` 单字符串列表 | `freesasa.selectArea(["residue, resi 1 and chain A"], ...)` |

**典型错误信息**:
- `TypeError: expected bytes, tuple found` — 2.2.1 不再接受元组
- 隐式静默返回空 `{}` 也可能发生（用旧格式传 2.2.1，内部解析失败）

## Environment Fingerprint

- **任务域**: Python 开源生物信息学库调用，FreeSASA 溶剂可及表面积计算
- **输入特征**: `pip install freesasa` 自动安装最新版，项目可能未锁定版本
- **约束条件**: pip 默认安装最新版，无版本锁定则自动升级到 2.2.1+
- **不适用**: 已锁定 `freesasa<2.2.1` 的项目；使用 conda 安装且 conda 尚未推送 2.2.1 的环境

## Audit Record

- **验证方式**: iGEM-silk SASA 微服务 Docker 容器内运行时崩溃 + 修复后验证
- **测试用例**:
  1. 旧格式 `[("residue", "resi 1 and chain A")]` → `TypeError: expected bytes, tuple found`
  2. 新格式 `["residue, resi 1 and chain A"]` → 正常返回 `{'residue': 85.3}`
  3. 修复后批量 90 PDB 评分 → 全部成功，SASA mean=0.742
- **成功率**: 100%
- **局限性**: 如果将来 freesasa 再次变更 API 格式，此修复仍会失效

## Usage

- **触发条件**: SASA 服务 `POST /predict` 返回 500，`selectArea` 调用处报 `TypeError: expected bytes`
- **调用方式**: 找到 `freesasa.selectArea()` 调用，将所有 tuple 参数改为 `"name, expression"` 单字符串格式
- **注意事项**: Docker 构建时会拉取最新 freesasa 版本，下次构建可能再次变更。推荐在 `pyproject.toml` 中锁定 `freesasa>=2.2.1` 并在代码中兼容两种格式，或固定版本号
