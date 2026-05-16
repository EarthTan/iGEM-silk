---
name: Git Worktree 协作与合并冲突解决 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [git, worktree, merge, conflict-resolution, collaboration]
validated: true
---

# Gene Capsule: Git Worktree 协作与合并冲突解决

## Experience

**问题类型**: 多分支并行开发时的工作区隔离与合并冲突处理。

**核心策略**:
1. **Git worktree 隔离并行开发** — 用 `git worktree add` 创建独立工作区，每条 feature 分支有独立的文件系统状态，互不干扰。主工作区可保留未提交的修改
2. **docker-compose 合并冲突：补全而非修改** — 合并两个相似服务块时，冲突通常是某服务缺少完整的 `volumes`/`profiles`/`deploy`/`healthcheck` 段。修复方式是将冲突双方各自补全为独立完整的块，而非尝试合并共享配置
3. **config.py/README 合并冲突：全部保留** — 多个服务同时注册端口和文档时，冲突类型是纯增量的（每条新服务添加自己的条目）。修复方式是在正确端口位置保留所有条目
4. **sibling 分支合并后变基** — 当 PR #1 先合入，基于旧状态的 PR #2 需要变基。冲突是**可预测的**（固定 3 个文件，相同模式），全部修完即可 `--continue`

**关键参数**:
- worktree 创建: `git worktree add ../igem-silk-<feature> <branch>`
- 冲突文件集: `tools/docker-compose.yml`（服务块补全）、`main/config.py`（端口注册）、`tools/README.md`（文档条目）
- 变基命令: `git rebase deploy`（目标分支合入后）→ 修 3 个文件 → `git rebase --continue`

## Environment Fingerprint

- **任务域**: Git 多分支协作开发，微服务架构项目
- **输入特征**: 多条 feature 分支并行开发，共享配置文件（docker-compose、config、文档）
- **约束条件**: 无法在 main checkout 中存储未提交修改时，worktree 是唯一不提交就能切换分支的方式
- **不适用**:
  - 单人开发（无并行分支冲突风险）
  - 使用 `git stash` 就能处理的工作流
  - 项目配置完全隔离（无共享配置文件）

## Audit Record

- **验证方式**: iGEM-silk 项目中 ESMFold 和 OmegaFold 两条 feature 分支并行开发 + 合入
- **测试用例**:
  1. ESMFold 和 OmegaFold 同时修改 `tools/docker-compose.yml` → 合入时产生合并冲突 → 补全两个服务块各自的完整配置解决
  2. ESMFold 和 OmegaFold 同时添加端口到 `main/config.py` → 纯增量冲突 → 保留两行
  3. OmegaFold 在 ESMFold 合入后变基 → 3 个文件冲突可预测 → 一次性修复解决
- **成功率**: 100%（3/3 场景均一次修复成功）
- **局限性**: worktree 不适用于 git 钩子外的自动化场景；如果 3 个以上服务同时修改相同文件，冲突复杂度可能上升

## Usage

- **触发条件**: 多分支并行开发导致合并冲突，或需要在有未提交修改时切换分支
- **调用方式**:
  1. 新分支: `git worktree add ../igem-silk-<name> <branch>`
  2. 合并冲突: `git mergetool` 或手动编辑冲突块，补全完整的服务块
  3. sibling 变基: `git rebase deploy` → 修 3 个已知冲突 → `--continue`
- **注意事项**:
  - worktree 修改与主工作区互不感知——提交前记得检查 diff
  - `git worktree list` 查看所有 worktree
  - `git worktree remove <path>` 完成后清理
