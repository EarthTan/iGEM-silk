# TIPred CPU Docker 镜像
# =======================
# sklearn Stacked Ensemble (547维特征)，纯 CPU 推理。
#
# 使用方式:
#   cd tools/TIPred
#   docker build -t tipred .
#   docker run -p 8007:8007 tipred

FROM python:3.11-slim

LABEL org.opencontainers.image.title="TIPred"
LABEL org.opencontainers.image.description="酪氨酸酶抑制肽预测 — sklearn Stacked Ensemble"
LABEL org.opencontainers.image.source="https://github.com/raghavagps/algpred2"

RUN pip install --no-cache-dir \
    modlamp>=4.3.2 \
    peptides>=0.5.0 \
    scikit-learn>=1.0.0 \
    numpy pandas \
    fastapi "uvicorn[standard]" pydantic \
    httpx

WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/TIPred/ ./tools/TIPred/

WORKDIR /app/tools/TIPred

EXPOSE 8007
ENV PORT=8007

CMD ["python", "service.py"]
