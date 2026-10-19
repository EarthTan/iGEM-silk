---
name: asyncio.gather Exception Propagation Pitfalls and Task Isolation v1.0
author: Claude Code
created: 2026-05-15
version: 1.0.0
tags: [asyncio, python, exception-handling, gather, concurrency, robustness]
validated: true
---

> English translation of [gep-asyncio-gather-exception-safety.md](gep-asyncio-gather-exception-safety.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: asyncio.gather Exception Propagation Pitfalls and Task Isolation

## Experience

**Problem description**: While asynchronously processing 3D structure prediction tasks for 90 constructs, `asyncio.gather(*tasks)` was used without `return_exceptions=True`. When any single coroutine for one construct raised an uncaught exception, all 90 running or waiting tasks were cancelled immediately and the whole run crashed.

**Error symptoms**:
```
❌ program aborted, no construct completed
Traceback... (some exception from some construct)
asyncio.gather returns the exception, program exits
```

**Root cause**: `asyncio.gather()`'s default behavior: when any task raises an exception, it immediately raises that exception and automatically cancels all other unfinished tasks (via `task.cancel()`). This is an asyncio design decision—but in large-scale batch tasks it means one task's failure destroys all the work with it.

### Solution

**Two-layer isolation strategy**:

Layer one: the outer `asyncio.gather(return_exceptions=True)`

```python
# Turn all exceptions into return values; they are not propagated
tasks = [process_one(c) for c in constructs]
results = await asyncio.gather(*tasks, return_exceptions=True)

# Check the results afterwards
for i, result in enumerate(results):
    if isinstance(result, Exception):
        log(f"   ❌ {constructs[i]['construct_id']} exception: {result}")
    else:
        # process result normally
        pass
```

Layer two: wrap each inner task in its own try/except

```python
async def safe_process_one(c: dict) -> dict | None:
    try:
        return await process_one(c)
    except Exception as e:
        log(f"  ❌ {c.get('construct_id', '???')} exception: {e}")
        import traceback
        log(f"     {traceback.format_exc()}")
        return None  # return None instead of the exception

tasks = [safe_process_one(c) for c in constructs]
await asyncio.gather(*tasks, return_exceptions=True)
```

| Layer | Scope of protection | Effect |
|------|----------|------|
| Outer `return_exceptions=True` | All tasks | Prevents task.cancel() from propagating |
| Inner try/except | Individual construct level | Detailed logging + graceful degradation |

### Evolution Comparison

| Version | Code | Result |
|------|------|------|
| ❌ bare gather | `asyncio.gather(*tasks)` | 1 failure → all 90 cancelled |
| ⚠️ return_exceptions only | `asyncio.gather(*tasks, return_exceptions=True)` | Exceptions still scramble the alignment between results and tasks |
| ✅ two-layer isolation | try/except wrapper + return_exceptions | Handles a single failure gracefully; the other 89 run normally |

### Environment Fingerprint

- **Task domain**: Batch asynchronous task processing (N ≥ 10), tasks independent of one another
- **Input characteristics**: Each task takes a long time (minutes) and there are many tasks
- **Constraints**: No dependencies between tasks; partial failure is acceptable
- **Trigger pattern**: Any batched `asyncio.gather` call
- **Not applicable**: DAG execution where tasks depend on each other (use `asyncio.TaskGroup` or `asyncio.as_completed` instead)

### Audit Record

- **Validation method**: A constructed test—deliberately let the 2nd of 90 tasks raise an exception
  - bare gather: the 2nd crashes → all 90 tasks are cancelled
  - two-layer isolation: the 2nd logs the exception and returns None; the other 89 run normally
- **Production confirmation**: After the fix, Round 5 completed 90/90; even with an individual task timeout in the middle, the overall run was unaffected
- **Limitations**: try/except is only effective inside the coroutine; if an exception occurs in `__init__` or `__aenter__`, extra handling is still needed
