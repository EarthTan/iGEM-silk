---
name: Docker Container Bridge IP Direct Connection to Bypass Unstable docker-proxy Connections v1.0
author: Claude Code
created: 2026-05-15
version: 1.0.0
tags: [docker, networking, bridge, proxy, httpx, connection-pool]
validated: true
---

> English translation of [gep-docker-container-bridge-ip.md](gep-docker-container-bridge-ip.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Docker Container Bridge IP Direct Connection to Bypass Unstable docker-proxy Connections

## Experience

**Problem description**: When the host connected to the OmegaFold container via `http://127.0.0.1:8204` (Docker port mapping), the httpx AsyncClient intermittently exhausted its connection pool and hung on requests. At the same moment `docker exec omegafold curl -s http://localhost:8204/health` (inside the container) responded normally.

**Symptoms**:
- httpx raises exceptions such as `ConnectError`, `ReadTimeout`
- Yet the service container is confirmed healthy
- curl from the host sometimes succeeds, sometimes hangs
- docker-proxy (dockerd) is the NAT proxy between host and container

**Root cause**:
```
Request path: httpx → 127.0.0.1:8204 → docker-proxy → container eth0:8204 → OmegaFold
```
docker-proxy (dockerd's userspace proxy) has bugs when handling httpx's HTTP/1.1 keep-alive connection pool:
1. Long-connection reuse causes connection state to fall out of sync
2. After a container restart (the /restart endpoint), docker-proxy does not clean up the old TCP connections
3. Under high concurrency the proxy's epoll model hits race conditions

**Connect directly to the container bridge IP to bypass docker-proxy**:

```python
import subprocess, json, os

def _fix_omegafold_docker_network():
    """Detect the OmegaFold container bridge IP and set OMEGAFOLD_HOST to bypass docker-proxy"""
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
        log(f"  ⚠ OmegaFold network detection failed: {e}")
```

After that, `service_url("omegafold")` reads the bridge IP from the environment variable and goes directly over the container network (Docker's internal DNS), no longer passing through docker-proxy.

**Effect**: From that point until the end of the run, OmegaFold connections succeeded 100% of the time.

### Diagnostic Method

| Method | Command | Effect |
|------|------|------|
| Host curl | `curl -s http://127.0.0.1:8204/health` | ❌ intermittent hangs |
| In-container curl | `docker exec omegafold curl -s http://localhost:8204/health` | ✅ always normal |
| docker-proxy status | `curl -s http://127.0.0.1:8204/health --connect-timeout 5` | Reproduces the problem |
| bridge IP detection | `docker inspect omegafold --format '{{json .NetworkSettings.Networks}}'` | Returns the bridge IP |

### Applicable Scenarios

Any intermittent connection problem when accessing container services through docker-proxy (127.0.0.1:PORT mapping):

- httpx AsyncClient connection pool anomalies
- Connections not refreshed after a container restart
- Host ↔ container communication unstable under load
- The problem worsens after frequent container restarts (the /restart endpoint)

### Inapplicable Scenarios

- Inter-service communication inside Docker Compose (automatic DNS resolution, does not go through the proxy)
- Short-lived, low-concurrency host→container access (docker-proxy works in normal scenarios)
- Services using host network mode (`--network host`)

### Related Files

- `main/stages2/round05_3d.py` — the `_fix_omegafold_docker_network()` implementation
- `main/config.py` — the `service_url()` environment variable override logic
- `.agents/learnings/microservice-host-binding.md` — service binding strategy (related but a different layer)

### Alternative

If the container's bridge network is unavailable (non-default bridge), you can use `docker inspect` to get the IP on another network, or access it directly via Docker DNS (container name):

```bash
# The container name is usable within the same docker-compose network
curl http://omegafold:8204/health
```
