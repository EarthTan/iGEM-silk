FROM nvidia/cuda:12.1.0-devel-ubuntu22.04

LABEL org.opencontainers.image.title="ESMFold API"
LABEL org.opencontainers.image.description="ESMFold 3D 结构预测 API — Meta FAIR"
LABEL org.opencontainers.image.source="https://github.com/facebookresearch/esm"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3.11-dev python3-pip build-essential ninja-build git curl \
    && rm -rf /var/lib/apt/lists/*

# 全量安装（含 openfold CUDA 编译）
RUN python3.11 -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python3.11 -m pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cu121 && \
    python3.11 -m pip install --no-cache-dir --no-build-isolation \
    https://github.com/aqlaboratory/openfold/archive/refs/tags/v2.2.0.tar.gz && \
    python3.11 -m pip install --no-cache-dir \
    biotite biopython einops ml-collections dm-tree modelcif omegaconf \
    fastapi "uvicorn[standard]" pydantic "fair-esm>=2.0.0"

WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/ESMFold/ ./tools/ESMFold/

ENV TORCH_HOME=/app/tools/models/fair-esm/
VOLUME /app/tools/models

WORKDIR /app/tools/ESMFold
EXPOSE 8203
ENV PORT=8203
CMD ["python3.11", "service.py"]
