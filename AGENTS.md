> **English** | [中文](AGENTS.zh.md)

# Project Conventions

1. The project root directory is named `iGEM-silk/`; from now on, `./` refers to it uniformly.

2. The project's Python environment is managed with uv, and the shared virtual environment is installed at `./venv`. The project's Python environment is managed with `pyproject.toml`. Each microservice under `tools/` has its own environment, provides its microservice through FastAPI, and exposes a port for use by the core functionality.

3. This project uses the smart `uv` and `pyproject.toml` to manage the Python environment, instead of the stupid `pip` or `requirements.md`.

   


# Notes for Agents

1. Never use subagent, do it yourself, step by step.
2. `.agents/learnings` stores the experience and lessons learned, and is worth consulting.
3. `.agents/skills` contains the skills commonly used in this project, including "GEP-creator".
4. In actual use, this project <u>**always runs all microservices with Docker; running microservices directly with Python is absolutely forbidden**</u>.

# Safety Rules (Production Deployment Machine)

## Identity of This Machine

- **Role**: iGEM-silk production deployment machine
- **Network**: University network; downloading large files is extremely slow (2.5 GB takes hours to a whole day)
- **Risk level**: High — any data loss requires an extremely long time to recover

## Absolute Prohibitions

> ⚠️ The following prohibitions come from a real lesson (2026-05-17): after running `git clean -fdx`, Claude Code deleted the esmfold model (6 GB), the ESM-2 t33 model (2.5 GB), hundreds of BepiPred embedding caches, and the stages3 output directory `output3/` (which contained unrecoverable data).

1. **Absolutely forbidden to run any variant of `git clean` on the production machine (including `git clean -fd` and `git clean -fdx`).**
   - Untracked files are not garbage; they are models and data currently in use.
   - This is even more true for files listed in `.gitignore`; once deleted, they are extremely hard to restore.

2. **Absolutely forbidden to run `git checkout -- .` or `git restore .` on the production machine.**

3. **Absolutely forbidden to run `git reset --hard` on the production machine.**

4. **Before performing any dangerous operation, you must first confirm the role of the current machine and understand the purpose of every untracked file.**

## Safe Operating Procedure

1. **Identify the machine role**: a machine with many `.pt` model files and `output/` `output3/` directories is the production machine. If unsure, ask the user.
2. **Distinguish file types**:
   - `.pt` / `.bin` / `.pth` / `.ckpt` model files → **must never be deleted**
   - `output/` / `output3/` output data → **must never be deleted**
   - `esm_cache/` cache → rebuildable but expensive; requires user confirmation
   - `__pycache__/` → safe
3. **Prefer isolation mechanisms**: for any modification work on the production machine, use `EnterWorktree` (git worktree) to create an isolated workspace; do not operate directly in the current directory.
4. **When unsure, ask the user**: for operations whose consequences are unclear, ask the user before executing.
