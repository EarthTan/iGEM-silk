---
name: Git Worktree Collaboration and Merge Conflict Resolution v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [git, worktree, merge, conflict-resolution, collaboration]
validated: true
---

> **English** | [中文](git-worktree-and-merge.zh.md)

# Gene Capsule: Git Worktree Collaboration and Merge Conflict Resolution

## Experience

**Problem type**: Workspace isolation and merge conflict handling during parallel multi-branch development.

**Core strategy**:
1. **Git worktree for isolated parallel development** — use `git worktree add` to create an independent workspace; each feature branch has its own filesystem state without interfering with the others. The main workspace can keep uncommitted changes
2. **docker-compose merge conflicts: complete rather than modify** — when merging two similar service blocks, the conflict is usually that one service is missing a complete `volumes`/`profiles`/`deploy`/`healthcheck` section. The fix is to complete each side of the conflict as its own self-contained block rather than trying to merge shared configuration
3. **config.py/README merge conflicts: keep everything** — when multiple services register ports and documentation entries at the same time, the conflicts are purely additive (each new service adds its own entries). The fix is to keep all entries at the correct port positions
4. **Rebase after a sibling branch is merged** — when PR #1 is merged first, PR #2, which is based on the old state, needs to be rebased. The conflicts are **predictable** (a fixed set of 3 files, same pattern), and once all are fixed `--continue` works

**Key parameters**:
- worktree creation: `git worktree add ../igem-silk-<feature> <branch>`
- Conflict file set: `tools/docker-compose.yml` (service block completion), `main/config.py` (port registration), `tools/README.md` (documentation entries)
- Rebase commands: `git rebase deploy` (after the target branch is merged) → fix the 3 files → `git rebase --continue`

## Environment Fingerprint

- **Task domain**: Git multi-branch collaborative development, microservice architecture project
- **Input characteristics**: Multiple feature branches developed in parallel, sharing configuration files (docker-compose, config, docs)
- **Constraints**: When uncommitted changes cannot be stored in the main checkout, worktree is the only way to switch branches without committing
- **Not applicable**:
  - Single-developer work (no risk of parallel branch conflicts)
  - Workflows that `git stash` can handle
  - Fully isolated project configuration (no shared configuration files)

## Audit Record

- **Validation method**: Parallel development and merging of two feature branches, ESMFold and OmegaFold, in the iGEM-silk project
- **Test cases**:
  1. ESMFold and OmegaFold both modified `tools/docker-compose.yml` → a merge conflict occurred on merge → resolved by completing each of the two service blocks with its full configuration
  2. ESMFold and OmegaFold both added ports to `main/config.py` → purely additive conflict → kept both lines
  3. OmegaFold rebased after ESMFold was merged → conflicts in 3 files were predictable → resolved with a single fix
- **Success rate**: 100% (all 3/3 scenarios fixed in one pass)
- **Limitations**: worktree is not suitable for automation outside git hooks; if 3 or more services modify the same file simultaneously, conflict complexity may rise

## Usage

- **Trigger conditions**: Parallel multi-branch development causes merge conflicts, or a branch switch is needed while there are uncommitted changes
- **How to invoke**:
  1. New branch: `git worktree add ../igem-silk-<name> <branch>`
  2. Merge conflict: `git mergetool` or manually edit the conflict blocks, completing the full service blocks
  3. Sibling rebase: `git rebase deploy` → fix the 3 known conflicts → `--continue`
- **Caveats**:
  - worktree changes and the main workspace are unaware of each other — remember to check the diff before committing
  - `git worktree list` shows all worktrees
  - `git worktree remove <path>` cleans up when done
