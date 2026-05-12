# GraphCPP GPU 加速 Docker 镜像
# ===============================
# 基于 PyTorch 官方 GPU 镜像，使用 CUDA 加速 GraphSAGE GNN 推理。
# 模型: GraphSAGE 2层卷积 + Topological Torsion Fingerprint (2048维)。
#
# 使用方式:
#   cd tools/GraphCPP
#   docker build -t graphcpp-gpu .
#   docker run --gpus all -p 8009:8009 graphcpp-gpu
#
# 前提条件:
#   - NVIDIA 驱动 (>=525)
#   - nvidia-container-toolkit

FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-runtime

LABEL org.opencontainers.image.title="GraphCPP GPU"
LABEL org.opencontainers.image.description="细胞穿膜肽预测 — GraphSAGE GNN + CUDA 加速"
LABEL org.opencontainers.image.source="https://github.com/drkumarnandan/GraphCPP"

# 安装服务依赖 (torch 已由基础镜像提供)
# torch_scatter 从 PyG 官方 wheel 安装，避免源码编译
RUN pip install --no-cache-dir \
    torch-geometric>=2.7.0 \
    deepchem>=2.8.0 \
    rdkit>=2022.09.5 \
    numpy pandas \
    fastapi "uvicorn[standard]" pydantic \
    httpx \
    && pip install --no-cache-dir --no-build-isolation \
    torch-scatter -f https://data.pyg.org/whl/torch-2.6.0+cu124.html

# 复制项目骨架
WORKDIR /app
COPY tools/utils.py ./tools/utils.py
COPY tools/template/ ./tools/template/
COPY tools/GraphCPP/ ./tools/GraphCPP/

WORKDIR /app/tools/GraphCPP

EXPOSE 8009
ENV PORT=8009

CMD ["python", "service.py"]
