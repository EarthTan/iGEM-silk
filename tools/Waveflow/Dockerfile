# Waveflow — Tamarind.bio API 包装微服务
# 轻量无状态服务，无 GPU 依赖，无需模型权重

FROM python:3.11-slim

WORKDIR /app

# 复制项目文件
COPY tools/__init__.py /app/tools/
COPY tools/template/ /app/tools/template/
COPY tools/Waveflow/ /app/tools/Waveflow/
COPY tools/utils.py /app/tools/

# 安装依赖（不安装包本身，service.py 直接运行）
RUN pip install --no-cache-dir httpx>=0.27.0 fastapi>=0.115.0 uvicorn[standard]>=0.30.0 pydantic>=2.0.0

ENV PYTHONPATH=/app

EXPOSE 8205

CMD ["python", "/app/tools/Waveflow/service.py"]
