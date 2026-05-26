---
name: BepiPred3 GPU 并发与超时系统调优 v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [bepipred3, gpu, timeout, semaphore, concurrency, batch-processing]
validated: true
---

# Gene Capsule: BepiPred3 GPU 并发与超时系统调优

## Experience

**问题描述**: BepiPred3 GPU 服务在批量处理 300 个 construct（Round 4）和 15K 序列（Round 3）时，大量请求因超时而失败。首次运行 300 个 construct 仅 50/300 成功（17% 成功率），其余全部 httpx 超时。

**症状**:
- httpx `ReadTimeout` 异常，即使设置 timeout=300s
- 部分请求在服务端已完成计算，但客户端收不到响应
- 服务日志显示 GPU 利用率正常，推理进行中
- 失败模式不一致：同一 construct 重试有时成功有时失败

**根因**: 三层嵌套的超时问题：

1. **并发过高（Semaphore=5）**: GPU 服务单请求 ~115s/50-seq 批，Semaphore=5 允许 5 个并发 → 排队请求在 300s 内等不到执行槽
2. **超时不足（300s）**: 单批 50 条约 115s，5 并发时第 5 个请求需等 4×115=460s + 115s=575s，远超 300s 超时
3. **docker-proxy 叠加效应**: 长耗时请求走 docker-proxy（127.0.0.1）时出现间歇性 keep-alive 挂死（见 gep-docker-container-bridge-ip.md），进一步降低有效吞吐

**三个独立问题的协同作用**:
```
Semaphore=5 + 300s timeout + docker-proxy
    → 5 请求同时进入 GPU
    → GPU 串行处理（单卡），4 个在排队
    → 排队的第 3 个起已在 300s 外
    → 前 2 个完成返回，但 docker-proxy 可能挂死
    → 第 3-5 个必然超时
    → 轮到这个请求时 Semaphore 已释放 → 新请求进入 → 继续超时
    → 最终只有少量短序列成功
```

### 解决方案

**三维度系统调优**，三个参数联动调整：

| 参数 | 原值 | 新值 | 理由 |
|------|------|------|------|
| Semaphore | 5 | **1** | GPU 串行推理，并发 >1 只会堆积排队 |
| 超时 | 300s | **600s** | 单批 115s，排队 0s（Semaphore=1），需要 2× 安全裕度 |
| Batch Size | 100 | **50** | 小批次减少单请求耗时，降低超时概率 |

```python
# round04_fix_bepipred3.py — 修复后的参数
BATCH_SIZE = 50          # 原来 100
BEPIPRED_SEMAPHORE = 1   # 原来 5
BEPIPRED_TIMEOUT = 600   # 原来 300
```

**关键洞察**: GPU 服务是单卡串行推理，Semaphore >1 **永远不会提升吞吐**，只会增加排队请求的超时概率。Semaphore=1 + 长超时 是最优配置。

### 诊断方法

| 步骤 | 命令/方法 | 判断 |
|------|-----------|------|
| 1. 检查服务日志 | `docker compose logs bepipred3` | GPU 利用率、推理时间 |
| 2. 统计成功率 | 对比请求数 vs 成功响应数 | 17% 极低 |
| 3. 测试单请求 | 单条 curl 看耗时 | 确认 ~115s/50-seq |
| 4. 分析超时模式 | 失败的请求是否总是在排队 | 确认是排队超时而非执行超时 |
| 5. 检查网络层 | 切换 bridge IP 直连 | 排除 docker-proxy 干扰 |

### 最终效果

- Round 3（15K 序列）: 全部完成，权重写入 composite score
- Round 4（300 constructs）: 150/150 有效（去掉 ESMFold-only 后），0 错误
- 成功率: **17% → 100%**

### Environment Fingerprint

- **任务域**: GPU 微服务批量推理，asyncio 客户端
- **输入特征**: 单次推理 60-120s，GPU 串行执行
- **约束条件**: 单 GPU 卡，显存有限，不可水平扩展
- **触发模式**: 客户端并发数 > GPU 串行执行能力 + 超时不足
- **不适用**: CPU 多线程服务（Semaphore 可 >1）；分布式 GPU 集群；推理时间 <10s 的服务

### 关联经验

- `gep-docker-container-bridge-ip.md` — docker-proxy 长连接挂死，同一问题的网络层面
- `gep-omegafold-sync-inference-blocking.md` — OmegaFold 同样 GPU 串行，同样 Semaphore=1

### Audit Record

- **验证方式**: stages2 Round 3 + Round 4 生产运行
- **测试用例**:
  1. Semaphore=5, timeout=300s → 50/300 成功（17%）
  2. Semaphore=1, timeout=300s → 约 210/300 成功（70%, 仍受 docker-proxy 影响）
  3. Semaphore=1, timeout=600s, bridge IP → 300/300 成功（100%）
- **成功率**: 100%
- **局限性**: 未在服务端层面优化推理速度。如果单批推理时间 >600s（更长序列），需进一步调大 timeout。
