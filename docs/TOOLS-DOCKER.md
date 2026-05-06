# Tools 微服务 Docker 容器化部署标准文档

## 目录

1. [架构概述](#1-架构概述)
2. [项目目录结构](#2-项目目录结构)
3. [Dockerfile 设计规范](#3-dockerfile-设计规范)
4. [docker-compose 编排配置](#4-docker-compose-编排配置)
5. [构建与运行流程](#5-构建与运行流程)
6. [Apple Silicon 平台适配](#6-apple-silicon-平台适配)
7. [Python 导入路径管理](#7-python-导入路径管理)
8. [常见问题与解决方案](#8-常见问题与解决方案)
9. [快速复刻清单](#9-快速复刻清单)

---

## 1. 架构概述

### 1.1 微服务设计原则

```
┌─────────────────────────────────────────────────────────────────┐
│                        项目根目录                                 │
│  iGEM-silk/                                                      │
│                                                                  │
│  ├── tools/                    ← 微服务工具代码（含模板）          │
│  │   ├── template/            │   BioToolService 基类所在         │
│  │   │   ├── __init__.py     │                                   │
│  │   │   └── tool_service.py │   每个工具靠近自己使用的服务基类    │
│  │   ├── AnOxPePred/         │                                   │
│  │   │   ├── service.py      │   工具特定业务逻辑                 │
│  │   │   ├── main.py         │   启动入口                         │
│  │   │   ├── Dockerfile      │   工具独立打包                     │
│  │   │   └── tools/          │   工具内部工具（如 anoxpepred_integration）│
│  │   └── ...                                                     │
│  │                                                                │
│  └── docker-compose.yml         容器编排文件                       │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计思想

| 原则 | 说明 |
|------|------|
| **工具自包含** | 每个工具目录下包含所有运行所需的代码和数据，不依赖外部 services/ 目录 |
| **服务基类就近** | `BioToolService` 放在 `tools/template/`，让使用它的工具能方便导入 |
| **单一职责镜像** | 每个工具独立打包成 Docker 镜像，镜像间无耦合 |
| **环境一致性** | 使用 Docker 确保开发、生产环境一致 |

---

## 2. 项目目录结构

### 2.1 标准工具目录结构

```
tools/
└── {ToolName}/                    # 工具目录（示例：AnOxPePred）
    ├── Dockerfile                  # 构建该工具的 Docker 镜像
    ├── pyproject.toml             # Python 依赖配置
    ├── uv.lock                    # 锁定依赖版本
    ├── service.py                 # 核心服务逻辑（继承 BioToolService）
    ├── main.py                    # 启动入口（设置 PYTHONPATH、启动服务）
    ├── tools/                     # 工具内部子模块（如第三方集成）
    │   └── {integration}.py      # 第三方工具包装器
    └── {toolname}_data/           # 静态数据（模型权重、配置等）
        ├── model/
        └── config/
```

### 2.2 关键文件作用

| 文件 | 作用 | 注意事项 |
|------|------|----------|
| `Dockerfile` | 定义镜像构建步骤 | 必须设置正确的 PYTHONPATH |
| `pyproject.toml` | 定义 Python 依赖 | 包含 ml（机器学习）和 service（服务）依赖 |
| `main.py` | 服务启动入口 | 必须设置 sys.path 以便正确导入 |
| `service.py` | 业务逻辑 | 继承 `tools.template.tool_service.BioToolService` |

---

## 3. Dockerfile 设计规范

### 3.1 标准 Dockerfile 模板

```dockerfile
# tools/{ToolName}/Dockerfile
# 构建命令（从项目根目录运行）：
#   docker build -f tools/{ToolName}/Dockerfile -t {toolname}:1.0.0 .

# 使用 TensorFlow 官方镜像（amd64 架构）
FROM --platform=linux/amd64 tensorflow/tensorflow:2.15.0

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PORT=8001

# 安装 uv（快速的包管理器）
RUN pip install uv

# 复制依赖配置文件
COPY tools/{ToolName}/pyproject.toml tools/{ToolName}/uv.lock ./

# 创建虚拟环境并安装所有依赖
RUN uv sync --frozen --all-extras

# 复制工具目录（必须包含 tools/template 和工具自身）
COPY tools/ ./tools/

# 复制工具数据
COPY tools/{ToolName}/{toolname}_data/ ./{toolname}_data/

# 复制启动脚本
COPY tools/{ToolName}/main.py tools/{ToolName}/service.py ./

# 暴露端口（根据工具调整）
EXPOSE 8001

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# 启动命令
CMD ["/app/.venv/bin/python", "main.py"]
```

### 3.2 Dockerfile 关键配置说明

#### 3.2.1 基础镜像选择

```dockerfile
# 机器学习类工具（TensorFlow）
FROM --platform=linux/amd64 tensorflow/tensorflow:2.15.0

# 如果不使用 ML，可选更轻量的镜像
# FROM python:3.11-slim
```

#### 3.2.2 依赖安装

```dockerfile
# 安装 uv（比 pip 更快）
RUN pip install uv

# 同步依赖（--frozen 锁定版本，--all-extras 包含所有 extra 依赖）
RUN uv sync --frozen --all-extras
```

#### 3.2.3 文件复制策略

```dockerfile
# 关键原则：只复制需要的目录，避免冗余

# 1. 复制工具目录（包含 tools/template 和工具自身代码）
# 这样 tools.template.tool_service 和 tools.{toolname}.tools.{integration} 都能被找到
COPY tools/ ./tools/

# 2. 如果工具内部有嵌套的 tools/ 子目录（如 AnOxPePred/tools/anoxpepred_integration.py）
# 同样可以被找到，因为父目录被复制了
```

### 3.3 多阶段构建（可选优化）

```dockerfile
# 适用于需要减少镜像大小的场景
FROM --platform=linux/amd64 tensorflow/tensorflow:2.15.0 as builder

WORKDIR /app
# ... 安装依赖 ...

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY tools/ ./tools/
CMD ["/app/.venv/bin/python", "main.py"]
```

---

## 4. docker-compose 编排配置

### 4.1 标准 docker-compose.yml

```yaml
# docker-compose.yml
version: "3.8"

services:
  # 工具服务示例（AnOxPePred）
  anoxpepred:
    build:
      context: .
      dockerfile: tools/AnOxPePred/Dockerfile
    container_name: anoxpepred
    ports:
      - "8001:8001"
    environment:
      - PYTHONUNBUFFERED=1
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s

  # 可添加更多工具服务
  # tool2:
  #   build:
  #     context: .
  #     dockerfile: tools/Tool2/Dockerfile
  #   container_name: tool2
  #   ports:
  #     - "8002:8001"
```

### 4.2 docker-compose 命令

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看服务日志
docker-compose logs -f anoxpepred

# 停止并移除容器
docker-compose down

# 重新构建（代码变更后）
docker-compose up -d --build
```

---

## 5. 构建与运行流程

### 5.1 标准构建流程

```bash
# 1. 清理旧容器和镜像（可选，但推荐）
docker stop anoxpepred 2>/dev/null
docker rm anoxpepred 2>/dev/null
docker rmi anoxpepred:1.0.0 2>/dev/null

# 2. 从项目根目录构建镜像
# 关键：context 是项目根目录，dockerfile 指向工具子目录
cd /path/to/iGEM-silk
docker build -f tools/AnOxPePred/Dockerfile -t anoxpepred:1.0.0 .

# 3. 运行容器
docker run -d --name anoxpepred -p 8001:8001 anoxpepred:1.0.0

# 4. 验证服务
sleep 10
curl http://localhost:8001/health
```

### 5.2 使用 docker-compose

```bash
# 构建并启动
docker-compose up -d --build

# 验证
curl http://localhost:8001/health
```

### 5.3 验证清单

```bash
# 检查容器运行状态
docker ps | grep anoxpepred

# 检查健康状态
curl http://localhost:8001/health
# 期望输出：{"status":"healthy","tool_name":"anoxpepred","version":"1.0.0","model_loaded":true}

# 查看日志
docker logs anoxpepred
```

---

## 6. Apple Silicon 平台适配

### 6.1 问题描述

Apple Silicon (M1/M2/M3) 使用 arm64 架构，但很多 ML 镜像（如 TensorFlow）只提供 amd64 版本。

### 6.2 解决方案

#### 方案一：指定平台（推荐）

```dockerfile
# 在 Dockerfile 中指定 amd64 平台
FROM --platform=linux/amd64 tensorflow/tensorflow:2.15.0
```

#### 方案二：docker build 时指定

```bash
docker build --platform=linux/amd64 -f tools/AnOxPePred/Dockerfile -t anoxpepred:1.0.0 .
```

### 6.3 注意事项

| 事项 | 说明 |
|------|------|
| **警告信息** | `WARNING: The requested image's platform (linux/amd64) does not match the detected host platform (linux/arm64/v8)` 这是正常的，Rosetta 会自动转译 |
| **性能损失** | x86 镜像在 ARM 上运行有少量性能损失 |
| **跨平台构建** | 无法在 M1/M2/M3 上构建 ARM 镜像，只能构建 amd64 镜像 |

---

## 7. Python 导入路径管理

### 7.1 问题背景

Docker 容器内的 Python 路径与本地开发环境不同，需要显式设置 `PYTHONPATH`。

### 7.2 main.py 中的路径配置

```python
# tools/{ToolName}/main.py
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path
# 这样可以导入 tools.template.tool_service 等模块
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 将工具自身目录添加到 sys.path
# 用于导入 tools/{ToolName}/tools/{integration}.py
TOOL_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOL_DIR))

# 其他必要的路径配置...
```

### 7.3 service.py 中的导入

```python
# 从 tools.template 导入基类
from tools.template.tool_service import BioToolService, ToolResult, create_app

# 从工具内部 tools/ 目录导入集成模块
from tools.AnOxPePred.tools.anoxpepred_integration import AnOxPePredIntegration
```

### 7.4 路径查找规则

```
Docker 容器内 /app 目录结构：

/app/
├── .venv/                    # 虚拟环境
├── tools/                    # 项目工具目录
│   ├── template/            # BioToolService 所在
│   │   └── tool_service.py
│   └── AnOxPePred/
│       ├── service.py
│       └── tools/           # 工具内部子模块
│           └── anoxpepred_integration.py
├── anoxpepred_data/         # 模型数据
├── main.py
└── service.py

sys.path 包含：
- "" (空字符串，表示当前目录)
- /app（WORKDIR）
- 项目根目录（通过 sys.path.insert 添加）
```

---

## 8. 常见问题与解决方案

### 8.1 ModuleNotFoundError

**问题**：`ModuleNotFoundError: No module named 'tools.template.tool_service'`

**原因**：sys.path 未正确设置

**解决**：
1. 检查 main.py 是否正确设置 sys.path
2. 检查 Dockerfile 是否复制了完整的 tools/ 目录
3. 检查 PYTHONPATH 环境变量

### 8.2 容器启动后立即退出

**问题**：容器状态为 Exited (0)

**原因**：
- main.py 执行完毕
- Python 脚本未启动服务

**解决**：
- 检查 CMD 是否使用正确路径：`/app/.venv/bin/python main.py`
- 检查 main.py 是否包含 `uvicorn.run()` 或类似服务启动逻辑

### 8.3 端口冲突

**问题**：`Bind for 0.0.0.0:8001 failed: port is already allocated`

**解决**：
```bash
# 查看占用端口的进程
lsof -i :8001

# 停止占用进程或使用其他端口
docker run -d --name anoxpepred -p 8002:8001 anoxpepred:1.0.0
```

### 8.4 模型加载失败

**问题**：`Failed to load model`

**可能原因**：
- 缺少模型文件
- 模型文件路径错误
- 依赖库缺失

**解决**：
1. 检查 Dockerfile 是否正确复制 anoxpepred_data/ 目录
2. 检查 service.py 中的模型路径是否正确
3. 查看容器日志 `docker logs anoxpepred`

### 8.5 镜像过大

**解决**：使用多阶段构建

```dockerfile
FROM --platform=linux/amd64 tensorflow/tensorflow:2.15.0 as builder
# ... 构建步骤 ...

FROM python:3.11-slim
COPY --from=builder /app/.venv /app/.venv
COPY tools/ ./tools/
CMD ["/app/.venv/bin/python", "main.py"]
```

### 8.6 磁盘空间不足

**问题**：Docker 构建失败，提示空间不足

**解决**：
```bash
# 清理未使用的镜像、容器、网络
docker system prune -a --volumes -f

# 查看 Docker 磁盘使用
docker system df
```

---

## 9. 快速复刻清单

### 9.1 新增工具 Docker 化检查清单

```
□ 1. 创建工具目录 tools/{ToolName}/
□ 2. 编写 pyproject.toml（包含 ml、service 依赖）
□ 3. 安装依赖并生成 uv.lock
□ 4. 编写 service.py（继承 BioToolService）
□ 5. 编写 main.py（正确设置 sys.path）
□ 6. 编写 Dockerfile
□ 7. 更新 docker-compose.yml
□ 8. 测试构建和运行
```

### 9.2 Dockerfile 检查清单

```
□ FROM --platform=linux/amd64 指定正确基础镜像
□ WORKDIR /app
□ 安装 uv
□ COPY pyproject.toml 和 uv.lock
□ uv sync --frozen --all-extras
□ COPY tools/ ./tools/
□ COPY {toolname}_data/ ./{toolname}_data/
□ COPY main.py service.py ./
□ EXPOSE 正确端口
□ HEALTHCHECK 配置
□ CMD 使用虚拟环境中的 Python
```

### 9.3 验证检查清单

```
□ docker build 成功
□ docker run 容器不退出的
□ curl http://localhost:{port}/health 返回 {"status":"healthy",...}
□ 模型加载成功（model_loaded: true）
□ 日志无严重错误
```

---

## 附录 A：完整示例（AnOxPePred）

### A.1 目录结构

```
tools/AnOxPePred/
├── Dockerfile
├── pyproject.toml
├── uv.lock
├── service.py
├── main.py
└── anoxpepred_data/
    └── ...（模型文件）
```

### A.2 pyproject.toml

```toml
[project]
name = "anoxpepred-service"
version = "1.0.0"
description = "AnOxPePred antioxidant peptide prediction service"
requires-python = ">=3.10"

[project.optional-dependencies]
ml = ["tensorflow", "numpy", "pandas"]
service = ["fastapi", "uvicorn", "pydantic"]
all = ["tensorflow", "numpy", "pandas", "fastapi", "uvicorn", "pydantic"]
```

### A.3 service.py 关键代码

```python
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 将工具目录添加到 sys.path（用于导入 tools/{ToolName}/tools/*.py）
ANOXPE_DIR = Path(__file__).parent
sys.path.insert(0, str(ANOXPE_DIR))

from tools.template.tool_service import BioToolService, ToolResult, create_app

class AnOxPePredService(BioToolService):
    tool_name = "anoxpepred"
    version = "1.1.0"

    async def load_model(self):
        from tools.AnOxPePred.tools.anoxpepred_integration import AnOxPePredIntegration
        self.model = AnOxPePredIntegration(verbose=True)

    async def predict_impl(self, sequence: str) -> ToolResult:
        # ... 预测逻辑 ...
        pass

# 启动服务
app = create_app(AnOxPePredService)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
```

---

## 附录 B：AI 助手复用提示词模板

当需要将新的工具 Docker 化时，可复用以下思维模板：

```
## 新工具 Docker 化模板

### 1. 分析工具结构
- 工具名称：{name}
- Python 依赖：查看 pyproject.toml
- 是否有第三方集成模块：检查 tools/ 子目录
- 模型/数据文件：检查 *_data/ 目录

### 2. 确定 sys.path 配置
- 工具代码位置：tools/{name}/
- BioToolService 位置：tools/template/tool_service.py
- 第三方集成位置：tools/{name}/tools/{integration}.py

### 3. 编写 Dockerfile
- 基础镜像：根据依赖选择（TensorFlow/Python-slim）
- 平台：--platform=linux/amd64（如果需要）
- COPY：确保 tools/ 目录完整复制
- 入口：/app/.venv/bin/python main.py

### 4. 更新 docker-compose
- 端口映射：container_port:host_port
- 健康检查：GET /health

### 5. 验证
- 构建成功
- 容器运行不退出
- /health 返回 healthy
```

---

## 附录 C：命令速查表

| 操作 | 命令 |
|------|------|
| 构建镜像 | `docker build -f tools/{ToolName}/Dockerfile -t {toolname}:1.0.0 .` |
| 运行容器 | `docker run -d --name {name} -p {port}:8001 {toolname}:1.0.0` |
| 查看日志 | `docker logs -f {name}` |
| 进入容器 | `docker exec -it {name} bash` |
| 查看状态 | `docker ps \| grep {name}` |
| 健康检查 | `curl http://localhost:{port}/health` |
| 清理 | `docker system prune -a --volumes -f` |

---

*文档版本：1.0*
*最后更新：2026-05-07*