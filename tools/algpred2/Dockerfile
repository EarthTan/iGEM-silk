# AlgPred2 CPU Docker 镜像
# ==========================
# sklearn Random Forest (AAC, 19维)，纯 CPU 推理。
#
# 使用方式:
#   cd tools/AlgPred2
#   docker build -t algpred2 .
#   docker run -p 8008:8008 algpred2

FROM python:3.11-slim

LABEL org.opencontainers.image.title="AlgPred2"
LABEL org.opencontainers.image.description="过敏原性风险预测 — sklearn Random Forest"
LABEL org.opencontainers.image.source="https://github.com/raghavagps/algpred2"

RUN pip install --no-cache-dir \
    algpred2>=1.4 \
    joblib>=1.5.3 \
    "numpy==1.26.4" \
    "scikit-learn==1.2.2" \
    pandas \
    fastapi "uvicorn[standard]" pydantic \
    httpx

WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/algpred2/ ./tools/algpred2/

WORKDIR /app/tools/algpred2

EXPOSE 8008
ENV PORT=8008

CMD ["python", "service.py"]
