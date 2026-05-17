---
name: PyTorch CUDA cache 残留进程占用 GPU 显存阻塞后续服务 v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [pytorch, cuda, gpu-memory, memory-leak, cache, anoxpepred, esmfold]
validated: true
---

# Gene Capsule: PyTorch CUDA cache 残留进程占用 GPU 显存阻塞后续服务

## Experience

**问题描述**: AnOxPePred 微服务（PyTorch 模型）运行后退出，但其进程残留占用了约 **34.5GB GPU 显存**（`nvidia-smi` 显示 `python` 进程仍存在）。后续启动 ESMFold（需 ~17GB）时，尽管总显存 48GB 减去 34.5GB = 13.5GB 不足 17GB，但 **ESMFold 静默挂死**——不抛异常、不写日志，仅 `model_loaded=false`。

**症状**:
- `nvidia-smi` 显示 48GB 显存中 34.5GB 被 `python` 进程占用（AnOxPePred）
- 实际 AnOxPePred 容器已停止，但进程未释放 CUDA context
- ESMFold `.cuda()` 调用静默失败（不抛出 `torch.cuda.OutOfMemoryError`）
- 日志中 ESMFold 状态为 `model_loaded=false`，无错误堆栈
- 重启 Docker 容器 **不释放显存**（因为进程属于 host PID namespace）

**根因**: 两个层面：

1. **PyTorch CUDA cache 分配器**: PyTorch 的 `torch.cuda` 使用内存缓存分配器（caching memory allocator），即使模型被删除、Python 对象被 GC，CUDA context 仍在进程中缓存已分配的显存，不立即返回给 OS。这是 PyTorch 的设计行为——减少 cudaMalloc 开销。
2. **Docker 未隔离 GPU 进程**: 使用 `--gpus all` 和 `nvidia/cuda` 镜像时，容器内的 CUDA 进程在宿主机 `nvidia-smi` 中可见。容器停止后，如果进程未正确退出，CUDA context 持续占用显存。

```python
# AnOxPePred service.py — 问题根源
model = YourPyTorchModel()  # 加载到 GPU，占用 ~10GB
model.cuda()                # 实际显存分配
# ... 推理 ...
# 服务停止时：Python 进程未正确释放 CUDA context
# PyTorch cache 分配器保留 ~34GB（含缓存 + 碎片化）
```

**注意**: 34.5GB 远大于模型实际参数大小（~10GB），因为 PyTorch cache 分配器会保留所有曾经分配过的显存块，包括中间激活值、梯度缓存等。

### 解决方案

**方案一：直接 kill 残留进程（本流程采用）**

```bash
# 查找 AnOxPePred 容器对应的进程 PID
ps aux | grep anoxpepred  # 或
nvidia-smi                 # 查看占用显存的 PID

# kill 进程（会释放 CUDA context）
kill -9 <PID>
# 或清理所有残留
ps aux | grep "python service.py" | grep -v grep | awk '{print $2}' | xargs kill -9
```

**方案二：Docker 配置自动清理**

```yaml
# docker-compose.yml — 在服务定义中添加
services:
  anoxpepred:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    # 关键：容器退出时杀死内部进程
    stop_grace_period: 5s
    init: true  # 使用 tini init 系统，确保僵尸进程被回收
```

**方案三：Python 层显存清理（辅助）**

```python
import torch
import gc

def cleanup_cuda():
    """在服务关闭时尝试释放 CUDA 显存（不一定有效）"""
    gc.collect()
    torch.cuda.empty_cache()     # 清空 PyTorch cache 分配器
    torch.cuda.synchronize()     # 等待所有 CUDA 流完成
    # 注意：empty_cache() 不一定将显存返回给 OS
```

**方案四：进程级隔离（推荐）**

最可靠的方案是确保每个 GPU 服务在独立的 Docker 容器中运行，通过 `docker stop` 和 `docker rm` 确保进程被 SIGKILL。使用 `init: true`（tini）确保容器内无残留子进程。

### 诊断流程

| 步骤 | 命令 | 发现 |
|------|------|------|
| 1. 检查 GPU 显存 | `nvidia-smi` | 34.5GB 被 `python` 占用 |
| 2. 确认进程身份 | `ps -p <PID> -o cmd=` | 判断是否属于已停止容器 |
| 3. 检查容器状态 | `docker ps -a \| grep anoxpepred` | 容器已 Exited |
| 4. 确认无法释放 | `docker stop` + `nvidia-smi` | 显存不释放 |
| 5. 强制 kill | `kill -9 <PID>` + `nvidia-smi` | 显存释放 ✅ |

### Environment Fingerprint

- **任务域**: GPU 微服务链式调用，Docker 容器管理
- **输入特征**: PyTorch 模型，多服务共享 GPU，Docker 容器
- **约束条件**: GPU 显存有限（48GB），服务需要按顺序启动和停止
- **触发模式**: 停止 GPU 容器后未检查进程残留；多 GPU 服务在同一个 Docker Compose 项目中使用
- **不适用**: CPU-only 服务；非 PyTorch 框架（TensorFlow 有类似问题但行为不同）；每个容器独占整卡（独享不会出现争用）

### 预防措施

1. **按需启动 GPU 服务**: 在 stages2 中，AnOxPePred 用完就停，停后检查 `nvidia-smi` 确认显存释放
2. **GPU 服务 serialized**: 不同时运行多个 GPU 密集型容器
3. **首次启动 ESMFold/OmegaFold 前做显存检查**:

```python
import subprocess, json

def check_gpu_memory():
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    free_mb = int(result.stdout.strip().split('\n')[0])
    return free_mb  # 需要 > 18000 (17GB) 才启动 ESMFold
```

### Audit Record

- **验证方式**: stages2 生产运行中排查解决
- **测试用例**:
  1. AnOxPePred 运行后 `nvidia-smi` → 34.5GB 占用
  2. `docker stop anoxpepred` + `nvidia-smi` → 仍 34.5GB
  3. `kill -9 <PID>` + `nvidia-smi` → 显存释放
  4. 清理后 ESMFold 启动成功 → `model_loaded=true`
- **成功率**: 100%
- **局限性**: `torch.cuda.empty_cache()` 在 Python 层不能保证释放所有显存给 OS。最可靠的方式仍然是进程级 kill。
