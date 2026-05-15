# Stages3 技术强制规范

> 版本: v1.0 — 2026-05-15
> 依据: stages2 执行中暴露的全部技术问题
> 强制性: 本文件所有规范均为强制要求，Pipeline 代码评审时逐条检查

---

## 一、Docker 强制使用规范

### 背景

stages2 执行中多次出现"本应使用 Docker 却直接在宿主机跑微服务"的情况。每次在宿主机跑都导致：
- 重新安装 Python 环境和依赖（uv sync + 解决版本冲突）
- 模型文件路径不一致（容器路径 vs 宿主路径）
- conda 环境和系统 Python 的环境污染
- 调试时浪费大量时间在环境问题上

### 强制规则

**规则 1**: 所有微服务在生产运行时必须通过 Docker Compose 启动，不得在宿主机直接运行 `python service.py`。

**规则 2**: 开发阶段可以在宿主机调试单个微服务，但调试完成后必须用 Docker 重新验证一次。

**规则 3**: 每次启动新轮次（或从断点恢复）时，先执行:
```bash
cd tools && docker compose --profile gpu --profile cpu up -d
```
确认所有服务 health check 通过后，再启动 pipeline 脚本。

**规则 4**: 每个微服务的 Dockerfile 必须在 `tools/template/` 的模板基础上构建，不得从头写 Dockerfile。

### 强制机制（Pipeline 代码层面）

在 pipeline 脚本入口处增加 Docker 健康检查：

- 启动任何 stage 之前，先对所有依赖的微服务调用 health check
- 如果任一服务不可达，检查其是否在 Docker 中运行（通过检查 /proc/1/cgroup 或环境变量）
- 如果服务未在 Docker 中运行，打印警告并退出，而不是自动回退到宿主机模式

### 模型缓存管理

Docker 部署时共享模型缓存的绑定挂载路径已在 docker-compose.yml 中定义：

```yaml
volumes:
  - ../models:/root/models  # 共享模型缓存
```

宿主机模型文件统一放在 `tools/models/` 下，Docker 容器内自动挂载。不要在容器内重新下载模型。

---

## 二、微服务层必须修复的技术问题

以下问题在 stages2 中被发现但只做了客户端侧绕行（workaround），未在服务端修复。stages3 中必须在微服务层彻底修复。

### 问题 1: OmegaFold 同步推理阻塞事件循环

**现象**: OmegaFold 的 `predict_structure()` 在 `async def` 中直接调用 `self.model(input_data)`——一个耗时 90-120 秒的 PyTorch CUDA 同步推理。这会阻塞 uvicorn 的事件循环，导致服务在处理一个请求期间完全无法响应其他任何请求（health check、状态查询等全部挂起）。

**当前状态**: 客户端用 Semaphore(1) 做串行化，绕过了并发请求问题。但服务端的事件循环仍然被阻塞。

**修复要求**: 将推理调用移入 `run_in_executor(ThreadPoolExecutor)`，释放事件循环：

```
service.py 中:
  1. 创建一个 ThreadPoolExecutor(max_workers=1)，因为 GPU 推理仍然需要串行化
  2. predict_structure() 中: await loop.run_in_executor(executor, lambda: self.model(...))
  3. 其他路由（/health, /status/{job_id}）在推理期间仍然可响应
```

**影响**: 即使当前并发限制为 1，修复后也可以为未来的多请求场景和更好的 health check 可用性做准备。

### 问题 2: Docker 桥接 IP 直连（网络层稳定性）

**现象**: 通过 `127.0.0.1:PORT`（docker-proxy）访问容器服务时，httpx 的 keep-alive 长连接出现间歇性挂死。尤其是在容器重启后，docker-proxy 不清理旧的 TCP 连接。同一时刻 `docker exec` 在容器内 curl 却完全正常。

**当前状态**: 客户端用 `docker inspect` 获取 bridge IP 后直连容器网络，绕过了 docker-proxy。

**修复要求**: 在客户端库 `main/client.py` 中实现自动化的 bridge IP 解析：

```
1. 在 ServiceClient 初始化时，提供可选的 auto_bridge 模式
2. 如果启用，对每个已知的 Docker 服务自动检测 bridge IP
3. 检测到 bridge IP 后，替换 URL 中的 127.0.0.1 为 bridge IP
4. 如果检测失败（非 Docker 环境或网络异常），回退到原始 URL
5. 缓存 bridge IP 到内存，每次连接前检查是否需要刷新
```

注意：此修复在客户端层而非服务端层，因为问题出在 Docker 网络层，不在服务代码中。

### 问题 3: ToxinPred3 模型加载线程安全问题

**现象**: ToxinPred3 基于 sklearn ExtraTreesClassifier，其预测方法在多线程并发时出现挂死。`asyncio.wait_for` 超时机制对此无效，因为挂死发生在 C 扩展层面，asyncio 无法中断。

**当前状态**: 客户端用小批次（batch_size=10）+ 连续超时检测 + 重启策略。

**修复要求**: 在 ToxinPred3 服务层增加全局推理锁：

```
在 service.py 中:
  1. 在模型初始化后创建一个 threading.Lock()
  2. predict_impl() 进入时获取锁，退出时释放
  3. 这不影响吞吐量（单个请求的处理时间不受锁影响）
  4. 但防止多个请求同时进入 sklearn 的 C 扩展层
```

### 问题 4: asyncio.gather 异常传播导致级联崩溃

**现象**: `asyncio.gather(*tasks)` 默认行为是只要一个 task 抛出未捕获异常，就立即取消所有其他正在运行或等待的任务。在批量处理数百个 construct 时，单个 task 的异常导致全部任务被取消，整个运行中断。

**当前状态**: 客户端使用双层隔离（外层 `return_exceptions=True` + 内层 try/except）。

**修复要求**: 在客户端库或 stage 脚本中建立标准化的批量任务执行模式：

```
标准模式:
  1. 定义 safe_task_wrapper() 统一包装，包含完整异常处理和日志记录
  2. 批量执行时始终使用 return_exceptions=True
  3. 执行后统一检查结果，收集异常信息但不中断流程
  4. 将异常计数纳入运行报告，而非阻断运行
```

### 问题 5: PDB 批处理 API 响应格式不一致

**现象**: SASA 和 Aggrescan3D 的 batch 端点返回的 JSON 结构中，单个结果中 score 字段的位置与单条 API 不一致。batch 返回在顶层，单条在 result.score 中。

**修复要求**: 统一批量和单条的响应格式：

```
单条响应: {"result": {"score": 0.5, ...}, ...}
批量响应: {"results": [{"score": 0.5, ...}, ...]}
```

即：批量结果中每个条目的结构与单条结果的 `result` 字段结构一致。

---

## 三、并发与资源管理规范

### GPU 内存管理

**现象**: 多个 GPU 微服务（ESMFold、OmegaFold、BepiPred-3.0、pLM4CPPs 等）共享 24G 显存。同时加载多个模型会导致 CUDA OOM。

**规范**:
1. 服务层：每个微服务在 `load_model()` 后立即执行 `torch.cuda.empty_cache()`，并设置 `torch.backends.cudnn.benchmark = True`
2. 编排层：docker-compose profiles 已按 GPU/CPU 分组，确保不同时启动 GPU 密集型服务
3. 运行时：通过环境变量 `CUDA_VISIBLE_DEVICES` 控制 GPU 可见性（虽然单 GPU 下作用有限）
4. 使用 `tools/utils.py` 中的 `detect_gpu()` 做统一的 GPU 检测

### 并发控制

| 服务类型 | 推荐并发数 | 说明 |
|---------|-----------|------|
| FastaToolService 子类 | 10 | 轻量序列预测，CPU 密集型 |
| StructureService 子类 | 1 | GPU 推理，串行执行 |
| PdbScoringService 子类 | 10 | 轻量 PDB 分析 |
| ToxinPred3（特殊） | 1 | sklearn 线程安全限制 |

### 超时策略

| 服务 | 超时 | 说明 |
|------|------|------|
| 轻量序列服务 | 30s | 单条预测 |
| 批量序列服务 | 120s | batch 预测 |
| 结构预测（ESMFold） | 600s | 单条结构预测 |
| 结构预测（OmegaFold） | 14400s | OmegaFold 较慢 |
| PDB 评估 | 60s | 轻量计算 |

---

## 四、网络稳定性规范

### Docker-proxy 规避

通过 `127.0.0.1:PORT` 访问容器服务的模式在本环境中被证实不可靠（见问题 2）。

**规范**:
1. 所有通过 `main/config.py:service_url()` 获取的 URL 应支持 bridge IP 覆盖
2. 在 pipeline 启动时执行一次网络检测，确定集群内所有服务的可达方式
3. 记录网络拓扑到日志：`[NET] SASA: 172.17.0.5:8101 (bridge)`
4. 如果 bridge IP 检测失败，回退到 127.0.0.1 并警告

### 失败重试策略

所有 HTTP 调用应遵循:
1. 首次失败 → 等待 1s，重试
2. 二次失败 → 等待 5s，重试
3. 三次失败 → 记录错误并跳过（不阻塞整体流程）
4. 对于结构预测等长任务，重试策略不同：task 级别的超时和重试，而非 HTTP 请求级别的重试

---

## 五、存储与 I/O 规范

### 数据库优先原则

stages3 中所有中间结果必须写入数据库，不再依赖 CSV 文件做数据传递：

| 存储对象 | 存储方式 | 保留策略 |
|---------|---------|---------|
| 候选肽序列 + 元数据 | DuckDB `candidates` 表 | 整个生命周期 |
| 各阶段分数 | DuckDB 各阶段表 | 整个生命周期 |
| 最终排名 | DuckDB `final_ranking` 表 | 整个生命周期 |
| PDB 文件 | 文件系统 `output3/pdb/` | 整个生命周期 |
| 日志文件 | 文件系统 `output3/logs/` | 按轮次归档 |
| 报告 | 文件系统 `output3/reports/` | 永久保留 |

### 检查点规范

每个阶段必须支持从上次中断处恢复：
1. 阶段开始时记录 `checkpoint_start` 到数据库
2. 阶段结束时记录 `checkpoint_done` 到数据库
3. 恢复运行时查询 `checkpoint_done`，跳过已完成阶段
4. 对于大批次处理（如 Stage 2 的数百万条评分），应支持更细粒度的中间检查点

---

## 六、CI / 代码质量规范

### 最终检查清单

每次提 PR 前逐条检查：

- [ ] 所有微服务是否在 Docker 中运行？
- [ ] Docker health check 是否全部通过？
- [ ] 是否有 `run_in_executor` 未处理的阻塞调用？
- [ ] 批量任务是否使用了 `return_exceptions=True`？
- [ ] 数据库连接是否在每个线程独立？
- [ ] 超时设置是否合理？
- [ ] 日志是否记录了关键步骤和错误？

---

## 附录：stages2 技术问题汇总

| # | 问题 | 影响 | 修复状态 | 见问题 # |
|---|------|------|---------|---------|
| 1 | OmegaFold sync blocking | 事件循环阻塞，health check 不可用 | 客户端绕行，服务端待修复 | 1 |
| 2 | Docker proxy 连接不稳定 | httpx 长连接间歇挂死 | 客户端绕行，待自动化 | 2 |
| 3 | ToxinPred3 sklearn 线程安全 | 高并发挂死 | 客户端绕行，服务端待修复 | 3 |
| 4 | asyncio.gather 级联崩溃 | 单任务异常导致全部取消 | 客户端已修复（双层隔离） | 4 |
| 5 | Batch API 响应格式不一致 | 解析错误，0/90 成功 | 已修复，格式待统一 | 5 |
| 6 | Docker Compose 构建原子性 | 一个失败全部回滚 | 需要分批构建 | — |
| 7 | 宿主机直接运行微服务 | 环境不一致，调试耗时 | 本文档强制规则 | — |
