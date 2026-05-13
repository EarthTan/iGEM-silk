---
name: Microservice Host Binding
description: All microservices bind to 0.0.0.0 (all interfaces), controlled by Docker Compose port mapping, not service code
type: project
---

## 微服务网络绑定策略：不动服务代码，由 Docker Compose 控制

所有微服务（包括模板类）都绑定到 `0.0.0.0`（硬编码或默认值），这是**正确的行为**，不应统一改为 `TOOL_HOST` 环境变量。

**Why:**
- 在 Docker Compose 模式下，容器内部必须绑 `0.0.0.0`，否则 Docker 网络内其他服务连不上它
- 对外暴露范围由 `docker-compose.yml` 的 `ports:` 控制：
  - `"8001:8001"` → LAN 可访问
  - `"127.0.0.1:8001:8001"` → 仅 localhost
- 修改服务代码里的 host 绑定是多此一举，反而可能破坏 Docker 内部通信

**How to apply:**
- 不需要在服务代码里统一 host 配置
- 也不需要 .env 文件管理
- 如果需要限制外部访问，直接改 `tools/docker-compose.yml` 的端口映射加上 `127.0.0.1:` 前缀即可
- 所有微服务代码维持 `0.0.0.0` 不变
