---
name: Microservice Network Binding Strategy v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [docker, networking, microservice, security, docker-compose]
validated: true
---

> **English** | [中文](microservice-host-binding.zh.md)

# Gene Capsule: Microservice Network Binding Strategy

## Experience

**Problem type**: Network binding strategy for microservices in a Docker Compose multi-service architecture — should the hardcoded `0.0.0.0` be changed to something controlled by environment variables?

**Core strategy**: Keep `0.0.0.0` (or the `0.0.0.0:8001` form) unchanged in all microservice code; the external exposure scope is controlled by the `ports:` mapping in `docker-compose.yml`. Do not touch the service code, do not change the host configuration, do not add a .env file.

**Why**:
1. **Docker internal communication must use `0.0.0.0`** — containers must bind `0.0.0.0` internally, otherwise other services on the Docker network cannot reach them. This is a basic requirement of the Docker network model
2. **External exposure is controlled by Docker Compose** — the port mapping syntax of `docker-compose.yml` naturally supports access control:
   - `"8001:8001"` → reachable from all machines on the LAN
   - `"127.0.0.1:8001:8001"` → reachable only from localhost on this machine
3. **Modifying the service code is a pointless exercise** — writing `TOOL_HOST` environment variable logic into the service code means stacking another layer on top of the abstraction Docker already provides, which only adds complexity and may break Docker internal communication

**Key parameters**:
- Service code: `uvicorn.run(host="0.0.0.0", port=8001)` or `0.0.0.0:8001` — kept unchanged
- docker-compose.yml `ports:` — the single configuration point controlling exposure scope
- No `.env` file is needed to manage the host

## Environment Fingerprint

- **Task domain**: Docker Compose multi-service project, microservice architecture
- **Input characteristics**: 15+ microservices, each with its own uvicorn/FastAPI binding configuration; orchestrated uniformly by Docker Compose
- **Constraints**: Containers must bind `0.0.0.0` (Docker network model); exposure scope is an operations/security concern, not a development concern
- **Not applicable**:
  - Non-containerized deployment (services running directly on bare metal/VM)
  - Single-service projects that need no Docker internal communication
  - Higher-level network abstractions such as Kubernetes (controlled by Service/Ingress)

## Audit Record

- **Validation method**: Docker Compose deployment validation of the 15 iGEM-silk microservices
- **Test cases**:
  1. `host="0.0.0.0"` + `ports: "8001:8001"` → accessible within the LAN
  2. `host="0.0.0.0"` + `ports: "127.0.0.1:8001:8001"` → reachable only from localhost, LAN denied
  3. `host="127.0.0.1"` (the wrong approach) → other services in the container cannot connect (docker-compose internal network unreachable)
- **Success rate**: 100% (the strategy is stable and has been validated on 15 services)
- **Limitations**: When a service needs to be exposed to the LAN and also accessed from the Docker internal network, two sets of port mapping configurations may have to be maintained. But that is a limitation of Docker, not of this strategy

## Usage

- **Trigger conditions**: Adding a new microservice, modifying a service's network binding configuration, configuring a security access policy
- **How to invoke**:
  1. Keep `uvicorn.run(host="0.0.0.0", port=<port>)` unchanged in the service code
  2. Control the exposure scope in the `ports:` of `docker-compose.yml`
  3. To restrict external access, simply add the `127.0.0.1:` prefix
- **Caveats**:
  - Do not try to manage the host of all services uniformly with environment variables — every change adds another chance of error
  - If other machines on the LAN need access at deployment time, do not add the `127.0.0.1:` prefix
  - The network behavior of Docker Desktop for Mac may differ from Linux Docker — validate on the Linux deployment machine
