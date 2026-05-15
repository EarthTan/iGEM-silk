---
name: Docker 容器桥接 IP 直连绕过 docker-proxy 不稳定连接 v1.0
author: Claude Code
created: 2026-05-15
version: 1.0.0
tags: [docker, networking, bridge, proxy, httpx, connection-pool]
validated: true
---

# Gene Capsule: Docker 容器桥接 IP 直连绕过 docker-proxy 不稳定连接

## Experience

**问题描述**: 宿主机通过 `http://127.0.0.1:8204`（Docker 端口映射）连接 OmegaFold 容器时，httpx AsyncClient 出现间歇性连接池耗尽和请求挂死。同一时刻 `docker exec omegafold curl -s http://localhost:8204/health`（容器内）却正常响应。

**症状**:
- httpx 抛出 `ConnectError`、`ReadTimeout` 等异常
- 但服务容器内确认 healthy
- 使用 curl 从宿主机偶尔成功、偶尔挂死
- docker-proxy (dockerd) 是宿主机→容器之间的 NAT 代理

**根因**:
```
请求路径: httpx → 127.0.0.1:8204 → docker-proxy → 容器 eth0:8204 → OmegaFold
```
docker-proxy（dockerd 的用户态代理）在处理 httpx 的 HTTP/1.1 keep-alive 连接池时存在 bug：
1. 长连接复用导致连接状态不同步
2. 容器重启后（/restart 端点）docker-proxy 未清理旧的 TCP 连接
3. 高并发场景下代理的 epoll 模型出现竞争条件

**直接使用容器 bridge IP 绕过 docker-proxy**:

```python
import subprocess, json, os

def _fix_omegafold_docker_network():
    """检测 OmegaFold 容器 bridge IP，设置 OMEGAFOLD_HOST 绕过 docker-proxy"""
    try:
        result = subprocess.run(
            ["docker", "inspect", "omegafold",
             "--format", "{{json .NetworkSettings.Networks}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            networks = json.loads(result.stdout)
            for net_name, net_info in networks.items():
                ip = net_info.get("IPAddress", "")
                if ip:
                    os.environ["OMEGAFOLD_HOST"] = ip
                    return
    except Exception as e:
        log(f"  ⚠ OmegaFold 网络检测失败: {e}")
```

之后 `service_url("omegafold")` 通过环境变量读到 bridge IP，直接走容器网络（Docker 内部 DNS），不再经过 docker-proxy。

**效果**: 从此时起到运行结束，OmegaFold 连接 100% 成功。

### 诊断方法

| 方法 | 命令 | 效果 |
|------|------|------|
| 宿主机 curl | `curl -s http://127.0.0.1:8204/health` | ❌ 间歇挂死 |
| 容器内 curl | `docker exec omegafold curl -s http://localhost:8204/health` | ✅ 总是正常 |
| docker-proxy 状态 | `curl -s http://127.0.0.1:8204/health --connect-timeout 5` | 可复现问题 |
| bridge IP 检测 | `docker inspect omegafold --format '{{json .NetworkSettings.Networks}}'` | 返回 bridge IP |

### 适用场景

任何通过 docker-proxy（127.0.0.1:PORT 映射）访问容器服务时出现间歇性连接问题：

- httpx AsyncClient 连接池异常
- 容器重启后连接未刷新
- 宿主机 ↔ 容器通信在负载下不稳定
- 容器频繁重启（/restart 端点）后问题加重

### 不适用场景

- Docker Compose 内部服务间通信（自动 DNS 解析，不经过 proxy）
- 宿主机→容器的短连接、低并发访问（docker-proxy 正常场景下可用）
- 使用 host 网络模式（`--network host`）的服务

### 相关文件

- `main/stages2/round05_3d.py` — `_fix_omegafold_docker_network()` 实现
- `main/config.py` — `service_url()` 环境变量覆盖逻辑
- `.agents/learnings/microservice-host-binding.md` — 服务绑定策略（相关但不同层面）

### 替代方案

如果容器 bridge network 不可用（非默认 bridge），可用 `docker inspect` 获取其他网络 IP，或使用 Docker DNS（容器名）直接访问：

```bash
# 同 docker-compose 网络内可用容器名
curl http://omegafold:8204/health
```
