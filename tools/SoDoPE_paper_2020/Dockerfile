# SoDoPE 微服务 Docker 镜像
# ==================================
# SWI 是纯数学计算，无需 GPU，使用轻量 Python 镜像。
#
# 使用方式:
#   docker build -t sodope -f SoDoPE_paper_2020/Dockerfile .
#   docker run -p 8012:8012 sodope

FROM python:3.13-slim

LABEL org.opencontainers.image.title="SoDoPE"
LABEL org.opencontainers.image.description="蛋白质溶解度预测微服务 — Solubility-Weighted Index (SWI)"
LABEL org.opencontainers.image.source="https://github.com/Gardner-BinfLab/TIsigner"

# 安装系统依赖（健康检查需要 curl）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制项目骨架 — 保留 tools/template/ 相对路径结构
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/

# 复制 SoDoPE 自身代码
COPY tools/SoDoPE_paper_2020/ ./tools/SoDoPE_paper_2020/
WORKDIR /app/tools/SoDoPE_paper_2020

# 使用 uv 同步依赖
RUN pip install --no-cache-dir uv && \
    uv sync --no-dev --frozen --extra service

EXPOSE 8012

ENV PORT=8012

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8012/health || exit 1

CMD ["uv", "run", "service.py"]
