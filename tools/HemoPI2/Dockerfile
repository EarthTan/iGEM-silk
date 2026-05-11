# HemoPI2 GPU 加速 Docker 镜像
# =============================
# 基于 PyTorch 官方 GPU 镜像，使用 CUDA 加速 ESM-2 (t6 8M) 蛋白质语言模型推理。
# 模型: ESM-2 t6 + 序列分类头 (Model 3)。
#
# 使用方式:
#   cd tools/HemoPI2
#   docker build -t hemopi2-gpu .
#   docker run --gpus all -p 8004:8004 hemopi2-gpu
#
# 前提条件:
#   - NVIDIA 驱动 (>=525)
#   - nvidia-container-toolkit

FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

LABEL org.opencontainers.image.title="HemoPI2 GPU"
LABEL org.opencontainers.image.description="肽溶血性预测微服务 — ESM-2 t6 + CUDA 加速"
LABEL org.opencontainers.image.source="https://github.com/raghavagps/HemoPI2"

# 安装服务依赖 (torch 已由基础镜像提供)
RUN pip install --no-cache-dir \
    hemopi2>=1.3 \
    numpy pandas \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 复制项目骨架
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/HemoPI2/ ./tools/HemoPI2/

WORKDIR /app/tools/HemoPI2

EXPOSE 8004
ENV PORT=8004

CMD ["python", "service.py"]
