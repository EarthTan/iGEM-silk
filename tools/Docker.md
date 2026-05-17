# Docker Operations Guide — iGEM-silk

> 本文件整合了 `.agents/learnings/` 中所有 Docker 相关的经验教训（23 个胶囊），
> 作为项目 Docker 部署、运行和故障排查的唯一参考。
>
> **最后更新**: 2026-05-18

---

## 1. 核心原则

### 1.1 所有服务必须用 Docker 运行

生产环境中的所有微服务**必须**通过 Docker Compose 运行。禁止直接在宿主机上用 `python service.py` 启动。

理由：
- 每个微服务有独立的 Python 环境和系统依赖，宿主机无法同时满足所有依赖版本
- 模型文件路径在不同环境中硬编码，直接在宿主机运行会因路径不对而报错
- Docker 环境已在构建时验证，直接运行等于跳过所有验证
- 宿主机上残留的进程会占用 GPU 显存，影响后续 Docker 服务

唯一例外：**开发调试**时可以在宿主机运行单个服务，但调试完成后必须在 Docker 中重新验证。

### 1.2 按需启动，用完即关

**不要一次性启动所有 16 个微服务。** 每个 pipeline step 只启动该 step 实际依赖的服务。

- GPU 服务之间会争夺显存（48GB 总量，单个 GPU 服务可能占用 6-34GB）
- 不必要的服务浪费系统资源（CPU、内存、网络连接）
- 服务越多，健康检查链越长，故障排查越复杂

每个 step 启动哪些服务由 `main/stages3/service_map.py` 定义，通过 `docker_utils.py` 的 `ensure_services()` 统一管理。

### 1.3 禁止裸机执行

| ❌ 禁止 | ✅ 正确 |
|---------|--------|
| `cd tools/AnOxPePred && python service.py` | `docker compose --profile gpu up -d anoxpepred` |
| `cd tools/SASA && python service.py` | `docker compose --profile cpu up -d sasa` |
| 修改 `uvicorn.run(host="0.0.0.0")` 来控制暴露范围 | 在 `docker-compose.yml` 的 `ports:` 中控制暴露范围 |

**特别说明**：所有服务代码中 `uvicorn.run(host="0.0.0.0")` 是**正确且必须的**。Docker 容器内部通信要求绑定 `0.0.0.0`，暴露范围由 Compose 端口映射控制：
- `"8001:8001"` — 局域网可访问（默认）
- `"127.0.0.1:8001:8001"` — 仅本机可访问
永远不要修改服务代码中的 host 绑定。

---

## 2. 服务总览

### 2.1 微服务清单

共 19 个微服务，分为两组 profile：

#### GPU services (`--profile gpu`)

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

> **注意**：`alphafold3` 是 Docker 套娃包装，它本身不占 GPU，但会通过 Docker socket 启动真正的 AF3 镜像。

#### CPU services (`--profile cpu`)

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

### 2.2 Profile 实际分布（与规划文档的差异）

早期规划假设大多数评分服务是 CPU，但 `docker-compose.yml` 的实际配置不同：

| 实际 GPU | 实际 CPU |
|----------|---------|
| anoxpepred, bepipred3, plm4cpps, graphcpp, temstapro, mhcflurry, hemopi2 | toxinpred3, algpred2, sodope, tipred |

这意味着大多数 pipeline step 需要同时启动 `gpu` 和 `cpu` 两个 profile。

### 2.3 Step 依赖地图

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

---

## 3. Docker Compose 用法

### 3.1 构建与启动（正确顺序）

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

### 3.2 常见陷阱

#### 陷阱 1：dockerfile 路径是相对于 build context 的

```yaml
# docker-compose.yml 中：
build:
  context: ..          # context = tools/..
  dockerfile: tools/AnOxPePred/Dockerfile   # ✅ 正确
  # dockerfile: Dockerfile                   # ❌ 错误 — 会在 context 根目录找
```

配置后用 `grep 'dockerfile:' docker-compose.yml` 验证。

#### 陷阱 2：COPY 遗漏共享依赖

几乎所有服务的 Dockerfile 都依赖项目根目录的共享文件。遗漏的 COPY 不会导致构建失败，但会在运行时抛出 `ModuleNotFoundError`。

**必须 COPY 的文件**：
```dockerfile
COPY tools/utils.py ./tools/utils.py           # GPU 检测工具
COPY tools/template/ ./tools/template/         # FastAPI 模板
```

**审计命令**：
```bash
for f in tools/*/Dockerfile; do
  if ! grep -q 'COPY.*utils\.py' "$f" 2>/dev/null; then
    echo "MISS utils.py: $f"
  fi
  if ! grep -q 'COPY.*template' "$f" 2>/dev/null; then
    echo "MISS template: $f"
  fi
done
```

#### 陷阱 3：`latest` 标签导致 CI 突发失败

```dockerfile
# ❌ 不要用 latest
FROM ghcr.io/astral-sh/uv:latest

# ✅ 固定版本
FROM ghcr.io/astral-sh/uv:0.4.30
```

`latest` 在不同时间点拉取不同版本。上游发布新版本后，你的构建会在没有做任何代码更改的情况下突然失败。

#### 陷阱 4：Linux 文件名大小写

macOS 的文件系统（APFS）默认不区分大小写，Linux（ext4/xfs）区分。
- 在 macOS 上 `Tipred` 和 `TIPred` 指向同一目录
- 在 Linux 上它们指向不同目录

```bash
# 用这个命令确认真实目录名，不要目测
ls -1 tools/
```

影响范围：Dockerfile `COPY`、docker-compose `dockerfile` 路径、Dockerfile 内的 `WORKDIR`。

#### 陷阱 5：Python 命名空间遮蔽（最隐蔽的错误）

项目根目录的 `tools/` 是命名空间包（无 `__init__.py`）。
如果微服务内部有一个同名的 `tools/` 子目录（有 `__init__.py`），
Python 会优先找到本地包，导致 `from tools.template.fasta_service import ...` 抛出 `ModuleNotFoundError`。

**诊断**：
```bash
python -c "import tools; print(tools.__path__)"
```

**修复**：微服务内部代码目录绝不能命名为 `tools/`。例如 `mv tools/AnOxPePred/tools tools/AnOxPePred/anoxpepred_sdk`。

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

### 3.3 基础镜像选型

本项目的 Dockerfile 使用 7 种基础镜像模式：

| 模式 | 基础镜像 | 适用场景 | 服务示例 |
|------|---------|---------|---------|
| **A** | `pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime` | GPU PyTorch | BepiPred3, HemoPI2, MHCflurry, pLM4CPPs, TemStaPro, GraphCPP |
| **B** | `nvidia/cuda:12.1.0-*-ubuntu22.04` | 原始 CUDA + 自定义 Python | ESMFold (devel), OmegaFold (runtime) |
| **C** | `python:3.11-slim` | CPU 服务 | ToxinPred3, SASA, AlgPred2, Tipred |
| **D** | `tensorflow/tensorflow:2.21.0-gpu` | TensorFlow GPU | AnOxPePred |
| **E** | `python:3.13-slim` | 最新 Python | SoDoPE |
| **F** | `ghcr.io/mamba-org/micromamba:latest` | Conda 环境 / Python 2.7 | Aggrescan3D |
| **G** | `python:3.11-slim` + Docker socket | Docker 套娃包装 | AlphaFold3, PEP-FOLD4, Waveflow |

**CUDA 版本矩阵**：
- CUDA 12.4 + cuDNN 9: PyTorch base image (Pattern A)
- CUDA 12.1: structure prediction (Pattern B)
- Torch index: `https://download.pytorch.org/whl/cu121`

### 3.4 GPU 服务管理

#### 健康检查不同步

GPU 服务的健康检查通过并不意味预测一定能成功。模型可能在容器启动后才开始加载到 GPU，健康检查的超时期限（`start_period`）需要足够长。

`docker-compose.yml` 中的健康检查模式：
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

#### 桥接 IP 直连（绕过 docker-proxy）

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

**修复**：获取桥接 IP 并直接访问：
```python
import subprocess, json
result = subprocess.run(
    ["docker", "inspect", "omegafold", "--format", '{{json .NetworkSettings.Networks}}'],
    capture_output=True, text=True
)
networks = json.loads(result.stdout)
bridge_ip = networks.get("bridge", {}).get("IPAddress")
# 设置环境变量: export OMEGAFOLD_HOST=<bridge_ip>
```

`docker_utils.py` 中的 `detect_bridge_ip()` 自动完成此操作。

#### GPU 显存检查

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

## 4. 服务生命周期管理

### 4.1 启动前检查清单

每个 pipeline step 执行前应确认：

```
□ Docker daemon 是否运行？  → docker info
□ 所需 GPU 服务显存是否充足？ → nvidia-smi
□ 所需 CPU 服务是否有端口冲突？ → ss -tnp | grep <PORT>
□ Docker Compose 文件是否存在？ → ls tools/docker-compose.yml
□ 之前 step 的 GPU 进程是否已清理？ → ps aux | grep python
```

### 4.2 按需启动协议

使用 `docker_utils.py` 的统一入口 `ensure_services()`：

```python
from main.stages3.docker_utils import ensure_services
from main.stages3.service_map import get_step_services

# 1. 查询当前 step 需要哪些服务
info = get_step_services("step1")

# 2. 启动并等待就绪
health = ensure_services(
    info["services"],
    profiles=info["profiles"],
    timeout=120.0,
)

# 3. 检查不可用的服务
unavailable = [s for s, h in health.items() if not h["available"]]
if unavailable:
    sys.exit(f"服务不可用: {unavailable}")
```

**API 速查**：

| 函数 | 作用 | 幂等 |
|------|------|------|
| `ensure_services(names, profiles, timeout, skip_docker)` | 主入口：启动 → 健康检查 → 缓存 | ✅ 缓存 120s |
| `check_docker_daemon()` | 检查 Docker 是否运行 | ❌ |
| `detect_bridge_ip(container)` | 获取容器桥接 IP | ✅ 缓存 |
| `clear_cache()` | step 切换时清空缓存 | — |
| `wait_for_services(services, timeout, poll_interval)` | 轮询等待 /health | ❌ |

**幂等机制**：同一服务连续调用 `ensure_services` 直接返回缓存结果，不会重复启动或重复健康检查。缓存：
- `_health_cache`: 服务健康状态（step 内有效）
- `_bridge_cache`: 容器桥接 IP（进程内有效）
- `_started_profiles`: 已启动的 profile（避免重复 `docker compose up`）

**Step 切换时清空缓存**：
```python
from main.stages3.docker_utils import clear_cache
clear_cache()  # 切换到新 step 前调用
```

### 4.3 运行中监控

```bash
# 查看服务日志
docker compose logs -f anoxpepred

# 查看所有服务状态
docker compose ps

# 查看 GPU 使用情况
watch -n 2 nvidia-smi

# 查看容器资源占用
docker stats --no-stream
```

**超时策略**（按服务类型）：

| 服务类型 | 超时 | 说明 |
|---------|------|------|
| 轻量评分（anoxpepred, algpred2 等） | 30s | 大多数请求 < 5s |
| BepiPred3 | 600s | GPU 串行，单批 ~115s（50条） |
| OmegaFold | 14400s（4h） | 单结构 90-120s，同步阻塞 |
| ESMFold | 600s | 单结构 ~120s |
| ToxinPred3 | 120s | socket 超时，asyncio 无法中断 |

### 4.4 关机与清理

#### 4.4.1 正常关闭

```bash
# 停止当前 step 使用的服务
docker compose stop anoxpepred algpred2

# 停止所有服务
docker compose down

# 停止并删除卷（谨慎——会删模型缓存）
docker compose down -v
```

#### 4.4.2 GPU 显存释放（==第 4 号坑==）

**`docker stop` 不能释放 GPU 显存。** 如果 GPU 进程属于宿主机 PID 命名空间，容器停止后 CUDA context 仍然占用显存。

AnOxPePred 尤其严重——即使进程退出，PyTorch 缓存分配器会保留曾分配过的所有 CUDA 内存块（最多 ~34GB）。

**正确的 GPU 显存释放流程**：
```bash
# 1. 找到残留的 Python 进程
ps aux | grep anoxpepred

# 2. 强制杀死
kill -9 <PID>

# 3. 确认显存已释放
nvidia-smi
```

**预防措施**：
- `docker-compose.yml` 中设置 `init: true`（tini init 进程，防止僵尸进程）
- `stop_grace_period: 5s`（快速终止）
- 启动新 GPU 服务前执行 `nvidia-smi` 确认显存
- **不同 step 之间务必检查是否有残留 GPU 进程**

#### 4.4.3 Step 切换标准流程

```
1. 停止当前 step 的服务：docker compose stop <services>
2. 检查 GPU 显存：nvidia-smi（如有残留 → kill -9）
3. 清空 docker_utils 缓存：clear_cache()
4. 启动新 step 的服务：ensure_services(...)
5. 确认新服务健康
```

---

## 5. 故障排查手册

### 5.1 Docker 构建失败

**症状**：`docker compose build` 失败，或构建通过但启动失败。

**排查步骤**：
1. 查看构建日志：`docker compose build <service> 2>&1 | tail -50`
2. 区分构建阶段 vs 运行阶段错误
3. 检查基础镜像是否可拉取（中国网络可能不通）
4. 检查 COPY 路径是否正确（大小写、相对路径）
5. 批量审计所有 Dockerfile 的常见问题：

```bash
# 审计脚本——一次收集所有问题
echo "=== dockerfile 路径 ==="
grep 'dockerfile:' docker-compose.yml

echo "=== COPY 遗漏 ==="
for f in tools/*/Dockerfile; do
  if ! grep -q 'COPY.*utils\.py' "$f"; then echo "MISS utils.py: $f"; fi
  if ! grep -q 'COPY.*template' "$f"; then echo "MISS template: $f"; fi
done

echo "=== 基础镜像 ==="
grep '^FROM' tools/*/Dockerfile

echo "=== WORKDIR ==="
grep 'WORKDIR' tools/*/Dockerfile

echo "=== 大小写敏感问题 ==="
ls -1 tools/
```

### 5.2 Docker Hub 不可达（中国网络）

**症状**：`docker pull` 超时，`docker compose build` 在 `FROM` 行挂死。

**解决方案 A — 配置镜像加速器**：
```json
// /etc/docker/daemon.json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```
```bash
sudo systemctl restart docker
```

**注意**：Daocloud 镜像有白名单，不在白名单的镜像（如 `ghcr.io/mamba-org/micromamba`）会被拒绝。此时需从原始源（如 GHCR）直接拉取。

**解决方案 B — 切换到原生执行**：
当 Docker 构建持续失败时，可以回退到宿主机原生 conda/pip 环境：
```bash
# 例如 Aggrescan3D 的回退
conda install -c lcbio aggrescan3d
export AGGRESCAN_CONDA_ENV=aggrescan3d
```
通过环境变量驱动切换，不修改代码。但**原生执行仅作临时回退**，Docker 化仍需修复。

### 5.3 容器健康但请求挂死（docker-proxy bug）

**症状**：服务健康检查通过，但长时间运行的预测请求间歇性挂死——客户端收不到响应，服务端实际上已完成。

**诊断三步法**：
```bash
# 1. 宿主机 curl —— 可能挂死
timeout 10 curl http://127.0.0.1:8002/predict -X POST ...

# 2. 容器内 curl —— 正常
docker exec bepipred3 curl http://localhost:8002/predict -X POST ...

# 3. 桥接 IP curl —— 正常（确认是 docker-proxy 问题）
BRIDGE_IP=$(docker inspect bepipred3 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
curl http://${BRIDGE_IP}:8002/predict -X POST ...
```

**根因**：docker-proxy（dockerd 的用户态 TCP 代理）在处理 keep-alive 连接时存在 bug——连接池状态不同步、重启后 TCP 连接未清理、高并发下 epoll 竞争条件。

**修复**：使用桥接 IP 直连，通过 `{SERVICE}_HOST` 环境变量注入。
`docker_utils.detect_bridge_ip()` 可自动获取桥接 IP。

**适用范围**：仅在宿主机访问容器时受影响。Docker Compose 内部服务间通信使用 DNS 解析，不受影响。

### 5.4 GPU 显存不足

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

**JAX 的 CUDA 初始化时机**（陷阱）：JAX 在容器启动时初始化 CUDA，而不是在模型加载时。这意味着健康检查通过时显存可能已经不够，但不会报错。预测时才会因 `RuntimeError: No supported devices found` 或 `OutOfMemoryError` 而失败。

### 5.5 服务挂死

#### ToxinPred3（sklearn 单线程挂死）

**症状**：ToxinPred3 进程 CPU 100%，端口无响应。`asyncio.wait_for` 超时不能中断（C 扩展不受 Python 信号控制）。

**最终解决方案**（经过多轮迭代）：
- 使用同步 `requests` 代替 `httpx`（socket 超时由内核处理，可中断）
- 批次大小：200（从 1000 减少）
- 超时：120s
- 连续 5 批超时时调用 `/restart` 端点
- 完全串行化（单连接，单请求）

参见 `main/stages2/round02_toxinpred3_sync.py`。

#### OmegaFold（同步推理阻塞事件循环）

**症状**：OmegaFold 的 `self.model(input_data)` 是同步 PyTorch CUDA 调用（90-120s），在 `async def` 中直接调用会阻塞 uvicorn 事件循环。在此期间 `/health`、`/status/{job_id}`、`/result/{job_id}` 全部挂起。

**客户端修复**：`asyncio.Semaphore(1)` 串行化请求。
**服务端推荐修复**（尚未实施）：将推理移入 `run_in_executor(ThreadPoolExecutor(max_workers=1), ...)`。

### 5.6 Python 命名空间遮蔽

**症状**：`ModuleNotFoundError: No module named 'tools.template'`，但 `tools/template/` 确实存在且已被 COPY。

**诊断**：
```bash
# 在容器内运行
docker exec -it <container> python -c "import tools; print(tools.__path__)"
# 输出类似：['/app/tools/AnOxPePred/tools'] ← 错误的路径！
# 应该是：['/app/tools']
```

**修复**：微服务内部代码目录绝不能命名为 `tools/`。

### 5.7 Linux 大小写敏感导致的构建失败

**症状**：在 macOS 上构建通过，推到 Linux 服务器上构建失败。错误信息为 `COPY failed: file not found`。

**排查**：
```bash
# macOS 和 Linux 上分别执行
ls -1 tools/<可疑目录>

# 检查 docker-compose.yml 中引用的路径是否与真实目录名匹配
grep 'dockerfile:' docker-compose.yml
ls -1 tools/
```

### 5.8 Docker-outside-Docker 路径问题

**症状**：通过 Docker socket 启动子容器的服务（AlphaFold3, PEP-FOLD4）找不到挂载卷——容器内的路径在宿主机上不存在。

**根因**：`docker run --volume` 的源路径由**宿主机 Docker 守护进程**解析，不是由 API 容器解析。

**修复**：使用双路径——宿主机路径（docker socket 用）和容器内路径（健康检查用）：
```yaml
# docker-compose.yml
environment:
  AF3_MODEL_DIR: /root/models           # 容器内路径（健康检查用）
  AF3_MODEL_HOST_DIR: /home/lenovo/af_models  # 宿主机路径（docker.sock 用）
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
  - /usr/bin/docker:/usr/bin/docker      # 挂载 docker CLI，不在容器内安装
```

---

## 6. 速查命令表

### 构建

| 命令 | 说明 |
|------|------|
| `cd tools` | 所有 Docker 操作在 tools/ 下执行 |
| `docker compose --profile cpu build` | 构建所有 CPU 服务 |
| `docker compose --profile gpu build` | 构建所有 GPU 服务 |
| `docker compose build anoxpepred` | 构建单个服务 |
| `docker compose --no-ansi build 2>&1 \| tail -50` | 查看构建最后 50 行日志 |

### 启动/停止

| 命令 | 说明 |
|------|------|
| `docker compose --profile gpu up -d` | 启动所有 GPU 服务 |
| `docker compose --profile cpu up -d` | 启动所有 CPU 服务 |
| `docker compose up -d anoxpepred algpred2` | 启动指定服务 |
| `docker compose stop anoxpepred` | 停止指定服务 |
| `docker compose down` | 停止并移除所有容器 |
| `docker compose restart anoxpepred` | 重启服务 |

### 监控

| 命令 | 说明 |
|------|------|
| `docker compose ps` | 查看服务状态 |
| `docker compose logs -f anoxpepred` | 查看实时日志 |
| `nvidia-smi` | 查看 GPU 显存 |
| `watch -n 2 nvidia-smi` | 实时监控 GPU |
| `docker stats --no-stream` | 查看容器资源占用 |
| `ss -tnp \| grep <PORT>` | 查看端口占用 |

### 容器内调试

| 命令 | 说明 |
|------|------|
| `docker exec -it anoxpepred bash` | 进入容器 shell |
| `docker exec anoxpepred curl localhost:8001/health` | 容器内健康检查 |
| `docker inspect anoxpepred --format '{{json .NetworkSettings.Networks}}'` | 查看网络配置 |

### 排查

| 命令 | 说明 |
|------|------|
| `docker inspect anoxpepred \| jq '.[0].State'` | 查看容器状态详情 |
| `docker logs anoxpepred --tail 100` | 查看最后 100 行日志 |
| `ps aux \| grep python` | 查找残留 Python 进程 |
| `kill -9 <PID>` | 强制释放 GPU 显存 |
| `docker system df` | 查看磁盘占用 |
| `docker builder prune` | 清理构建缓存 |

---

## 附录：经验胶囊索引

本文件的内容来自以下 `.agents/learnings/` 中的经验胶囊，如需查看完整上下文请参阅原文：

| 主题 | 胶囊文件 |
|------|---------|
| Docker Compose 原子性回滚 | `docker/compose-atomic-build.md` |
| 批量故障审计 | `docker/batch-failure-audit.md` |
| Dockerfile COPY 遗漏 | `docker/dockerfile-copy-audit.md` |
| dockerfile 路径相对于 context | `docker/dockerfile-path-compose.md` |
| latest 标签版本不确定性 | `docker/latest-tag-pinning.md` |
| Linux 大小写敏感 | `docker/linux-case-sensitivity.md` |
| Python 命名空间遮蔽 | `docker/python-namespace-shadowing.md` |
| slim 缺少 C 编译依赖 | `docker/slim-image-build-deps.md` |
| Docker Hub 中国镜像 | `docker/docker-hub-china-mirror.md` |
| Docker-outside-Docker 路径 | `docker/docker-outside-docker-paths.md` |
| 容器内 Docker CLI 安装 | `docker/docker-cli-in-container.md` |
| 桥接 IP 直连 | `gep-docker-container-bridge-ip.md` |
| Docker 不可达时原生回退 | `gep-docker-native-hybrid.md` |
| PyTorch CUDA 缓存残留 | `gep-pytorch-cuda-cache-gpu-memory-leak.md` |
| GPU 显存争用 | `gpu-memory-contention.md` |
| BepiPred3 GPU 超时调优 | `gep-bepipred3-gpu-timeout-tuning.md` |
| OmegaFold 同步推理阻塞 | `gep-omegafold-sync-inference-blocking.md` |
| ToxinPred3 单线程挂死 | `gep-toxinpred3-concurrency-limit.md` |
| TemStaPro 预筛减少 GPU 瓶颈 | `gep-temstapro-prescreen-gpu-bottleneck.md` |
| 结构预测置信度级联 | `gep-pipeline-confidence-cascade.md` |
| 流水线阶段编排与检查点 | `gep-pipeline-stage-orchestration.md` |
| 微服务网络绑定策略 | `microservice-host-binding.md` |
| 结构预测 Docker 模式 | `structure-service-pattern.md` |
