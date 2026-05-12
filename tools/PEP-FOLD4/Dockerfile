# PEP-FOLD4 微服务 Docker 镜像
# ===============================
# API 层轻量镜像，通过 Docker CLI 调用官方 PEP-FOLD4 镜像。
# PEP-FOLD4 是 CPU 运行的粗粒度力场 + 蒙特卡洛采样，无需 GPU。
#
# 使用方式:
#   cd tools/PEP-FOLD4
#   docker build -t igem-silk/pepfold4-api .
#   docker run --rm -p 8202:8202 \
#       -v /var/run/docker.sock:/var/run/docker.sock \
#       igem-silk/pepfold4-api
#
# 前提条件:
#   - PEP-FOLD4 Docker 镜像已加载 (从 RPBS OwnCloud 获取)
#     docker load < pepfold4.tar
#   - Docker 守护进程可访问

FROM python:3.11-slim

LABEL org.opencontainers.image.title="PEP-FOLD4 API"
LABEL org.opencontainers.image.description="PEP-FOLD4 肽从头结构预测 API — Docker 封装"
LABEL org.opencontainers.image.source="https://bioserv.rpbs.univ-paris-diderot.fr/services/PEP-FOLD4/"

# 安装 Docker CLI（使用 Debian 源，避免 download.docker.com 被墙）
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker-cli \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 复制项目骨架
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/PEP-FOLD4/ ./tools/PEP-FOLD4/

WORKDIR /app/tools/PEP-FOLD4

EXPOSE 8202
ENV PORT=8202

CMD ["python", "service.py"]
