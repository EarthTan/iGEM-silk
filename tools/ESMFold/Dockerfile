# ESMFold 微服务 Docker 镜像
# ===============================
# ESMFold 是原生 Python 模型（非 DinD），直接在进程内加载执行。
# GPU (CUDA) 必需，CPU 环境自动降级。
#
# 使用方式:
#   cd tools/ESMFold
#   docker build -t igem-silk/esmfold .
#   docker run --rm --gpus all -p 8203:8203 igem-silk/esmfold
#
# 前提条件:
#   - NVIDIA 驱动 >= 525 + nvidia-container-toolkit
#   - 显存 >= 16 GB

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

LABEL org.opencontainers.image.title="ESMFold API"
LABEL org.opencontainers.image.description="ESMFold 3D 结构预测 API — Meta FAIR"
LABEL org.opencontainers.image.source="https://github.com/facebookresearch/esm"

# 安装 Python 和编译工具（openfold 需要 nvcc 编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
# 使用 PyTorch CUDA 12.1 wheel 确保 GPU 支持
RUN python3.11 -m pip install --no-cache-dir \
    "fair-esm[esmfold]>=3.0.0" \
    torch --index-url https://download.pytorch.org/whl/cu121 \
    biotite \
    fastapi "uvicorn[standard]" pydantic

# 复制项目代码
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/ESMFold/ ./tools/ESMFold/

# 共享模型缓存目录
ENV TORCH_HOME=/app/tools/models/fair-esm/
VOLUME /app/tools/models

WORKDIR /app/tools/ESMFold

EXPOSE 8203
ENV PORT=8203

CMD ["python3.11", "service.py"]
