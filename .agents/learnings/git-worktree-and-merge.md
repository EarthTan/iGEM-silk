---
name: Git Worktree & Merge Resolution Patterns
description: Worktrees for parallel feature branches, merge conflict resolution patterns for microservice registrations
type: reference
---

- **Git worktrees**: useful for working on parallel features without disturbing uncommitted changes in the main checkout. Create with `git worktree add`, the CLI supports isolated copies.
- **docker-compose merge conflicts**: when merging two similar service blocks into docker-compose.yml, each must be a complete standalone block. A common merge error is one service missing its `volumes`/`profiles`/`deploy`/`healthcheck` sections because they were accidentally attributed to the other service.
- **config.py/README merge conflicts**: both ESMFold and OmegaFold add entries to `main/config.py` and `tools/README.md`. These are simple additive conflicts — keep both entries at the right port.
- **Rebase after sibling merge**: when PR #1 (ESMFold) merges first, PR #2 (OmegaFold) based on pre-ESMFold deploy needs rebase. Conflicts are predictable (same 3 files, same pattern). Fix all 3, continue, force-push.
