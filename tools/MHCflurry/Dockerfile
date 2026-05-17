# MHCflurry GPU 加速 Docker 镜像
# ===============================
# 基于 PyTorch 官方 GPU 镜像，使用 CUDA 加速神经网络推理。
# 模型: 14,883 MHC I 类等位基因，肽长度 5-15 aa。
#
# 使用方式:
#   cd tools/MHCflurry
#   docker build -t mhcflurry-gpu .
#   docker run --gpus all -p 8005:8005 mhcflurry-gpu
#
# 前提条件:
#   - NVIDIA 驱动 (>=525)
#   - nvidia-container-toolkit

FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

LABEL org.opencontainers.image.title="MHCflurry GPU"
LABEL org.opencontainers.image.description="MHC I 类肽结合亲和力预测 — PyTorch + CUDA 加速"
LABEL org.opencontainers.image.source="https://github.com/openvax/mhcflurry"

# 安装服务依赖 (torch 已由基础镜像提供)
RUN pip install --no-cache-dir \
    mhcflurry>=2.0.3 \
    numpy pandas \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 预下载 MHCflurry 模型权重到项目目录 (避免首次请求延迟)
# 注意：GitHub 在国内可能无法直接访问，使用 COPY 替代在线下载
# 如需在线下载，取消注释下行并注释掉 COPY 行：
# RUN mkdir -p /app/tools/MHCflurry/models && \
#     MHCFLURRY_DOWNLOADS_DIR=/app/tools/MHCflurry/models \
#     mhcflurry-downloads fetch models_class1_pan --release 2.2.0 2>&1
COPY models/ /app/tools/MHCflurry/models/

# 复制项目骨架
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/MHCflurry/ ./tools/MHCflurry/

WORKDIR /app/tools/MHCflurry

EXPOSE 8005
ENV PORT=8005

CMD ["python", "service.py"]
