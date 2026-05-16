---
name: OmegaFold 同步推理阻塞事件循环与并发控制 v1.0
author: Claude Code
created: 2026-05-15
version: 1.0.0
tags: [omegafold, async, event-loop, blocking, semaphore, structure-service]
validated: true
---

# Gene Capsule: OmegaFold 同步推理阻塞事件循环与并发控制

## Experience

**问题描述**: OmegaFold 微服务的 `predict_structure()` 方法直接在 `async def` 中调用 PyTorch `model(input_data)` 进行同步推理（耗时 90-120s）。这阻塞了 uvicorn 的 asyncio 事件循环，导致服务在处理一个请求期间完全无法响应任何其他请求（/health、/status/{job_id}、/result/{job_id} 全部挂起）。

**症状**:
- 并发 ≥2 时第二个 construct 的 POST /predict/async 超时（httpx 30s timeout）
- curl 从宿主机请求 health 端点挂起，但 `docker exec` 在容器内请求正常
- 日志中 OmegaFold 条目全部标记为 "N/A (30s)"，因为 POST 阶段就超时了

**根因** (templates/structure_service.py):
```python
# tools/template/structure_service.py — 问题代码
async def predict_structure(self, sequence: str) -> StructureResult:
    # ... 准备数据 ...
    result = self.model(input_data, predict_with_confidence=True)  # 同步阻塞！90-120s
    # ... 处理结果 ...
```
`self.model(...)` 是 PyTorch CUDA 推理，在 async def 中调用时阻塞整个事件循环。uvicorn 是单线程事件循环，无法在等待期间处理其他请求。

### 解决方案

**方案一：客户端 Semaphore（本流程采用）**

```python
# main/stages2/round05_3d.py
OMEGAFOLD_CONCURRENCY = 1   # 全局串行化
omegafold_sem = asyncio.Semaphore(OMEGAFOLD_CONCURRENCY)

async def timed_predict(service: str, seq: str, cid: str, timeout: float) -> dict:
    if service == "omegafold" and omegafold_sem is not None:
        async with omegafold_sem:     # 保证同时只有 1 个 OmegaFold 请求
            result = await client.predict_structure_async(...)
    else:
        result = await client.predict_structure_async(...)
    return result
```

| 参数 | 值 | 说明 |
|------|-----|------|
| OMEGAFOLD_CONCURRENCY | 1 | 全局并发限制 |
| 超时 | 14400s (4h) | OmegaFold 单条 ~6min，足够 |
| 轮询间隔 | 30s | 标准结构预测轮询 |

**方案二：服务端修复（推荐，但本次未实施）**

将阻塞推理放入 `asyncio.get_event_loop().run_in_executor()` 或 `concurrent.futures.ThreadPoolExecutor`，释放事件循环：

```python
# 推荐方案：在 service.py 中使用线程池
import asyncio
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=1)  # GPU 推理仍应串行化

async def predict_structure(self, sequence: str) -> StructureResult:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        executor,
        lambda: self.model(input_data, predict_with_confidence=True)
    )
    # ... 处理结果 ...
```

### Environment Fingerprint

- **任务域**: 结构预测微服务，async 模式的 FastAPI/uvicorn 服务
- **输入特征**: PyTorch/TensorFlow 等深度学习框架的同步推理调用
- **约束条件**: GPU 推理不可取消、单次 60-120s 完成
- **触发模式**: 异步 Job 模式（POST /predict/async → 轮询 GET /status/{job_id}）
- **不适用**: CPU 推理 <5s 的轻量模型（影响不大）；已使用 `run_in_executor` 的服务

### Audit Record

- **验证方式**: 生产运行 90 个 construct，加 Semaphore 前 OmegaFold 成功率 0/2（首 2 个就超时），加后 90/90 成功
- **测试用例**:
  1. CONCURRENCY=2, 无 Semaphore → 第 2 个 OmegaFold 在 30s POST 阶段超时 → N/A
  2. CONCURRENCY=2, OmegaFold_CONCURRENCY=1 → 90 个全部完成，OmegaFold 串行执行（~6min/条 × 90 = ~9h，与 ESMFold 并行不额外耗时）
- **成功率**: 90/90 (100%)
- **局限性**: 客户端 Semaphore 只是绕过了问题，服务端事件循环仍然被阻塞（只是不让并发请求进来）。推荐在 `service.py` 层面修复。
