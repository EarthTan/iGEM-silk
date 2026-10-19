---
name: Residual PyTorch CUDA Cache Process Occupying GPU Memory and Blocking Subsequent Services v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [pytorch, cuda, gpu-memory, memory-leak, cache, anoxpepred, esmfold]
validated: true
---

> English translation of [gep-pytorch-cuda-cache-gpu-memory-leak.md](gep-pytorch-cuda-cache-gpu-memory-leak.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Residual PyTorch CUDA Cache Process Occupying GPU Memory and Blocking Subsequent Services

## Experience

**Problem description**: The AnOxPePred microservice (a PyTorch model) ran and exited, but its residual process held about **34.5GB of GPU memory** (`nvidia-smi` still showed the `python` process). When ESMFold (needing ~17GB) was started afterward, the free memory was 48GB total minus 34.5GB = 13.5GB, less than the 17GB required, and yet **ESMFold hung silently** — no exception, no log entry, only `model_loaded=false`.

**Symptoms**:
- `nvidia-smi` showed 34.5GB of the 48GB occupied by a `python` process (AnOxPePred)
- The AnOxPePred container had actually stopped, but the process had not released its CUDA context
- The ESMFold `.cuda()` call failed silently (no `torch.cuda.OutOfMemoryError` raised)
- In the logs the ESMFold state was `model_loaded=false`, with no error stack
- Restarting the Docker container **does not release the GPU memory** (because the process belongs to the host PID namespace)

**Root cause**: Two levels:

1. **PyTorch CUDA cache allocator**: PyTorch's `torch.cuda` uses a caching memory allocator; even after the model is deleted and the Python object is GC'd, the CUDA context still caches the allocated GPU memory inside the process and does not return it to the OS immediately. This is PyTorch's designed behavior — it reduces cudaMalloc overhead.
2. **Docker does not isolate GPU processes**: With `--gpus all` and `nvidia/cuda` images, CUDA processes inside the container are visible in the host's `nvidia-smi`. After the container stops, if the process did not exit properly, the CUDA context keeps occupying GPU memory.

```python
# AnOxPePred service.py — root cause
model = YourPyTorchModel()  # loaded onto the GPU, occupies ~10GB
model.cuda()                # actual GPU memory allocation
# ... inference ...
# when the service stops: the Python process does not release the CUDA context correctly
# the PyTorch cache allocator retains ~34GB (including cache + fragmentation)
```

**Note**: 34.5GB is far larger than the model's actual parameter size (~10GB), because the PyTorch cache allocator retains every GPU memory block ever allocated, including intermediate activations and gradient caches.

### Solution

**Option 1: kill the residual process directly (adopted by this pipeline)**

```bash
# find the PID of the process corresponding to the AnOxPePred container
ps aux | grep anoxpepred  # or
nvidia-smi                 # check the PID occupying GPU memory

# kill the process (releases the CUDA context)
kill -9 <PID>
# or clean up all leftovers
ps aux | grep "python service.py" | grep -v grep | awk '{print $2}' | xargs kill -9
```

**Option 2: Docker configuration for automatic cleanup**

```yaml
# docker-compose.yml — add to the service definition
services:
  anoxpepred:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    # key: kill internal processes when the container exits
    stop_grace_period: 5s
    init: true  # use the tini init system to ensure zombie processes are reaped
```

**Option 3: Python-level GPU memory cleanup (auxiliary)**

```python
import torch
import gc

def cleanup_cuda():
    """Try to release CUDA GPU memory on service shutdown (not necessarily effective)"""
    gc.collect()
    torch.cuda.empty_cache()     # empty the PyTorch cache allocator
    torch.cuda.synchronize()     # wait for all CUDA streams to complete
    # note: empty_cache() does not necessarily return memory to the OS
```

**Option 4: process-level isolation (recommended)**

The most reliable approach is to ensure every GPU service runs in its own Docker container, using `docker stop` and `docker rm` to guarantee the process is SIGKILLed. Use `init: true` (tini) to ensure no residual child processes remain inside the container.

### Diagnosis Procedure

| Step | Command | Finding |
|------|------|------|
| 1. Check GPU memory | `nvidia-smi` | 34.5GB occupied by `python` |
| 2. Confirm process identity | `ps -p <PID> -o cmd=` | determine whether it belongs to a stopped container |
| 3. Check container state | `docker ps -a \| grep anoxpepred` | container already Exited |
| 4. Confirm it cannot be released | `docker stop` + `nvidia-smi` | memory not released |
| 5. Force kill | `kill -9 <PID>` + `nvidia-smi` | memory released ✅ |

### Environment Fingerprint

- **Task domain**: Chained GPU microservice calls, Docker container management
- **Input characteristics**: PyTorch models, multiple services sharing a GPU, Docker containers
- **Constraints**: Limited GPU memory (48GB); services must be started and stopped in sequence
- **Trigger pattern**: Not checking for residual processes after stopping a GPU container; multiple GPU services in the same Docker Compose project
- **Not applicable**: CPU-only services; non-PyTorch frameworks (TensorFlow has a similar problem but different behavior); each container exclusively owning a whole card (no contention when exclusive)

### Preventive Measures

1. **Start GPU services on demand**: In stages2, AnOxPePred is stopped once it is done being used, and `nvidia-smi` is checked after stopping to confirm the memory is released
2. **GPU services serialized**: Do not run multiple GPU-intensive containers at the same time
3. **Check GPU memory before starting ESMFold/OmegaFold for the first time**:

```python
import subprocess, json

def check_gpu_memory():
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
        capture_output=True, text=True
    )
    free_mb = int(result.stdout.strip().split('\n')[0])
    return free_mb  # requires > 18000 (17GB) before starting ESMFold
```

### Audit Record

- **Validation method**: Diagnosed and resolved during the stages2 production run
- **Test cases**:
  1. After AnOxPePred ran, `nvidia-smi` → 34.5GB occupied
  2. `docker stop anoxpepred` + `nvidia-smi` → still 34.5GB
  3. `kill -9 <PID>` + `nvidia-smi` → memory released
  4. ESMFold started successfully after cleanup → `model_loaded=true`
- **Success rate**: 100%
- **Limitations**: `torch.cuda.empty_cache()` at the Python level cannot guarantee that all GPU memory is returned to the OS. Process-level kill remains the most reliable approach.
