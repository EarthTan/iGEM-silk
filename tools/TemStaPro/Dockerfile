FROM pytorch/pytorch:2.0.0-cuda11.7-cudnn8-runtime

LABEL maintainer="iGEM-silk"
LABEL description="TemStaPro — Protein thermostability prediction (ProtT5-XL + MLP)"

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
RUN pip install --no-cache-dir \
    transformers>=4.40.0 \
    sentencepiece>=0.1.96 \
    fastapi>=0.115.0 \
    uvicorn[standard]>=0.30.0 \
    httpx>=0.27.0

# Copy service code
COPY tools/utils.py ./tools/utils.py
COPY tools/TemStaPro/service.py ./tools/TemStaPro/
COPY tools/TemStaPro/prottrans.py ./tools/TemStaPro/
COPY tools/TemStaPro/mlp.py ./tools/TemStaPro/
COPY tools/template/ ./tools/template/

WORKDIR /app/tools/TemStaPro

ENV PORT=8010
ENV HOST=0.0.0.0

# HF cache + classifier models mounted at runtime
VOLUME ["/root/.cache/huggingface", "/app/models"]

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8010/health || exit 1

EXPOSE 8010

CMD ["python", "service.py"]
