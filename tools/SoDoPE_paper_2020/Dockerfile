# SoDoPE 微服务 Docker 镜像
# ==================================
# SWI 是纯数学计算，无需 GPU，使用轻量 Python 镜像。
#
# 使用方式:
#   cd SoDoPE_paper_2020
#   docker build -t sodope .
#   docker run -p 8012:8012 sodope

FROM python:3.13-slim

LABEL org.opencontainers.image.title="SoDoPE"
LABEL org.opencontainers.image.description="蛋白质溶解度预测微服务 — Solubility-Weighted Index (SWI)"
LABEL org.opencontainers.image.source="https://github.com/Gardner-BinfLab/TIsigner"

# 安装服务依赖
RUN pip install --no-cache-dir \
    numpy \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 复制项目骨架 — 保留 tools/template/ 相对路径结构
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY SoDoPE_paper_2020/ ./SoDoPE_paper_2020/

WORKDIR /app/SoDoPE_paper_2020

EXPOSE 8012

ENV PORT=8012

CMD ["python", "service.py"]
