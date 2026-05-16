# Aggrescan3D 微服务 Docker 镜像
# ==============================
# 基于 continuumio/miniconda2 安装 aggrescan3d，直接调用 aggrescan 命令。
#
# 使用方式:
#   docker build -f tools/Aggrescan3D/Dockerfile -t igem-silk/aggrescan3d-api .
#   docker run --rm -p 8102:8102 igem-silk/aggrescan3d-api

FROM continuumio/miniconda2:latest

LABEL org.opencontainers.image.title="Aggrescan3D API"
LABEL org.opencontainers.image.description="Aggrescan3D PDB aggregation propensity API — conda-based"
LABEL org.opencontainers.image.source="https://bitbucket.org/lcbio/aggrescan3d"

# 安装 aggrescan3d
RUN conda install -y -c lcbio aggrescan3d && conda clean -afy

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app
COPY tools/template/ ./tools/template/
COPY tools/Aggrescan3D/ ./tools/Aggrescan3D/

WORKDIR /app/tools/Aggrescan3D
RUN uv sync

EXPOSE 8102
ENV PORT=8102

CMD [".venv/bin/python", "service.py"]
