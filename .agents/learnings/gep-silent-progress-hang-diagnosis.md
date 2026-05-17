---
name: 流水线脚本静默挂起的诊断方法 v1.0
author: Claude Code
created: 2026-05-17
version: 1.0.0
tags: [diagnosis, debugging, docker, networking, progress, hang, async]
validated: true
---

# Gene Capsule: 流水线脚本静默挂起的诊断方法

## Experience

**问题描述**: Round 3 脚本通过 `127.0.0.1` 访问 BepiPred-3.0 容器时，脚本进程存活、容器正常处理请求、但 `run.log` 长达 30+ 分钟没有任何进度输出。

**症状**:
- `pgrep -f round03` → 进程存活
- `docker logs bepipred3 | grep "Batch predict done"` → 容器在持续处理批次
- `tail -f run.log` → 无新日志
- 容器实际已处理 50+ 批次，但脚本的 `asyncio.gather` 未返回

**根因**: docker-proxy（dockerd 的用户态代理）在处理 httpx 的 HTTP/1.1 keep-alive 长连接时，对于执行时间较长的请求（BepiPred3 ~45s/batch）会出现连接挂死。Semaphore(2) 下 2 个并发连接中的 1 个挂起，导致整体吞吐减半，且 `asyncio.gather` 需要等待全部 50 个任务完成才输出日志，加剧了"无进度"的假象。

### 诊断流程

当脚本运行但无日志输出时，按以下顺序排查：

| 步骤 | 命令 | 判断依据 |
|------|------|----------|
| 1. 进程存活 | `pgrep -f round03_heavy` | 进程必须存活 |
| 2. 容器活动 | `docker logs bepipred3 \| tail -5` | 是否有新请求/处理完成 |
| 3. 批次计数 | `docker logs bepipred3 \| grep "Batch predict done" \| wc -l` | 计数是否在增长 |
| 4. 连接状态 | `ss -tnp \| grep $(pgrep -f round03_heavy \| head -1)` | 目标 IP 是 127.0.0.1 还是 172.18.0.x |
| 5. 并发数 | `ss -tnp \| grep 8002` | Semaphore(N) 应有 N 个 ESTABLISHED 连接 |
| 6. 容器内 curl | `docker exec bepipred3 curl -s http://localhost:8002/health` | 服务本身是否正常 |
| 7. 吞吐速率 | 隔 30 秒重复步骤 3，计算批次数增量 | 正常: N_concurrent × 60/batch_time |

**关键信号**: 步骤 4 显示目标 IP 为 `127.0.0.1`（docker-proxy）+ 步骤 5 显示部分连接无数据流动 → docker-proxy 挂起。

### 修复方法

设置环境变量 `{SERVICE}_HOST` 为容器 bridge IP 绕过 docker-proxy：

```bash
# 获取容器 bridge IP
docker inspect bepipred3 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
# 输出: 172.18.0.7

# 设置环境变量后重启
export BEPIPRED3_HOST=172.18.0.7
uv run python -m main.stages2.round03_heavy
```

`main/config.py` 中的 `service_url()` 会优先读取环境变量：

```python
def service_url(name: str) -> str:
    env_host = os.environ.get(f"{name.upper()}_HOST")
    host = env_host or SERVICES[name].get("host", SERVICE_HOST)
    # env_host="172.18.0.7" → 直接走容器网络
```

### 影响条件

docker-proxy 挂起具有**选择性**:
| 服务 | 单批耗时 | 是否受影响 | 原因 |
|------|---------|-----------|------|
| TemStaPro | ~1.3s/batch | ❌ 未受影响 | 请求快，keep-alive 未触发 bug |
| BepiPred3 | ~45s/batch | ✅ 受影响 | 长请求触发 docker-proxy 连接状态不同步 |

**规律**: 请求耗时越长，docker-proxy keep-alive 挂死概率越高。~1s 的请求几乎不受影响，~45s 的请求大概率出现。

### 相关文件

- `main/config.py` — `service_url()` 环境变量覆盖逻辑
- `.agents/learnings/gep-docker-container-bridge-ip.md` — 已有的 bridge IP 解决方案（侧重 OmegaFold）
- `main/stages2/round05_3d.py` — `_fix_omegafold_docker_network()` 自动检测实现

### 类似症状的可能原因

| 现象 | 可能原因 | 区别 |
|------|---------|------|
| 容器无请求日志 | 脚本在之前阶段卡住 | 检查容器日志时间戳 |
| 容器报错 | 服务异常 / OOM | 检查容器日志错误 |
| 连接数=0 | 网络不通 | `curl 127.0.0.1:PORT` 测试 |
| 连接数正常但无进度 | 此 GEP 描述的 docker-proxy 挂起 | `ss -tnp` 检查目标 IP |
