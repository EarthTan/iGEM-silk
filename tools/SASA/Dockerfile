# SASA 微服务 Docker 镜像
# ========================
# FreeSASA + Biopython 的轻量 CPU 镜像。
# 无需 GPU，纯 Python 计算 (Lee-Richards 算法)。
#
# 使用方式:
#   cd tools/SASA
#   docker build -t igem-silk/sasa .
#   docker run -p 8101:8101 igem-silk/sasa

FROM python:3.11-slim

LABEL org.opencontainers.image.title="SASA"
LABEL org.opencontainers.image.description="溶剂可及表面积分析 — FreeSASA Lee-Richards"
LABEL org.opencontainers.image.source="https://freesasa.github.io/"

# FreeSASA 需要编译依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev python3-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    freesasa biopython numpy \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 复制项目骨架
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/SASA/ ./tools/SASA/

WORKDIR /app/tools/SASA

EXPOSE 8101
ENV PORT=8101

CMD ["python", "service.py"]
