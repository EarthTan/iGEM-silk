# Docker 历史归档 — iGEM-silk

> ⚠️ **本文件为历史归档**。本项目（`as-micro-service` 及之后分支）已**不再使用 Docker**
> 作为部署方式。当前微服务全部以 `uv`-managed venv 直接运行：
>
> ```bash
> cd tools/<service-name>
> uv sync                                # 首次：装依赖
> .venv/bin/python service.py            # 启动
> ```
>
> 详情见 [`tools/README.md`](./README.md)；Agent 行为约束见仓库根 [`AGENTS.md`](../AGENTS.md)。
>
> 本仓库仍遗留 `docker-compose.yml` 与若干 `tools/*/Dockerfile` 作为历史产物，**它们已无人维护、不要新提交依赖其正确性**，新部署请使用上面 `uv` 方式。本文档保留所有 Docker 相关经验教训，仅供：
>
> - 排查遗留 `Dockerfile` / `docker-compose.yml` 中可能存在的旧 bug
> - 复用本文沉淀的 GPU 显存、命名空间、健康检查等通用微服务经验
> - 必要时回退到 Docker 化部署的参考
>
> **最后更新**: 2026-08-06（标记归档；最后一次有效 Docker 操作经验为 2026-05-18）

---

## 0. 当前部署方式（取代 Docker）

按 [`AGENTS.md` §1–§2](../AGENTS.md) 与 [`tools/README.md`](./README.md)：

| 项目 | 值 |
|------|-----|
| 包管理 | `uv`（不用 `pip` / `requirements.txt`） |
| Python 环境 | 每个服务独立 `pyproject.toml` + `uv.lock`，独立 `.venv` |
| 启动方式 | `cd tools/<name> && uv sync && .venv/bin/python service.py` |
| 端口覆盖 | `PORT=8888 .venv/bin/python service.py` |
| Host 覆盖 | `HOST=127.0.0.1 .venv/bin/python service.py` |
| 健康检查 | `curl http://localhost:<port>/health` |

**删除/保留判断**（参考 `AGENTS.md` §3）：

- `tools/*/Dockerfile`、`tools/docker-compose.yml`：历史部署产物，新部署不使用 → 可删
- `tools/models/**`、`tools/*/models/**`：共享权重与专属权重 → **绝不删**
- `tools/utils.py`、`tools/template/`：跨包导入目标 → **绝不删**

**安全规则**（仍适用，见 `AGENTS.md` §4）：

- 禁止 `git clean` / `git checkout -- .` / `git reset --hard` / `git restore .`
- 任何清理前先列清单确认

---

## 1. 核心原则（历史）

> 适用于旧版 Docker 化部署；当前不再适用，仅作背景。

### 1.1 ~~所有服务必须用 Docker 运行~~ → 改为 `uv` 直接运行

旧原则：所有微服务通过 Docker Compose 运行，宿主机不直接 `python service.py`。

**当前**：

- 服务独立 `uv` venv，每个服务一套 Python 环境，比 Docker 更轻量
- 模型文件路径已按仓库布局硬编码，裸跑 (`uv` 启动) 即可
- `service.py` 的 `uvicorn.run(host="0.0.0.0")` 仍是正确且必须的，**永远不要修改**
- Docker 容器内部通信要求绑定 `0.0.0.0`；裸跑时同样需要 `0.0.0.0` 以接受跨容器/跨主机的健康检查

### 1.2 ~~按需启动，用完即关~~

旧 Docker 部署下，GPU 服务之间会争夺显存（48GB），需要按 step 启停。

**当前**：每个服务独立进程，启停粒度自然就是单个服务，约束更松，但仍建议：

- GPU 显存总量 48GB，单个 GPU 服务可能占用 6–34GB
- 不同 step 切换前确认已停掉前 step 的 GPU 服务，`nvidia-smi` 检查残留

### 1.3 ~~禁止裸机执行~~ → 改为鼓励裸机执行（用 `uv`）

旧原则禁止 `cd tools/AnOxPePred && python service.py`。

**当前**：`cd tools/AnOxPePred && uv run python service.py` 正是推荐方式。

---

## 2. 服务总览（历史）

### 2.1 微服务清单

历史版本共 19 个微服务，分为两组 profile。本节仅作为旧部署的记忆。

#### 旧 GPU services (`--profile gpu`)

| 服务 | 端口 | 分组 | 显存占用 | 启动等待 | 备注 |
|------|------|------|---------|---------|------|
| anoxpepred | 8001 | score | ~10GB | 30s | TensorFlow GPU |
| bepipred3 | 8002 | score | ~6GB | 60s | ESM-2 650M 模型 |
| hemopi2 | 8004 | filter | ~2GB | 60s | |
| mhcflurry | 8005 | score | ~2GB | 120s | 模型加载慢 |
| plm4cpps | 8006 | score | ~6GB | 60s | ESM-2 + TF |
| graphcpp | 8009 | score | ~4GB | 30s | torch-geometric |
| temstapro | 8010 | score | ~11GB | 120s | HuggingFace 模型 |
| alphafold3 | 8201 | structure | (wrapper) | 15s | Docker socket 包装 |
| esmfold | 8203 | structure | ~17GB | 120s | openfold 编译 |
| omegafold | 8204 | structure | ~11GB | 120s | 同步推理阻塞事件循环 |

#### 旧 CPU services (`--profile cpu`)

| 服务 | 端口 | 分组 | 备注 |
|------|------|------|------|
| toxinpred3 | 8003 | filter | sklearn 单线程，容易挂死 |
| algpred2 | 8008 | filter | |
| sodope | 8012 | score | |
| tipred | 8007 | score | 暂未在 pipeline 中使用 |
| sasa | 8101 | pdb_score | |
| aggrescan3d | 8102 | pdb_score | Python 2.7 via micromamba |
| waveflow | 8205 | structure | Tamarind.bio API wrapper |
| pepfold4 | 8202 | structure | Docker socket 包装 |

**当前**：参见 [`tools/README.md`](./README.md) 的服务清单（21 个服务，含 `AMP-ESM` 等新增项）。当前服务全部以 `uv` 直接启动，不再有 GPU/CPU profile 概念。

### 2.2 Profile 实际分布（与规划文档的差异）

历史笔记：旧 Docker Compose 实际分布与早期规划不一致——大多数评分服务是 GPU 而非 CPU。这意味着大多数 pipeline step 需要同时启动 `gpu` 和 `cpu` 两个 profile。

**当前**：该约束已不存在。

### 2.3 Step 依赖地图（历史）

```
step0: []                          — 纯本地预处理
step1: [anoxpepred, algpred2]      — gpu + cpu
step2: [anoxpepred, bepipred3,     — gpu + cpu (9 服务)
        plm4cpps, graphcpp,
        temstapro, sodope,
        mhcflurry, toxinpred3,
        hemopi2]
step3: [sodope, temstapro]         — cpu + gpu
step4: [omegafold]                 — gpu only
step5: [sasa, aggrescan3d]         — cpu only
step6: []                          — 纯本地排名
```

**当前**：主流程（`main/`、`data/`、`output*`）已在 `as-micro-service` 分支删除，pipeline 不再存在；本图仅作历史参考。

---

## 3. Docker Compose 用法（历史）

### 3.1 构建与启动（正确顺序）

> 仅在回退到 Docker 部署时使用。

#### 错误做法

```bash
cd tools
docker compose --profile gpu --profile cpu up -d --build
# ↑ 15 个服务一起构建，一个失败则全部回滚
```

#### 正确做法

```bash
cd tools

# 1. 按 profile 分批构建，隔离故障
docker compose --profile cpu build
docker compose --profile gpu build

# 2. 构建全部通过后再启动
docker compose --profile gpu --profile cpu up -d

# 或者只启动当前 step 需要的服务
docker compose --profile gpu up -d anoxpepred
docker compose --profile cpu up -d algpred2
```

#### 仅重构建单个服务

```bash
docker compose build anoxpepred
docker compose up -d anoxpepred
```

> **关键**：`docker compose up -d --build` 是原子性的——15 个服务中即使只有一个构建失败，前面已经构建成功的 10 个也会被丢弃。始终将构建（build）和启动（up）分开。

### 3.2 常见陷阱（依然有参考价值）

虽然 Docker 不再使用，但以下陷阱在裸跑 `service.py` 时部分仍然适用。

#### 陷阱 1：路径是相对于 build context 的

旧 Docker Compose：
```yaml
build:
  context: ..          # context = tools/..
  dockerfile: tools/AnOxPePred/Dockerfile   # ✅ 正确
  # dockerfile: Dockerfile                 # ❌ 错误 — 会在 context 根目录找
```

**当前等价**：服务代码里 `service.py` 有 `PROJECT_ROOT = Path(__file__).parent.parent.parent; sys.path.insert(0, str(PROJECT_ROOT))` 来支持跨包导入，**不要删**，否则 `from tools.template....` 会失败。

#### 陷阱 2：共享依赖遗漏

历史 Docker 构建中遗漏 `COPY tools/utils.py` 或 `COPY tools/template/` 不会导致构建失败，但会在运行时抛 `ModuleNotFoundError`。

**当前**：直接 `uv sync` 安装依赖；服务代码通过 `PROJECT_ROOT` 路径追加 `sys.path` 来引用 `tools/utils.py` 和 `tools/template/`，只要这两个目录存在就不会出问题。

#### 陷阱 3：`latest` 标签导致 CI 突发失败

```dockerfile
# ❌ 不要用 latest
FROM ghcr.io/astral-sh/uv:latest

# ✅ 固定版本
FROM ghcr.io/astral-sh/uv:0.4.30
```

**当前**：`uv` 版本通过 `uv self update` 控制；不要在 `pyproject.toml` 中钉 `uv` 自身版本。如果遇到上游破坏，升级/降级全局 `uv`。

#### 陷阱 4：Linux 文件名大小写

macOS 的文件系统（APFS）默认不区分大小写，Linux（ext4/xfs）区分。
- 在 macOS 上 `Tipred` 和 `TIPred` 指向同一目录
- 在 Linux 上它们指向不同目录

```bash
# 用这个命令确认真实目录名，不要目测
ls -1 tools/
```

**当前仍适用**：影响 `cd tools/Tipred` 的服务路径、跨包 `import` 等。Linux 部署时一定先 `ls -1` 确认。

#### 陷阱 5：Python 命名空间遮蔽（最隐蔽的错误）

项目根目录的 `tools/` 是命名空间包（无 `__init__.py`）。
如果微服务内部有一个同名的 `tools/` 子目录（有 `__init__.py`），
Python 会优先找到本地包，导致 `from tools.template.fasta_service import ...` 抛出 `ModuleNotFoundError`。

**诊断**：
```bash
python -c "import tools; print(tools.__path__)"
```

**修复**：微服务内部代码目录绝不能命名为 `tools/`。例如 `mv tools/AnOxPePred/tools tools/AnOxPePred/anoxpepred_sdk`。

**当前仍适用**：本仓库根目录的 `tools/` 是命名空间包（注意 `tools/__init__.py` 是空的），如果新服务内建了 `tools/` 子目录就会出现这个问题。

#### 陷阱 6：slim 镜像缺少 C 扩展编译依赖

```dockerfile
# ❌ 这样会失败——slim 镜像没有 Python.h
FROM python:3.11-slim
RUN pip install freesasa

# ✅ 需要先装构建依赖
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev pkg-config libxml2-dev \
    && rm -rf /var/lib/apt/lists/*
```

**当前仍适用**：如果某个服务在 `uv sync` 时报 `Python.h` 缺失，说明系统缺编译工具链：

```bash
# Debian/Ubuntu
sudo apt install build-essential python3-dev

# macOS (Homebrew)
xcode-select --install
```

### 3.3 基础镜像选型（历史）

旧 Docker 部署使用 7 种基础镜像模式，本节仅供历史归档查阅。`uv` 部署下不再涉及。

| 模式 | 基础镜像 | 适用场景 | 服务示例 |
|------|---------|---------|---------|
| **A** | `pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime` | GPU PyTorch | BepiPred3, HemoPI2, MHCflurry, pLM4CPPs, TemStaPro, GraphCPP |
| **B** | `nvidia/cuda:12.1.0-*-ubuntu22.04` | 原始 CUDA + 自定义 Python | ESMFold (devel), OmegaFold (runtime) |
| **C** | `python:3.11-slim` | CPU 服务 | ToxinPred3, SASA, AlgPred2, Tipred |
| **D** | `tensorflow/tensorflow:2.21.0-gpu` | TensorFlow GPU | AnOxPePred |
| **E** | `python:3.13-slim` | 最新 Python | SoDoPE |
| **F** | `ghcr.io/mamba-org/micromamba:latest` | Conda 环境 / Python 2.7 | Aggrescan3D |
| **G** | `python:3.11-slim` + Docker socket | Docker 套娃包装 | AlphaFold3, PEP-FOLD4, Waveflow |

### 3.4 GPU 服务管理

#### 健康检查不同步（依然适用）

GPU 服务的健康检查通过并不意味预测一定能成功。模型可能在容器启动后才开始加载到 GPU，健康检查的超时期限（`start_period`）需要足够长。

裸跑 `service.py` 时等价问题：访问 `/health` 返回 200，但模型还没加载完，第一个预测请求会超时。`curl` 几次 `/health` 或在前几次预测上加更长超时。

旧 `docker-compose.yml` 中的健康检查模式：
```yaml
healthcheck:
  test: curl -f http://localhost:PORT/health || exit 1
  interval: 30s
  timeout: 10s       # 轻量服务
  timeout: 30s       # GPU 重服务
  timeout: 60s       # 结构预测
  retries: 3         # 轻量服务
  retries: 5         # GPU 重服务
  start_period: 60s  # GPU 服务（模型加载时间）
```

#### 桥接 IP 直连（绕过 docker-proxy）—— Docker 专属

通过 `127.0.0.1:PORT`（docker-proxy）访问容器在长耗时请求下会出现间歇性挂死——容器内正常处理请求，但客户端收不到响应。

**诊断方法**：
```bash
# 宿主机 curl 可能挂死
curl http://127.0.0.1:8002/health

# 但容器内 curl 正常
docker exec bepipred3 curl http://localhost:8002/health

# 桥接 IP 直连正常
curl http://172.18.0.X:8002/health
```

**当前**：本节是 Docker 专属问题，裸跑 `service.py` 时服务直接绑定宿主机 `0.0.0.0`，不再有 docker-proxy 中间层。仍可能遇到类似的间歇性挂死，那是 asyncio/uvicorn 自身问题（如 OmegaFold 同步阻塞，见下），需要排查具体服务。

#### GPU 显存检查（依然适用）

启动 GPU 服务前确认显存充足：
```bash
nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits
```

各 GPU 服务显存需求（粗略）：
- AnOxPePred: ~10GB（退出后残留 ~34GB CUDA context！）
- BepiPred3: ~6GB
- TemStaPro: ~11GB
- OmegaFold: ~11GB
- ESMFold: ~17GB
- pLM4CPPs: ~6GB
- 总可用: 48GB

**GPU 服务并发原则**：
- 同一时间只运行一个 GPU 密集型服务
- Semaphore > 1 对串行 GPU 推理永远没有好处——只会增加超时概率
- 使用 CPU 预筛（TemStaPro）减少 GPU 负载：取 Top 30% 再喂给 GPU

---

## 4. 服务生命周期管理（历史 + 部分仍适用）

### 4.1 启动前检查清单（部分仍适用）

```
□ Python 环境是否就绪？  → cd tools/<name> && uv sync
□ 所需 GPU 服务显存是否充足？ → nvidia-smi
□ 所需端口是否冲突？ → ss -tnp | grep <PORT>
□ 端口/Host 是否需要覆盖？ → 确认 PORT / HOST 环境变量
□ 之前 step 的 GPU 进程是否已清理？ → ps aux | grep python
```

### 4.2 按需启动协议（历史）

旧版通过 `main/stages3/docker_utils.py::ensure_services()` 统一入口。当前主流程已删除，本节仅供历史归档。

### 4.3 运行中监控（依然适用）

```bash
# 查看服务进程
ps aux | grep service.py

# 查看 GPU 使用情况
watch -n 2 nvidia-smi

# 查看端口监听
ss -tnlp | grep <PORT>

# 健康检查
curl http://localhost:<port>/health
```

**超时策略**（按服务类型，仍适用）：

| 服务类型 | 超时 | 说明 |
|---------|------|------|
| 轻量评分（anoxpepred, algpred2 等） | 30s | 大多数请求 < 5s |
| BepiPred3 | 600s | GPU 串行，单批 ~115s（50条） |
| OmegaFold | 14400s（4h） | 单结构 90-120s，同步阻塞 |
| ESMFold | 600s | 单结构 ~120s |
| ToxinPred3 | 120s | socket 超时，asyncio 无法中断 |

### 4.4 关机与清理

#### 4.4.1 正常关闭（已不适用）

旧 Docker 部署下 `docker compose stop` / `docker compose down`。

**当前**：找到进程并 `kill`：

```bash
# 找到服务进程
ps aux | grep service.py | grep <name>

# 优雅终止
kill <PID>

# 仍未释放则强制
kill -9 <PID>
```

#### 4.4.2 GPU 显存释放（第 4 号坑，依然适用）

**容器 `docker stop` 不能释放 GPU 显存**——这是旧 Docker 部署的痛点。即使切到裸跑，仍会出现 PyTorch 缓存分配器保留 CUDA context 导致显存不释放的问题（AnOxPePred 尤其严重，可残留 ~34GB）。

**正确的 GPU 显存释放流程**：
```bash
# 1. 找到残留的 Python 进程
ps aux | grep service.py | grep anoxpepred

# 2. 强制杀死
kill -9 <PID>

# 3. 确认显存已释放
nvidia-smi
```

**预防措施**：
- 启动新 GPU 服务前执行 `nvidia-smi` 确认显存
- **不同 step 之间务必检查是否有残留 GPU 进程**
- 旧 Docker 下还会设置 `init: true`（tini init 进程）、`stop_grace_period: 5s`；裸跑下注意 SIGTERM 处理

#### 4.4.3 Step 切换标准流程（历史）

主流程已删除，本节作废。当前只需：

```
1. 停旧服务：kill <PID>（必要时 kill -9）
2. 检查 GPU 显存：nvidia-smi
3. 启动新服务：cd tools/<name> && .venv/bin/python service.py
4. 确认新服务健康：curl http://localhost:<port>/health
```

---

## 5. 故障排查手册（部分仍适用）

### 5.1 Docker 构建失败（已不适用）

本节是 Docker 专属。当前问题转写为：

**`uv sync` 失败**：
1. 查看错误最后几行：`uv sync 2>&1 | tail -50`
2. 检查 Python 版本（`tools/<name>/.python-version` 是否钉了版本，宿主机是否安装）
3. 检查系统编译依赖（见 §3.2 陷阱 6）
4. 网络问题：设置 `UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple` 或 `HF_ENDPOINT=https://hf-mirror.com`

### 5.2 Docker Hub 不可达（中国网络）→ 改为 PyPI/HF 镜像

**当前症状**：`uv sync` 在某些包下载时超时或失败。

**解决方案 — 配置镜像**：
```bash
# 临时
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export HF_ENDPOINT=https://hf-mirror.com

# 永久（写入 shell rc）
echo 'export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple' >> ~/.zshrc
echo 'export HF_ENDPOINT=https://hf-mirror.com' >> ~/.zshrc
```

历史 Docker Hub 镜像配置（已不适用，仅归档）：
```json
// /etc/docker/daemon.json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```

### 5.3 容器健康但请求挂死（docker-proxy bug）→ 已不适用

Docker 专属问题。裸跑下若出现类似挂死，请先排除：
1. OmegaFold 同步推理阻塞事件循环（见 §5.5）
2. asyncio 任务队列堆积
3. 系统层面 DNS/socket 问题（`dmesg | tail`）

### 5.4 GPU 显存不足（依然适用）

**症状**：服务健康检查通过但预测失败，或模型加载到一半静默挂死（无 OOM 错误，无日志）。

**排查**：
```bash
nvidia-smi
# 检查：已用显存 vs 总显存（48GB）
# 检查：是否有残留的 python 进程占用显存
```

**按需启动策略**（避免同时启动多个 GPU 服务）：

```
场景: Step 1 需要 anoxpepred + algpred2
  → 先启动 anoxpepred (GPU, ~10GB)
  → 显存剩余 38GB，够用
  → 再启动 algpred2 (CPU, 不占显存)

场景: Step 4 需要 omegafold (~11GB)
  → 确保之前 step 的 GPU 服务已停止并释放显存
  → 确认 nvidia-smi 显存空闲 > 20GB
  → 启动 omegafold
```

**JAX 的 CUDA 初始化时机**（陷阱）：JAX 在进程启动时初始化 CUDA，而不是在模型加载时。这意味着健康检查通过时显存可能已经不够，但不会报错。预测时才会因 `RuntimeError: No supported devices found` 或 `OutOfMemoryError` 而失败。

### 5.5 服务挂死（依然适用）

#### ToxinPred3（sklearn 单线程挂死）

**症状**：ToxinPred3 进程 CPU 100%，端口无响应。`asyncio.wait_for` 超时不能中断（C 扩展不受 Python 信号控制）。

**最终解决方案**（经过多轮迭代）：
- 使用同步 `requests` 代替 `httpx`（socket 超时由内核处理，可中断）
- 批次大小：200（从 1000 减少）
- 超时：120s
- 连续 5 批超时时调用 `/restart` 端点
- 完全串行化（单连接，单请求）

参见 `main/stages2/round02_toxinpred3_sync.py`（主流程已删除，请参考思路自行迁移）。

#### OmegaFold（同步推理阻塞事件循环）

**症状**：OmegaFold 的 `self.model(input_data)` 是同步 PyTorch CUDA 调用（90-120s），在 `async def` 中直接调用会阻塞 uvicorn 事件循环。在此期间 `/health`、`/status/{job_id}`、`/result/{job_id}` 全部挂起。

**客户端修复**：`asyncio.Semaphore(1)` 串行化请求。
**服务端推荐修复**（尚未实施）：将推理移入 `run_in_executor(ThreadPoolExecutor(max_workers=1), ...)`。

### 5.6 Python 命名空间遮蔽（依然适用）

**症状**：`ModuleNotFoundError: No module named 'tools.template'`，但 `tools/template/` 确实存在。

**诊断**：
```bash
cd tools/<name>
.venv/bin/python -c "import tools; print(tools.__path__)"
# 输出类似：['/.../tools/AnOxPePred/tools'] ← 错误的路径！
# 应该是：['/.../tools']
```

**修复**：微服务内部代码目录绝不能命名为 `tools/`。必要时 `mv tools/<name>/tools tools/<name>/<name>_sdk`。

### 5.7 Linux 大小写敏感导致的构建失败 → 改为 Linux 大小写敏感导致的服务找不到

**症状**：在 macOS 上 `uv run python service.py` 正常，部署到 Linux 上 `ModuleNotFoundError`。

**排查**：
```bash
# macOS 和 Linux 上分别执行
ls -1 tools/

# 确认 cd 进去的目录名与代码中引用一致
cd tools/Tipred && cat pyproject.toml | grep -i name
```

### 5.8 Docker-outside-Docker 路径问题（已不适用）

Docker 专属问题，裸跑下不再存在。AF3 / PEP-FOLD4 / Waveflow 等若仍依赖 Docker socket 启动子容器，请参考历史方案：

```yaml
environment:
  AF3_MODEL_DIR: /root/models
  AF3_MODEL_HOST_DIR: /home/lenovo/af_models
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - /usr/bin/docker:/usr/bin/docker
```

---

## 6. 速查命令表（更新版）

### 启动/停止（当前）

| 命令 | 说明 |
|------|------|
| `cd tools/<name>` | 所有服务操作在各自目录下执行 |
| `uv sync` | 安装/同步依赖到 `.venv` |
| `.venv/bin/python service.py` | 启动服务 |
| `uv run python service.py` | 启动服务（备选） |
| `PORT=8888 .venv/bin/python service.py` | 覆盖端口 |
| `HOST=127.0.0.1 .venv/bin/python service.py` | 覆盖 host |
| `kill <PID>` | 优雅终止服务 |
| `kill -9 <PID>` | 强制终止 |
| `curl http://localhost:<port>/health` | 健康检查 |

### 历史 Docker 命令（归档参考）

| 命令 | 说明 |
|------|------|
| `cd tools` | 所有 Docker 操作在 tools/ 下执行 |
| `docker compose --profile cpu build` | 构建所有 CPU 服务 |
| `docker compose --profile gpu build` | 构建所有 GPU 服务 |
| `docker compose build anoxpepred` | 构建单个服务 |
| `docker compose --profile gpu up -d` | 启动所有 GPU 服务 |
| `docker compose --profile cpu up -d` | 启动所有 CPU 服务 |
| `docker compose up -d anoxpepred algpred2` | 启动指定服务 |
| `docker compose stop anoxpepred` | 停止指定服务 |
| `docker compose down` | 停止并移除所有容器 |

### 监控（依然适用）

| 命令 | 说明 |
|------|------|
| `ps aux \| grep service.py` | 查看服务进程 |
| `nvidia-smi` | 查看 GPU 显存 |
| `watch -n 2 nvidia-smi` | 实时监控 GPU |
| `ss -tnlp \| grep <PORT>` | 查看端口占用 |
| `curl http://localhost:<port>/health` | 健康检查 |

### 排查（依然适用）

| 命令 | 说明 |
|------|------|
| `ps aux \| grep python` | 查找残留 Python 进程 |
| `kill -9 <PID>` | 强制释放 GPU 显存 |
| `uv sync 2>&1 \| tail -50` | 查看依赖安装最后几行 |
| `dmesg \| tail` | 查看内核日志（OOM、CUDA 错误） |
| `ls -1 tools/` | 确认目录名大小写 |

---

## 附录：经验胶囊索引

本文件的内容来自以下 `.agents/learnings/` 中的经验胶囊，部分仍在裸跑下适用：

| 主题 | 胶囊文件 | 当前是否适用 |
|------|---------|-------------|
| Docker Compose 原子性回滚 | `docker/compose-atomic-build.md` | ❌ Docker 专属 |
| 批量故障审计 | `docker/batch-failure-audit.md` | ❌ Docker 专属 |
| Dockerfile COPY 遗漏 | `docker/dockerfile-copy-audit.md` | ❌ Docker 专属 |
| dockerfile 路径相对于 context | `docker/dockerfile-path-compose.md` | ❌ Docker 专属 |
| latest 标签版本不确定性 | `docker/latest-tag-pinning.md` | ❌ Docker 专属 |
| Linux 大小写敏感 | `docker/linux-case-sensitivity.md` | ✅ 仍适用 |
| Python 命名空间遮蔽 | `docker/python-namespace-shadowing.md` | ✅ 仍适用 |
| slim 缺少 C 编译依赖 | `docker/slim-image-build-deps.md` | ✅ 仍适用（系统级） |
| Docker Hub 中国镜像 | `docker/docker-hub-china-mirror.md` | ❌ Docker 专属 |
| Docker-outside-Docker 路径 | `docker/docker-outside-docker-paths.md` | ❌ Docker 专属 |
| 容器内 Docker CLI 安装 | `docker/docker-cli-in-container.md` | ❌ Docker 专属 |
| 桥接 IP 直连 | `gep-docker-container-bridge-ip.md` | ❌ Docker 专属 |
| Docker 不可达时原生回退 | `gep-docker-native-hybrid.md` | ❌ Docker 专属 |
| PyTorch CUDA 缓存残留 | `gep-pytorch-cuda-cache-gpu-memory-leak.md` | ✅ 仍适用 |
| GPU 显存争用 | `gpu-memory-contention.md` | ✅ 仍适用 |
| BepiPred3 GPU 超时调优 | `gep-bepipred3-gpu-timeout-tuning.md` | ✅ 仍适用 |
| OmegaFold 同步推理阻塞 | `gep-omegafold-sync-inference-blocking.md` | ✅ 仍适用 |
| ToxinPred3 单线程挂死 | `gep-toxinpred3-concurrency-limit.md` | ✅ 仍适用 |
| TemStaPro 预筛减少 GPU 瓶颈 | `gep-temstapro-prescreen-gpu-bottleneck.md` | ✅ 仍适用 |
| 结构预测置信度级联 | `gep-pipeline-confidence-cascade.md` | ❌ 主流程已删除 |
| 流水线阶段编排与检查点 | `gep-pipeline-stage-orchestration.md` | ❌ 主流程已删除 |
| 微服务网络绑定策略 | `microservice-host-binding.md` | ✅ 仍适用 |
| 结构预测 Docker 模式 | `structure-service-pattern.md` | ❌ Docker 专属 |