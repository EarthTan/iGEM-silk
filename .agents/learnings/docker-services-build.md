# Docker 微服务构建经验教训

## 项目背景
iGEM-silk 平台有 15 个微服务，通过 Docker Compose（tools/docker-compose.yml）管理。在首次构建全量服务时遭遇了一系列问题。

---

## 1. Dockerfile 路径一致性

### 教训
docker-compose.yml 中 `dockerfile` 路径是**相对于 build context** 的，不是相对于 compose 文件位置。当 `context: ..`（项目根目录）而 Dockerfile 在 `tools/<name>/` 下时，必须写 `dockerfile: tools/<name>/Dockerfile`。

### 正确做法
第一次排查时就全量 grep：
```bash
grep 'dockerfile:' docker-compose.yml
```
然后逐一与 `ls tools/*/Dockerfile` 比对，而不是凭记忆修几个就跑。

---

## 2. Linux 大小写敏感

### 教训
macOS 开发时大小写不敏感，但 Linux 严格区分。`Tipred` vs `TIPred`、`algpred2` vs `AlgPred2` 是不同的路径。Dockerfile 的 COPY、compose 的 dockerfile 路径、WORKDIR 三处都可能不一致。

### 正确做法
用 `ls` 逐字符确认实际目录名，不要"目测一致"就认为正确。

---

## 3. Docker Hub 在中国被墙

### 教训
`registry-1.docker.io` 在中国大部分网络环境不可达。使用 Docker Hub 镜像加速器是刚需。

### 配置
```json
{
  "registry-mirrors": ["https://docker.m.daocloud.io"]
}
```
写入 `/etc/docker/daemon.json` 并重启 Docker。

### 注意
修改 daemon.json 需要 sudo 权限，应尽早告知用户。

---

## 4. Docker-in-Docker 方式安装 docker-ce-cli

### 教训
PEP-FOLD4、AlphaFold3、Aggrescan3D 需要在容器内运行 `docker` 命令访问宿主机 Docker 守护进程。它们从 `download.docker.com`（也被墙）安装 docker-ce-cli。

### 解决方案
使用 Debian 源自带的 `docker.io` 包代替：
```dockerfile
RUN apt-get update && apt-get install -y docker.io
```

### 更好的方案
直接挂载宿主机 `/usr/bin/docker`：
```yaml
volumes:
  - /usr/bin/docker:/usr/bin/docker
```
避免在容器内安装任何 Docker 包。

---

## 5. `:latest` tag 的不确定性

### 教训
`ghcr.io/astral-sh/uv:latest` 在不同时间拉取不同版本。uv 在 0.5.x 中移除了 `--system` 参数，导致 `uv sync --system --no-dev` 在新版本中报错 `unexpected argument '--system' found`。

同时，不带 `--system` 的 `uv sync` 会创建 `.venv` 而非安装到系统 Python，后续 `CMD ["python", "service.py"]` 找不到包。

### 解决方案
1. Pin 版本：`ghcr.io/astral-sh/uv:0.4.30`
2. 或者使用 `.venv/bin/python`：`CMD [".venv/bin/python", "service.py"]`
3. 或者退回到 `pip install`（更稳定）

---

## 6. Python 命名空间冲突（最隐蔽）

### 现象
`from tools.template.fasta_service import ...` 在某些服务中报错 `ModuleNotFoundError`，但在其他服务中正常。

### 根因
- 项目结构：`/app/tools/` 下有 `template/`（框架代码）和 `AnOxPePred/`（微服务代码）
- AnOxPePred 内部有 `tools/AnOxPePred/tools/` 子目录（自己的 SDK 代码），其中包含 `__init__.py`
- Docker 的 `WORKDIR /app/tools/AnOxPePred` 使得 CWD 被加入 `sys.path[0]`
- Python 解析 `import tools` 时先找到本地的 `tools/`（有 `__init__.py`，正规包），遮蔽了项目级的 `tools/`（无 `__init__.py`，命名空间包）

### 修复
将内部 `tools/` 重命名为 `anoxpepred_sdk/`、`sodope_sdk/` 等唯一名称，避免与项目级 package 冲突。

### 预防
项目结构设计时约定：顶层 `tools/` 是项目框架包，各微服务的内部代码不要复用 `tools/` 作为目录名。

---

## 7. 渐进式修复的低效

### 教训
每次构建失败只修一个问题，循环 7-8 轮。每轮需要 2-10 分钟等待构建失败。

### 正确做法
第一次失败后就做全面审计扫描：
1. 检查所有 `dockerfile:` 路径
2. 检查所有 Dockerfile 的 COPY 语句
3. 检查所有 WORKDIR 和 CMD
4. 检查所有基础镜像的 Python 环境差异
5. 检查所有 pip/uv 依赖安装方式

用脚本一次性扫描，而非逐个等待 CI 报错。

---

## 8. Docker Compose 的原子性缺陷

### 教训
`docker compose --profile gpu --profile cpu up -d --build` 在构建 15 个服务时，任意一个失败就全部取消。前面 10 个可能已经成功，但因为最后一个失败而全部浪费。

### 更好的策略
分批次构建：
```bash
# 先构建 CPU 服务
docker compose --profile cpu build
# 再构建 GPU 服务
docker compose --profile gpu build
# 最后启动全部
docker compose --profile gpu --profile cpu up -d
```
或者用 `docker compose build <service1> <service2>` 单独构建失败的服务。

---

## 9. COPY `tools/utils.py` 遗漏

### 教训
多个 Dockerfile 只 COPY 了 `tools/template/` 和 `tools/<service>/`，但漏了 `tools/utils.py`。运行时 `from tools.utils import detect_system` 失败。

### 预防
脚本扫描所有 Dockerfile：
```bash
for f in tools/*/Dockerfile; do
  if ! grep -q 'COPY.*utils\.py' "$f" 2>/dev/null; then
    echo "MISS: $f"
  fi
done
```

---

## 10. slim 镜像缺少编译依赖

### 教训
`python:3.11-slim` 不含 C 扩展编译所需的头文件。`pip install freesasa` 需要 `python3-dev` 和 `pkg-config`。

### 通用解决方案
所有 slim 镜像的 Dockerfile 中，如果涉及 pip 安装原生扩展，标准配置应包括：
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc python3-dev pkg-config libxml2-dev \
    && rm -rf /var/lib/apt/lists/*
```

---

## 11. MHCflurry `| tail -5` 吞掉了模型下载错误

### 教训
Dockerfile 中：
```dockerfile
RUN ... mhcflurry-downloads fetch models_class1_pan 2>&1 | tail -5
```
`| tail -5` 的退出码永远是 0，即使 `mhcflurry-downloads` 失败。Docker 认为 RUN 成功了，镜像不含模型文件。

### 修复
移除 `| tail -5`，或改用：
```dockerfile
RUN ... mhcflurry-downloads fetch models_class1_pan && \
    echo "OK" || (echo "FAIL" && exit 0)
```

### 更好的方案
把模型文件下载到宿主机并用 volume 挂载，避免每层都 rebuild。
```yaml
volumes:
  - ./MHCflurry/models:/app/tools/MHCflurry/models
```

---

## 12. AlphaFold3 Docker-outside-Docker GPU 检测

### 教训
AlphaFold3 API 容器本身没有 GPU（通过 Docker socket 调用宿主机的 GPU），所以容器内没有 `nvidia-smi`。原来使用 `nvidia-smi` 检测 GPU 必然失败。

### 修复
1. 改从 Docker 信息查询：`docker info --format "{{json .Runtimes}}"` 检查 `nvidia` runtime
2. `nvidia-container-toolkit` 检测（`docker run --rm --gpus all alpine:latest echo ok`）是更可靠的 GPU 可用性验证
3. 避免使用需要从 Docker Hub 拉取的镜像做检测（`nvidia/cuda:12.0-base`），网络不通时会导致检测失败

---

## 13. 运行时下载的模型在容器重建后丢失

### 教训
用 `docker exec <container> mhcflurry-downloads fetch` 下载模型虽然成功，但容器被 `docker compose up -d --force-recreate` 重建后，文件全部消失。

### 修复
始终用 volume 挂载持久化模型文件：
```yaml
volumes:
  - ./MHCflurry/models:/app/tools/MHCflurry/models
```
然后在宿主机准备好模型文件。

---

## 14. `pip install bp3` 不会自动安装所有依赖

### 教训
`bp3==0.0.12.7`（BepiPred-3.0 包）依赖 `fair-esm` 和 `plotly`，但 pip 不一定自动安装它们。首次运行时报 `ModuleNotFoundError: No module named 'esm'` 和 `No module named 'plotly'`。

### 修复
在 Dockerfile 中显式声明所有已知依赖：
```dockerfile
RUN pip install bp3 plotly "fair-esm>=1.0.3"
```

### 预防
首次构建前先 `pip install` 测试一下，观察哪些包被实际安装。
