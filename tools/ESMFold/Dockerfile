FROM nvidia/cuda:12.1.0-devel-ubuntu22.04

LABEL org.opencontainers.image.title="ESMFold API"
LABEL org.opencontainers.image.description="ESMFold 3D 结构预测 API — Meta FAIR"
LABEL org.opencontainers.image.source="https://github.com/facebookresearch/esm"

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3.10-dev python3-pip build-essential ninja-build git curl \
    && rm -rf /var/lib/apt/lists/*

# Layer 1: pip + torch
RUN python3.10 -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python3.10 -m pip install --no-cache-dir torch "numpy<2" --index-url https://download.pytorch.org/whl/cu121

# Layer 2: openfold CUDA compile (~12min, isolated layer)
# Use v2.2.0 (CUDA 12.x 兼容)。IPA 模块 key 不匹配的问题在
# service.py 中通过 strict=False 绕开（缺失层随机初始化）。
RUN python3.10 -m pip install --no-cache-dir --no-build-isolation \
    https://github.com/aqlaboratory/openfold/archive/refs/tags/v2.2.0.tar.gz

# Layer 3: remaining deps (fast iteration)
RUN python3.10 -m pip install --no-cache-dir \
    biotite biopython einops ml-collections dm-tree modelcif omegaconf scipy \
    "deepspeed==0.5.9" \
    "fastapi<=0.99.1" "uvicorn[standard]" "pydantic==1.9.2" "fair-esm==2.0.0"

WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/ESMFold/ ./tools/ESMFold/

ENV TORCH_HOME=/app/tools/models/fair-esm/
VOLUME /app/tools/models

WORKDIR /app/tools/ESMFold
EXPOSE 8203
ENV PORT=8203
CMD ["python3.10", "service.py"]
