# AnOxPePred GPU 加速 Docker 镜像
# ==================================
# 基于 TensorFlow 官方 GPU 镜像，使用 CUDA/cuDNN 加速 CNN 推理。
#
# 使用方式:
#   cd tools/AnOxPePred
#   docker build -t anoxpepred-gpu .
#   docker run --gpus all -p 8001:8001 anoxpepred-gpu
#
# 前提条件:
#   - NVIDIA 驱动 (>=525)
#   - nvidia-container-toolkit (https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)

FROM tensorflow/tensorflow:2.21.0-gpu

LABEL org.opencontainers.image.title="AnOxPePred GPU"
LABEL org.opencontainers.image.description="抗氧化肽预测微服务 — CNN 深度学习 + CUDA 加速"
LABEL org.opencontainers.image.source="https://github.com/TobiasHeOl/AnOxPePred"

# 安装服务依赖 (TF/CUDA 已由基础镜像提供)
RUN pip install --no-cache-dir \
    numpy pandas \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 复制项目骨架 — 保留 tools/template/ 相对路径结构
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/AnOxPePred/ ./tools/AnOxPePred/

WORKDIR /app/tools/AnOxPePred

EXPOSE 8001

ENV PORT=8001

CMD ["python", "service.py"]
