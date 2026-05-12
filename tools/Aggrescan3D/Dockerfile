# Aggrescan3D 微服务 Docker 镜像
# ==============================
# API 层轻量镜像，通过 Docker CLI 调用原作者的 lcbio/a3d_server 镜像。
# Aggrescan3D 本体是 Python 2.7 工具，因此不安装到本服务的 Python 3 环境。
#
# 使用方式:
#   docker build -f tools/Aggrescan3D/Dockerfile -t igem-silk/aggrescan3d-api .
#   docker run --rm -p 8102:8102 \
#       -v /var/run/docker.sock:/var/run/docker.sock \
#       igem-silk/aggrescan3d-api
#
# 前提条件:
#   docker pull lcbio/a3d_server

FROM python:3.11-slim

LABEL org.opencontainers.image.title="Aggrescan3D API"
LABEL org.opencontainers.image.description="Aggrescan3D PDB aggregation propensity API — Docker wrapper"
LABEL org.opencontainers.image.source="https://bitbucket.org/lcbio/aggrescan3d"

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 安装 Docker CLI（使用 Debian 源，避免 download.docker.com 被墙）
RUN apt-get update && apt-get install -y --no-install-recommends \
    docker-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY tools/template/ ./tools/template/
COPY tools/Aggrescan3D/ ./tools/Aggrescan3D/

WORKDIR /app/tools/Aggrescan3D
RUN uv sync

EXPOSE 8102
ENV PORT=8102
ENV A3D_IMAGE=lcbio/a3d_server

CMD [".venv/bin/python", "service.py"]
