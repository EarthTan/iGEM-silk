# OmegaFold 微服务 Docker 镜像
# ===============================
# OmegaFold 是原生 Python 模型，直接在进程内加载执行。
# GPU (CUDA) 推荐，CPU/MPS 也支持（自动检测）。
#
# 使用方式:
#   cd tools/OmegaFold
#   docker build -t igem-silk/omegafold .
#   docker run --rm --gpus all -p 8204:8204 igem-silk/omegafold
#
# 前提条件:
#   - NVIDIA 驱动 >= 525 + nvidia-container-toolkit (GPU 模式)

FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

LABEL org.opencontainers.image.title="OmegaFold API"
LABEL org.opencontainers.image.description="OmegaFold 3D 结构预测 API — HeliXon"
LABEL org.opencontainers.image.source="https://github.com/HeliXonProtein/OmegaFold"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3-pip \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# OmegaFold 从 GitHub 安装，依赖 torch + biopython
RUN pip install --no-cache-dir \
    torch \
    biopython \
    fastapi "uvicorn[standard]" pydantic \
    && pip install --no-cache-dir \
    git+https://github.com/HeliXonProtein/OmegaFold.git

WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/OmegaFold/ ./tools/OmegaFold/

ENV OMEGAFOLD_CACHE=/app/tools/models/omegafold
VOLUME /app/tools/models

WORKDIR /app/tools/OmegaFold

EXPOSE 8204
ENV PORT=8204

CMD ["python3.11", "service.py"]
