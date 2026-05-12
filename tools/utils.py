"""
GPU 环境检测 — 所有微服务共享。

同一份代码，Mac / Linux / Docker 三种环境都能跑，代码自己检测后端。
每个微服务在 load_model() 时调用一次，结果存入 self.gpu_info。

返回结构:
    {
        "backend": "gpu" | "mps" | "cpu",
        "gpu_count": int,
        "message": str,        # 人可读的摘要
        "details": [str, ...], # 各框架的详细检测结果
    }
"""

from __future__ import annotations


def detect_gpu() -> dict:
    """自动检测 PyTorch + TensorFlow 的 GPU 可用性，返回统一诊断信息。

    检测优先级: CUDA > MPS > CPU
    """
    gpu_count = 0
    backend = "cpu"
    details: list[str] = []

    # ── PyTorch ──
    try:
        import torch

        if torch.cuda.is_available():
            n = torch.cuda.device_count()
            gpu_count = max(gpu_count, n)
            backend = "gpu"
            details.append(f"PyTorch CUDA x{n}")
            for i in range(min(n, 4)):
                details.append(f"  GPU {i}: {torch.cuda.get_device_name(i)}")
        elif torch.backends.mps.is_available():
            if backend == "cpu":
                backend = "mps"
            details.append("PyTorch MPS (Apple GPU) — 注意: 仅 torch 内置操作可用，第三方库通常忽略 MPS")
    except ImportError:
        details.append("PyTorch not installed")
    except Exception as exc:
        details.append(f"PyTorch error: {exc}")

    # ── TensorFlow ──
    try:
        import tensorflow as tf

        if tf.test.is_built_with_cuda():
            try:
                gpus = tf.config.list_physical_devices("GPU")
            except Exception:
                gpus = []
            if gpus:
                n = len(gpus)
                gpu_count = max(gpu_count, n)
                backend = "gpu"
                details.append(f"TensorFlow CUDA x{n}: {[g.name for g in gpus]}")
            else:
                details.append("TensorFlow built with CUDA but no GPU found (check nvidia driver / container runtime)")
        else:
            details.append("TensorFlow CPU-only (pip install, no CUDA)")
    except ImportError:
        details.append("TensorFlow not installed")
    except Exception as exc:
        details.append(f"TensorFlow error: {exc}")

    # ── 组装结果 ──
    if not details:
        message = "No ML framework detected"
    elif backend == "gpu":
        message = f"GPU × {gpu_count}"
    elif backend == "mps":
        message = "Apple MPS (CPU fallback for most tools)"
    else:
        message = "CPU only"

    return {
        "backend": backend,
        "gpu_count": gpu_count,
        "message": message,
        "details": details,
    }


def detect_system() -> dict:
    """返回 /health 专用的系统环境信息。

    基于 detect_gpu()，补充 GPU 名称和显存等细节。

    GPU 环境:
        {"device": "gpu", "gpu_available": true, "gpu_name": "NVIDIA RTX 5880", "gpu_memory": "48 GB"}
    CPU 环境:
        {"device": "cpu", "gpu_available": false}
    """
    info = detect_gpu()
    result: dict = {
        "device": info["backend"],
        "gpu_available": info["backend"] == "gpu",
    }

    if result["gpu_available"]:
        try:
            import torch
            result["gpu_name"] = torch.cuda.get_device_name(0)
            total_mem = torch.cuda.get_device_properties(0).total_mem
            result["gpu_memory"] = f"{total_mem / (1 << 30):.0f} GB"
        except Exception:
            pass

    return result
