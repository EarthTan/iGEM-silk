# ToxinPred3 CPU Docker 镜像
# ============================
# sklearn ExtraTreesClassifier (AAC+DPC, 420维)，纯 CPU 推理。
#
# 使用方式:
#   cd tools/ToxinPred3
#   docker build -t toxinpred3 .
#   docker run -p 8003:8003 toxinpred3

FROM python:3.11-slim

LABEL org.opencontainers.image.title="ToxinPred3"
LABEL org.opencontainers.image.description="肽毒性预测 — sklearn ExtraTreesClassifier"
LABEL org.opencontainers.image.source="https://github.com/raghavagps/toxinpred3"

RUN pip install --no-cache-dir \
    toxinpred3 \
    "numpy<2" pandas \
    "scikit-learn==1.2.2" joblib \
    fastapi "uvicorn[standard]" pydantic \
    httpx

WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/ToxinPred3/ ./tools/ToxinPred3/

WORKDIR /app/tools/ToxinPred3

EXPOSE 8003
ENV PORT=8003

CMD ["python", "service.py"]
