# Docker-outside-Docker 路径解析

## 问题

当 API 容器通过挂载 `/var/run/docker.sock` 调用宿主机 Docker 守护进程运行其他容器时，`docker run --volume` 的**源路径由宿主机 Docker 守护进程解析**，不是 API 容器内部路径。

## 典型案例：AlphaFold3

### 错误配置

```yaml
# docker-compose.yml
environment:
  - AF3_MODEL_DIR=/root/models           # ❌ 容器内路径
volumes:
  - /home/lenovo/af_models:/root/models  # 宿主机->容器挂载
```

service.py 中用 `AF3_MODEL_DIR`（值=`/root/models`）作为 Docker socket `--volume` 源路径：

```python
cmd = [
    "docker", "run", "--rm",
    "--volume", f"{self._model_dir}:/root/models",  # ❌ /root/models 在宿主机上不存在
    ...
]
```

Docker 守护进程在宿主机上找 `/root/models`，**找不到文件**。

### 正确做法

宿主机的 Docker 守护进程解析 volume 源路径，所以需要将**宿主机路径**传入容器：

```yaml
# docker-compose.yml
environment:
  - AF3_MODEL_DIR=/root/models                    # 容器内路径（health check 用）
  - AF3_MODEL_HOST_DIR=${AF3_MODEL_DIR}            # 宿主机路径（Docker socket 用）
volumes:
  - ${AF3_MODEL_DIR:-/tmp/af3_models}:/root/models
```

```python
# service.py
self._model_host_dir = os.environ.get("AF3_MODEL_HOST_DIR", self._model_dir)

cmd = [
    "docker", "run", "--rm",
    "--volume", f"{self._model_host_dir}:/root/models",  # ✅ 宿主机路径
    ...
]
```

### 适用范围

凡是 Docker-outside-of-Docker 模式（挂载 `/var/run/docker.sock`）且需要在 `docker run` 中挂载 host 目录的服务，都适用此规则。本项目涉及：

- `tools/AlphaFold3/` — 需要挂载模型参数和数据库目录
- `tools/PEP-FOLD4/` — 需要挂载 workspace 目录
- `tools/Aggrescan3D/` — 需要挂载 workspace 目录

## 健康检查的局限性

这类服务的 `/health` 端点只验证了**容器内路径存在**（因为 docker-compose 的 volume mount 创建了挂载点），但**不验证 Docker socket 路径在宿主机上是否可解析**。健康检查通过不代表预测能跑通。

### 排查思路

遇到 Docker socket + path 问题时，检查链路：

1. 宿主机真实路径在哪里？→ `ls /home/lenovo/public_databases`
2. docker-compose volumes 映射是否正确？→ `docker compose config`
3. 环境变量传递的是容器路径还是宿主机路径？→ `docker compose config | grep AF3_`
4. service.py 用哪个路径构建 `docker run --volume`？
5. 宿主机上是否存在该路径？
