# AlphaFold3 微服务 Docker 镜像
# ===============================
# 这是 API 层的轻量镜像，通过 Docker CLI 调用官方 alphafold3 镜像。
# 运行时需要挂载 Docker socket 以访问宿主机的 AF3 容器。
#
# 使用方式:
#   cd tools/AlphaFold3
#   docker build -t igem-silk/alphafold3-api .
#   docker run --rm -p 8201:8201 \
#       -v /var/run/docker.sock:/var/run/docker.sock \
#       -v /path/to/af3/models:/root/models \
#       -v /path/to/af3/databases:/root/public_databases \
#       -e AF3_MODEL_DIR=/root/models \
#       -e AF3_DATABASE_DIR=/root/public_databases \
#       igem-silk/alphafold3-api
#
# 前提条件:
#   - Ubuntu 宿主机 (Linux 内核)
#   - NVIDIA 驱动 >= 525 + nvidia-container-toolkit
#   - AlphaFold3 Docker 镜像已 pull: docker pull alphafold3
#   - 模型参数和数据库已下载

FROM python:3.11-slim

LABEL org.opencontainers.image.title="AlphaFold3 API"
LABEL org.opencontainers.image.description="AlphaFold3 3D 结构预测 API — Docker 封装"
LABEL org.opencontainers.image.source="https://github.com/google-deepmind/alphafold3"

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
COPY tools/AlphaFold3/ ./tools/AlphaFold3/

WORKDIR /app/tools/AlphaFold3

EXPOSE 8201
ENV PORT=8201

CMD ["python", "service.py"]
