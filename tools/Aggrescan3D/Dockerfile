# Aggrescan3D 微服务 Docker 镜像
# ==============================
# 基于 ghcr.io/mamba-org/micromamba（GitHub Container Registry，国内可访问）
#
# 使用方式:
#   docker build -f tools/Aggrescan3D/Dockerfile -t igem-silk/aggrescan3d-api .
#   docker run --rm -p 8102:8102 igem-silk/aggrescan3d-api

FROM ghcr.io/mamba-org/micromamba:latest

LABEL org.opencontainers.image.title="Aggrescan3D API"
LABEL org.opencontainers.image.description="Aggrescan3D PDB aggregation propensity API — conda-based"
LABEL org.opencontainers.image.source="https://bitbucket.org/lcbio/aggrescan3d"

# 切换 root 安装系统包 + uv
USER root

# 安装 aggrescan3d（Python 2.7 环境）
RUN micromamba create -y -n a3d -c conda-forge -c lcbio python=2.7 aggrescan3d \
    && micromamba clean -afy

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY tools/template/ ./tools/template/
COPY tools/Aggrescan3D/ ./tools/Aggrescan3D/

WORKDIR /app/tools/Aggrescan3D
RUN uv sync

EXPOSE 8102
ENV PORT=8102
ENV AGGRESCAN_CONDA_ENV=/opt/conda/envs/a3d

CMD [".venv/bin/python", "service.py"]
