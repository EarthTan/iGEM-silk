# BepiPred-3.0 GPU 加速 Docker 镜像
# ====================================
# 基于 PyTorch 官方 GPU 镜像，使用 CUDA 加速 ESM-2 (650M) 蛋白质语言模型推理。
# 模型: ESM-2 t33 650M + 5-model ensemble 分类器。
#
# 使用方式:
#   cd tools/BepiPred-3.0
#   docker build -t bepipred3-gpu .
#   docker run --gpus all -p 8002:8002 bepipred3-gpu
#
# 前提条件:
#   - NVIDIA 驱动 (>=525)
#   - nvidia-container-toolkit

FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

LABEL org.opencontainers.image.title="BepiPred-3.0 GPU"
LABEL org.opencontainers.image.description="B 细胞表位预测微服务 — ESM-2 650M + CUDA 加速"
LABEL org.opencontainers.image.source="https://github.com/UberClifford/BepiPred-3.0"

# 安装服务依赖 (torch 已由基础镜像提供)
RUN pip install --no-cache-dir \
    bp3==0.0.12.7 \
	    numpy pandas plotly \
    numpy pandas plotly \
    fastapi "uvicorn[standard]" pydantic \
    httpx

# 复制项目骨架
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/BepiPred-3.0/ ./tools/BepiPred-3.0/

WORKDIR /app/tools/BepiPred-3.0

EXPOSE 8002
ENV PORT=8002

# 预下载 ESM-2 模型权重 (避免首次请求延迟)
RUN python -c "import torch; from esm import pretrained; pretrained.esm2_t33_650M_UR50D()" 2>/dev/null || true

CMD ["python", "service.py"]
