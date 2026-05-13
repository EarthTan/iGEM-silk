---
name: 微服务网络绑定策略 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, networking, microservice, security, docker-compose]
validated: true
---

# Gene Capsule: 微服务网络绑定策略

## Experience

**问题类型**: 微服务在 Docker Compose 多服务架构中的网络绑定策略——是否应将硬编码的 `0.0.0.0` 改为通过环境变量控制？

**核心策略**: 所有微服务代码维持 `0.0.0.0`（或 `0.0.0.0:8001` 格式）不变，对外暴露范围由 `docker-compose.yml` 的 `ports:` 映射控制。不动服务代码，不改 host 配置，不加 .env 文件。

**Why**:
1. **Docker 内部通信必须用 `0.0.0.0`** — 容器内部必须绑 `0.0.0.0`，否则 Docker 网络内其他服务连不上它。这是 Docker 网络模型的基本要求
2. **对外暴露由 Docker Compose 控制** — `docker-compose.yml` 的端口映射语法天然支持访问控制：
   - `"8001:8001"` → LAN 内所有机器可访问
   - `"127.0.0.1:8001:8001"` → 仅本机 localhost 可访问
3. **修改服务代码是多此一举** — 在服务代码里写 `TOOL_HOST` 环境变量逻辑，等于在 Docker 已经提供的抽象层之上再叠一层，徒增复杂度，且可能破坏 Docker 内部通信

**关键参数**:
- 服务代码: `uvicorn.run(host="0.0.0.0", port=8001)` 或 `0.0.0.0:8001` — 维持不变
- docker-compose.yml `ports:` — 唯一控制暴露范围的配置点
- 不需要 `.env` 文件管理 host

## Environment Fingerprint

- **任务域**: Docker Compose 多服务项目，微服务架构
- **输入特征**: 15+ 个微服务，每个都有独立的 uvicorn/FastAPI 绑定配置；Docker Compose 统一编排
- **约束条件**: 容器内必须绑 `0.0.0.0`（Docker 网络模型）；暴露范围是运维/安全问题，不是开发问题
- **不适用**:
  - 非容器化部署（裸机/VM 直接运行服务）
  - 不需要 Docker 内部通信的单服务项目
  - 使用 Kubernetes 等更高级的网络抽象（由 Service/Ingress 控制）

## Audit Record

- **验证方式**: iGEM-silk 15 个微服务的 Docker Compose 部署验证
- **测试用例**:
  1. `host="0.0.0.0"` + `ports: "8001:8001"` → LAN 内访问成功
  2. `host="0.0.0.0"` + `ports: "127.0.0.1:8001:8001"` → 仅 localhost 可访问，LAN 拒绝
  3. `host="127.0.0.1"`（错误做法）→ 容器内其他服务无法连接（docker-compose 内部网络不通）
- **成功率**: 100%（策略稳定，已在 15 个服务上验证）
- **局限性**: 当服务即需要暴露到 LAN、又需要被 Docker 内部网络访问时，可能要维护两套端口映射配置。但这是 Docker 的限制，不是此策略的问题

## Usage

- **触发条件**: 添加新微服务、修改服务代码的网络绑定配置、配置安全访问策略
- **调用方式**:
  1. 服务代码中保持 `uvicorn.run(host="0.0.0.0", port=<port>)` 不变
  2. 在 `docker-compose.yml` 的 `ports:` 控制暴露范围
  3. 需要限制外部访问时，加 `127.0.0.1:` 前缀即可
- **注意事项**:
  - 不要试图用环境变量统一管理所有服务的 host——每改一次增加一次出错风险
  - 如果部署时 LAN 内的其他机器需要访问，不要加 `127.0.0.1:` 前缀
  - Docker Desktop for Mac 的网络行为和 Linux Docker 可能有差异——在 Linux 部署机上验证
