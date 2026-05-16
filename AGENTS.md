# 项目约定

1. 项目的根目录名称是 `iGEM-silk/`,以后统一用 `./` 表示

2. 项目的python环境使用 uv 管理，总的虚拟环境安装在 `./venv`。项目的python环境使用 `pyproject.toml` 来管理。`tools/`下的微服务每个有各自的环境，通过 FastAPI 的方式提供微服务，暴露端口提供给核心功能使用。

3. 本项目使用聪慧的 `uv` 和 `pyproject.toml` 来管理python环境，而不使用愚蠢的 `pip` 或者 `requirements.md`。

   


# Agent 须知

1. Never use subagent, do it yourself, step by step.
2. `.agents/learnings` 存储了学到的经验和教训，值得参考
3. `.agents/skills` 是本项目常用的skill，其中就包括了 "GEP-creator"
4. 本项目在实际使用中 <u>**一律使用docker运行所有微服务，绝对禁止直接用python运行微服务**</u>

# 安全规则（生产部署机器）

## 这台机器的身份

- **角色**: iGEM-silk 生产部署机器
- **网络**: 学校网络，下载大文件极慢（2.5GB 需数小时到一整天）
- **风险等级**: 高 — 任何数据丢失都需要极长时间恢复

## 绝对禁令

> ⚠️ 以下禁令源于真实教训（2026-05-17）：Claude Code 在执行 `git clean -fdx` 后，删除了 esmfold 模型（6GB）、ESM-2 t33 模型（2.5GB）、数百个 BepiPred embedding 缓存，以及 stages3 输出目录 `output3/`（含不可恢复的数据）。

1. **绝对禁止在生产机器上运行 `git clean` 的任何变体（包括 `git clean -fd` 和 `git clean -fdx`）。**
   - untracked 文件不是垃圾文件，是正在使用的模型和数据。
   - `.gitignore` 中的文件更是如此，删除后恢复极难。

2. **绝对禁止在生产机器上运行 `git checkout -- .` 或 `git restore .`。**

3. **绝对禁止在生产机器上运行 `git reset --hard`。**

4. **在执行任何危险操作前，必须先确认当前机器的角色，并理解每个 untracked 文件的作用。**

## 安全操作流程

1. **识别机器角色**: 有大量 `.pt` 模型文件、有 `output/` `output3/` 目录的就是生产机器。不确定就问用户。
2. **区分文件类型**:
   - `.pt` / `.bin` / `.pth` / `.ckpt` 模型文件 → **绝对不能删**
   - `output/` / `output3/` 输出数据 → **绝对不能删**
   - `esm_cache/` 缓存 → 可重建但成本高，需用户确认
   - `__pycache__/` → 安全
3. **优先使用隔离机制**: 对生产机器的任何修改工作，使用 `EnterWorktree`（git worktree）创建隔离工作区，不要直接在当前目录操作。
4. **不确定就问用户**: 不清楚后果的操作，先问用户再执行。
