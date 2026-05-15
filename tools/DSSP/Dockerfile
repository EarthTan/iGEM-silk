# DSSP 微服务 Docker 镜像
# ======================
# mkdssp + Biopython 的轻量 CPU 镜像。
# 无需 GPU，纯结构分析。
#
# 使用方式:
#   cd C:\yoyo\iGEM\iGEM-silk
#   docker build -f tools/DSSP/Dockerfile -t igem-silk/dssp .
#   docker run -p 8103:8103 igem-silk/dssp

FROM python:3.11-slim

LABEL org.opencontainers.image.title="DSSP"
LABEL org.opencontainers.image.description="DSSP 二级结构分析与 beta-sheet 风险过滤"
LABEL org.opencontainers.image.source="https://github.com/PDB-REDO/dssp"

# mkdssp 运行需要 dssp + libcifpp 数据。
# components.cif 是 CCD 化学组分字典；没有它时 mkdssp 会无法识别 ALA/THR 等标准氨基酸。
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources && \
    apt-get -o Acquire::Retries=5 update && \
    apt-get install -y --no-install-recommends \
        dssp \
        libcifpp-data \
        ca-certificates \
        curl \
        gzip \
    && mkdir -p /usr/share/libcifpp /var/cache/libcifpp \
    && curl -L --retry 5 --retry-delay 5 \
        -o /tmp/components.cif.gz \
        https://files.wwpdb.org/pub/pdb/data/monomers/components.cif.gz \
    && gunzip -c /tmp/components.cif.gz > /usr/share/libcifpp/components.cif \
    && cp /usr/share/libcifpp/components.cif /var/cache/libcifpp/components.cif \
    && test -s /usr/share/libcifpp/components.cif \
    && test -s /var/cache/libcifpp/components.cif \
    && rm -f /tmp/components.cif.gz \
    && rm -rf /var/lib/apt/lists/*

ENV LIBCIFPP_DATA_DIR=/usr/share/libcifpp

RUN pip install --no-cache-dir \
    biopython numpy \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 复制项目骨架
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/DSSP/ ./tools/DSSP/

WORKDIR /app/tools/DSSP

EXPOSE 8103
ENV PORT=8103

CMD ["python", "service.py"]