---
name: ToxinPred3 单线程并发限制与挂死恢复策略 v1.0
author: Claude Code
created: 2026-05-15
version: 1.0.0
tags: [toxinpred3, sklearn, concurrency, timeout, recovery, extra-trees]
validated: true
---

# Gene Capsule: ToxinPred3 单线程并发限制与挂死恢复策略

## Experience

**问题描述**: ToxinPred3 (sklearn ExtraTreesClassifier) 在处理大批量肽序列时会周期性挂死（100% CPU，无响应）。挂死后所有并发连接堆积，最终导致全部批次失败。

**发生环境**: ToxinPred3 微服务（FastAPI + uvicorn），CPU 推理，无 GPU。后端模型 sklearn ExtraTreesClassifier（AAC+DPC，420 维特征）。服务作为 `tools/ToxinPred3/` 下的独立进程运行。

### 根因分析

1. **sklearn ExtraTreesClassifier 单线程限制**：ExtraTreesClassifier 的 `predict()` 底层调用 C 扩展（`sklearn.ensemble._forest`），单线程运行。当处理特定序列时可能触发无限循环或死锁（在树遍历中陷入），导致进程 100% CPU 永不返回
2. **并发请求导致 CLOSE_WAIT 堆积**：使用 `asyncio.Semaphore(N)` 并发 ≥2 时，挂死请求使 uvicorn worker 阻塞，后续请求排队。客户端超时（httpx）断开连接后，服务端 socket 进入 CLOSE_WAIT 状态积累，最终所有新请求失败
3. **asyncio.wait_for 不可靠**：Python `asyncio.wait_for(coro, timeout=120)` 在 httpx 等待 socket 响应时无法可靠取消。原因是 httpx 的 `await` 点可能不响应 `CancelledError`（取决于内部实现状态）。同步版 `requests.post(..., timeout=120)` 使用内核级 socket 超时，可靠得多

### 解决方案

最终采用 **同步 + 小批次 + 持续超时 + 服务重启** 策略：

| 策略 | 参数 | 原理 |
|------|------|------|
| 同步 requests | `timeout=120` | 内核 socket 超时，比 asyncio 取消可靠 |
| 小批次 | 200 条/批（原 1000） | 单批挂死最多损失 200 条 |
| 连续超时检测 | 连续 5 批超时触发重启 | 清除挂死 worker |
| 串行执行 | 单连接单请求 | 避免 socket 堆积 |
| 跳过继续 | 超时后标记 None 继续下一批 | 不影响整体流程 |

### 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 批次大小 | 200 | 原 1000，减小后降低单批风险 |
| 超时 | 120s | 正常 16s/批，120s 足够但能截断挂死 |
| 连续超时阈值 | 5 | 触发服务 `/restart` 端点 |
| 客户端类型 | `requests` (同步) | 替代 `httpx` (async)，超时更可靠 |
| 总体吞吐 | ~12 seq/s | 受 ExtraTrees 单线程限制 |

### 演进记录

1. **并发 Semaphore=10**: 100/100 批次全部错误，CLOSE_WAIT 堆积
2. **并发 Semaphore=2**: 前半程 OK，~80K 处服务挂死导致大面积超时
3. **串行 httpx**: 7 批 OK，第 8 批挂死，`asyncio.wait_for` 120s 无法截断（持续 30 分钟无响应）
4. **同步 requests + 200批 + 120s超时**: 500 批全部完成，100,000/100,000 有效，0 超时

### 适用场景

任何使用 sklearn 非线程安全模型（ExtraTrees、RandomForest 等）的微服务，在大批量推理时出现间歇性挂死：

- 优先使用同步请求 + 系统级超时（`requests` > `asyncio.wait_for`）
- 小批次（200–500）降低单次风险
- 连续失败触发服务热重启
- 串行化避免 socket 堆积

### 相关文件

- `main/stages2/round02_toxinpred3_sync.py` — 最终成功方案
- `main/stages2/round02_toxinpred3_robust.py` — asyncio 版（超时不可靠，弃用）
- `main/stages2/round02_toxinpred3_serial.py` — 串行 httpx 版（超时仍不可靠）
- `main/stages2/round02_recover_toxinpred3.py` — 初始并发版
- `tools/ToxinPred3/service.py` — ToxinPred3 微服务入口
