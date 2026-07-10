# AGENTS.md — AI Agent 行为约束

> 本文件约束本仓库的 AI Agent（Claude Code、Zed Agent 等）的行为。
> 人类开发者也请遵守"安全规则"部分。

---

## 1. 仓库形态（先理解再动手）

`iGEM-silk` 是一个**微服务工具库**，不是完整流程。

- **服务**：`tools/<name>/` 下 20 个独立的 FastAPI 微服务
- **主流程**：**已废弃**。`main/`、`data/`、`output*`、`docs/` 等主流程相关文件已在 `as-micro-service` 分支中删除
- **不要再尝试跑主流程**（如 `python -m main`）—— 入口已不存在
- **每个服务可独立启动、对外提供服务**

如果用户的需求是"跑完整设计流水线"，请明确告知：当前仓库仅保留微服务组件，完整流程需要从其他渠道获取或重建。

---

## 2. Python 环境约定

- **统一使用 `uv`**，不用 `pip`、`requirements.txt` 等
- **每个服务用各自 `pyproject.toml` + `uv.lock`**，独立 `.venv`
- **根目录无统一虚拟环境**（已删除）
- 根目录无 `pyproject.toml`（已删除）

**启动服务的标准流程**：
```bash
cd tools/<service-name>
uv sync                                # 第一次：装依赖到本目录 .venv
.venv/bin/python service.py            # 启动（推荐：明确使用本 venv 的 python）
# 或
uv run python service.py               # 启动（备选：uv 自动激活 venv）
```

**覆盖端口**：
```bash
PORT=8888 .venv/bin/python service.py
```

**覆盖 host**：
```bash
HOST=127.0.0.1 .venv/bin/python service.py
```

---

## 3. 文件类型判别（删之前先想清楚）

**判断依据：删了它会不会影响工具的调用？** 不看 git 是否 tracked。

| 路径 | 影响 | 操作建议 |
|------|------|---------|
| `tools/models/fair-esm/**/*.pt` | 11 GB 共享权重，ESMFold/BepiPred-3.0/pLM4CPPs 都靠它 | **绝不删** |
| `tools/models/omegafold/model.pt` | OmegaFold 权重 | **绝不删** |
| `tools/<name>/models/**` | 某些服务专属权重（MHCflurry / TemStaPro / AnOxPePred 等） | **绝不删** |
| `tools/<name>/uv.lock` | 子服务依赖锁定，重建 venv 的关键 | **保留** |
| `tools/<name>/.python-version` | uv 钉 Python 版本 | **保留** |
| `tools/<name>/pyproject.toml` | 子服务依赖声明 | **保留** |
| `tools/<name>/service.py` | 服务入口 | **保留** |
| `tools/<name>/Dockerfile` | 历史部署产物，新部署不使用 | 可删（不影响运行） |
| `tools/<name>/.venv/` | uv 创建的虚拟环境 | 可删（`uv sync` 可重建） |
| `tools/__init__.py` | 把 `tools/` 暴露为 Python 包，service.py 跨包导入目标 | **绝不删** |
| `tools/utils.py` | 跨包工具函数（`detect_system` 等） | **绝不删** |
| `tools/template/` | 三类服务模板（fasta/pdb/structure），service.py 跨包导入目标 | **绝不删** |
| `tools/<name>/.venv/`, `__pycache__/` | uv 缓存、Python 编译缓存 | 可删 |
| `tools/logs/` | 历史日志 | 可删 |
| 根目录 `.venv/`、`uv.lock`、`.python-version`、`pyproject.toml` | 主流程残留，已无作用 | **已删除** |

**判断口诀**：
- 任何 `*.pt` / `*.pth` / `*.bin` / `*.ckpt` → **先想是不是模型**
- 任何被 `service.py` `import` 的模块/包 → **不能删**
- 任何被 `service.py` 路径引用（`Path(...)`）的目录 → **不能删**
- 任何 `uv.lock`、`.python-version`、`pyproject.toml` → **重建 venv 关键，保留**
- 不确定 → **问用户**

---

## 4. 安全规则（生产环境教训）

> **本节源于真实教训（2026-05-17）**：在某次任务中，AI Agent 执行 `git clean -fdx` 后，删除了 esmfold 模型（6 GB）、ESM-2 t33 模型（2.5 GB）、数百个 BepiPred embedding 缓存，以及不可恢复的 `output3/` 数据。
> 在学校网络环境下，2.5 GB 文件下载需数小时到一天。

### 绝对禁令

1. **禁止**在仓库根运行 `git clean` 的任何变体（`git clean -fd` / `git clean -fdx` / `git clean -fdX`）
   - untracked 文件不是垃圾，是正在使用的模型、缓存、输出
   - `.gitignore` 中的文件更是如此

2. **禁止**运行 `git checkout -- .` 或 `git restore .`
   - 会用 HEAD 覆盖工作区未提交的修改

3. **禁止**运行 `git reset --hard`
   - 会丢弃未提交的修改和 untracked 改动

4. **执行任何"清理"操作前**：
   - 确认当前机器的角色（开发机/部署机）
   - 列出将被删除的文件，让用户确认
   - 区分文件类型（模型 vs 缓存 vs 输出 vs 编译产物）

### 文件类型白名单（可安全删除）

仅以下类型可被工具自动清理（且仍建议在执行前列出清单）：

- `**/__pycache__/`
- `**/*.pyc`、`**/*.pyo`
- `**/.mypy_cache/`、`**/.ruff_cache/`、`**/.pytest_cache/`
- `**/node_modules/`（本仓库无此情况）
- `**/.DS_Store`

**其他任何文件，删之前必须先问用户。**

---

## 5. 工作流程建议

### 修改 service.py 时的注意事项

- 20 个 `service.py` 都有 `PROJECT_ROOT = Path(__file__).parent.parent.parent; sys.path.insert(0, str(PROJECT_ROOT))`，**不要删这几行**，否则跨包导入会失败
- 启动方式 `if __name__ == "__main__": uvicorn.run(app, host=HOST, port=PORT)` 是统一入口模式，新增服务请保持一致
- 默认 `PORT` 应与 `tools/README.md` 的端口表一致

### 添加新服务时

参考 `tools/template/` 下的三类模板（`fasta_service.py` / `pdb_service.py` / `structure_service.py`），它们提供统一接口契约。新服务应：

1. 创建 `tools/<new-name>/` 目录
2. 写 `pyproject.toml`（参考同类服务）
3. 写 `service.py`（基于合适的 template）
4. 写 `uv.lock`（运行 `uv lock` 生成）
5. 文档化到 `tools/README.md`
6. **不要**新建 `docker-compose.yml` entry（本仓库已不再用 Docker 编排）

### 调试服务时

- **不要在仓库根运行 service**（会因路径不对找不到 `tools.template`）
- 必须 `cd tools/<name>/` 后再启动
- 用 `curl http://localhost:<port>/health` 验证

---

## 6. Agent 自身行为

- **不用 subagent**（项目根 `AGENTS.md` 历史约定保留）
- **不做超出用户请求范围的事**：用户没要求的事先问
- **不在用户工作区做不可逆操作**（特别是删除、reset、rebase）
- **不修改用户未请求的服务**：20 个服务是平行的，不要为"统一风格"擅自改写其他服务
- **遇到不确定的事先停下来问**，不要"猜测 + 实施"

---

## 7. 网络与外部依赖

部分服务首次启动需下载模型（学校网络下可能很慢）：

| 服务 | 下载内容 | 覆盖环境变量 |
|------|---------|-------------|
| ESMFold | `esmfold_3B_v1.pt` (~2.6 GB) | `ESMFOLD_MODEL_URL` |
| BepiPred-3.0 | `esm2_t33_650M_UR50D.pt` (~2.5 GB) | `ESM2_URL` |
| TemStaPro | ProtT5-XL (~3 GB) | `HF_ENDPOINT=https://hf-mirror.com` |
| OmegaFold | `release1.pt` (~1.5 GB) | `OMEGAFOLD_WEIGHTS_URL` |
| HemoPI2 | ESM-2 t6 (~29 MB) | `HF_ENDPOINT=https://hf-mirror.com` |

**建议**：在中国大陆网络下，设置 `HF_ENDPOINT=https://hf-mirror.com` 加速 HuggingFace 下载。

---

## 8. 历史背景（给 Agent 的人类读者）

iGEM-silk 仓库经历了三个阶段：

1. **完整流程期**：从候选肽生成到 3D 结构评估的完整流水线
2. **过渡期**：保留完整流程，开始沉淀微服务组件
3. **工具库期（当前）**：主流程废弃，仓库作为微服务工具库被其他业务复用

本 `AGENTS.md` 的安全规则写于第 2 阶段（生产部署机器上），反映的是「模型不可重下」的现实约束。
在第 3 阶段（工具库）下，虽然主流程已删除，但模型权重仍然在仓库中且下载成本高，**安全规则依然适用**。
