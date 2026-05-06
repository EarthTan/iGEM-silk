# tools/AnOxPePred/Dockerfile
# AnOxPePred 微服务 Docker 镜像
#
# 构建命令（从项目根目录运行）：
#   docker build -f tools/AnOxPePred/Dockerfile -t anoxpepred:1.0.0 .

# 使用 Python 官方镜像
FROM --platform=linux/amd64 python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PORT=8001

# 安装 uv（快速的包管理器）
RUN pip install uv

# 复制依赖配置文件（相对于构建上下文）
COPY tools/AnOxPePred/pyproject.toml tools/AnOxPePred/uv.lock ./

# 创建虚拟环境并安装所有依赖
RUN uv venv .venv && \
    uv pip install --frozen -e ".[all]"

# 只复制本服务需要的 tools 子目录
COPY tools/__init__.py ./tools/
COPY tools/template/ ./tools/template/
COPY tools/AnOxPePred/ ./tools/AnOxPePred/

# 复制工具数据（模型权重等）
COPY tools/AnOxPePred/anoxpepred_data/ ./anoxpepred_data/

# 复制启动脚本到 /app/tools/AnOxPePred/
# 这样 parents[2] 才能正确指向 /app
COPY tools/AnOxPePred/main.py tools/AnOxPePred/service.py ./tools/AnOxPePred/

# 暴露端口
EXPOSE 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# 启动命令
CMD [".venv/bin/python", "tools/AnOxPePred/main.py"]