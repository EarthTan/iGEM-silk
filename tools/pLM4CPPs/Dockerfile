# pLM4CPPs GPU 加速 Docker 镜像
# ===============================
# 基于 PyTorch 官方 GPU 镜像，使用 CUDA 加速 ESM-2 + 1D-CNN 推理。
# 模型: ESM-2 t6 8M 嵌入 (320维) + 1D-CNN 分类器 (Keras/TensorFlow)。
#
# 使用方式:
#   cd tools/pLM4CPPs
#   docker build -t plm4cpps-gpu .
#   docker run --gpus all -p 8006:8006 plm4cpps-gpu
#
# 前提条件:
#   - NVIDIA 驱动 (>=525)
#   - nvidia-container-toolkit

FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

LABEL org.opencontainers.image.title="pLM4CPPs GPU"
LABEL org.opencontainers.image.description="细胞穿膜肽预测 — ESM-2 + 1D-CNN + CUDA 加速"
LABEL org.opencontainers.image.source="https://github.com/drkumarnandan/pLM4CPPs"

# 安装服务依赖 (torch 已由基础镜像提供)
RUN pip install --no-cache-dir \
    tensorflow>=2.20.0 \
    fair-esm>=2.0.0 \
    scikit-learn>=1.0.0 \
    h5py>=3.16.0 \
    biopython>=1.87 \
    numpy pandas \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 复制项目骨架
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/pLM4CPPs/ ./tools/pLM4CPPs/

WORKDIR /app/tools/pLM4CPPs

EXPOSE 8006
ENV PORT=8006

CMD ["python", "service.py"]
