---
name: asyncio.gather 异常传播陷阱与任务隔离 v1.0
author: Claude Code
created: 2026-05-15
version: 1.0.0
tags: [asyncio, python, exception-handling, gather, concurrency, robustness]
validated: true
---

# Gene Capsule: asyncio.gather 异常传播陷阱与任务隔离

## Experience

**问题描述**: 在异步处理 90 个 construct 的 3D 结构预测任务时，使用 `asyncio.gather(*tasks)` 未设置 `return_exceptions=True`。当单个 construct 的任何一个协程抛出未捕获异常时，所有 90 个正在运行或等待的任务被立即取消，整个运行崩溃。

**错误现象**:
```
❌ 程序中断，无任何 construct 完成
Traceback... (某个 construct 的某种异常)
asyncio.gather 返回异常，程序退出
```

**根因**: `asyncio.gather()` 默认行为：当其中任一 task 抛出异常时，立即抛出该异常，并自动取消所有其他未完成的任务（通过 `task.cancel()`）。这是 asyncio 的设计决策——但在大规模批量任务中，这意味着一个任务的失败会连带摧毁全部工作。

### 解决方案

**双层隔离策略**:

第一层：外层 `asyncio.gather(return_exceptions=True)`

```python
# 将所有异常转为返回值，不会传播
tasks = [process_one(c) for c in constructs]
results = await asyncio.gather(*tasks, return_exceptions=True)

# 事后检查结果
for i, result in enumerate(results):
    if isinstance(result, Exception):
        log(f"   ❌ {constructs[i]['construct_id']} 异常: {result}")
    else:
        # 正常处理 result
        pass
```

第二层：内层每个任务独立 try/except 包装

```python
async def safe_process_one(c: dict) -> dict | None:
    try:
        return await process_one(c)
    except Exception as e:
        log(f"  ❌ {c.get('construct_id', '???')} 异常: {e}")
        import traceback
        log(f"     {traceback.format_exc()}")
        return None  # 返回 None 而不是异常

tasks = [safe_process_one(c) for c in constructs]
await asyncio.gather(*tasks, return_exceptions=True)
```

| 层级 | 保护范围 | 效果 |
|------|----------|------|
| 外层 `return_exceptions=True` | 全部任务 | 阻止 task.cancel() 传播 |
| 内层 try/except | 单个 construct 级别 | 提供详细日志 + 优雅降级 |

### 演化对比

| 版本 | 代码 | 结果 |
|------|------|------|
| ❌ 裸 gather | `asyncio.gather(*tasks)` | 1 个失败 → 全部 90 个被取消 |
| ⚠️ 仅 return_exceptions | `asyncio.gather(*tasks, return_exceptions=True)` | 异常仍会打乱结果与 task 的对齐 |
| ✅ 双层隔离 | try/except 包装 + return_exceptions | 优雅处理单个失败，其余 89 个正常运行 |

### Environment Fingerprint

- **任务域**: 批量异步任务处理（N ≥ 10），任务间相互独立
- **输入特征**: 每个任务耗时较长（分钟级），且任务数量多
- **约束条件**: 任务间无依赖，允许部分失败
- **触发模式**: 任意批量 `asyncio.gather` 调用
- **不适用**: 任务间有依赖关系的 DAG 执行（应使用 `asyncio.TaskGroup` 或 `asyncio.as_completed`）

### Audit Record

- **验证方式**: 构造测试 — 在 90 个任务中故意让第 2 个抛出异常
  - 裸 gather: 第 2 个崩溃 → 全部 90 个任务被取消
  - 双层隔离: 第 2 个记录异常返回 None，其余 89 个正常运行
- **生产确认**: 修复后 Round 5 完成 90/90，即使中间有单任务超时也未影响整体
- **局限性**: try/except 仅在协程内部有效，如果异常发生在 `__init__` 或 `__aenter__` 中仍需额外处理
