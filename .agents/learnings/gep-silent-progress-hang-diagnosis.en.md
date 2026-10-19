---
name: Diagnosis Method for Silent Hangs in Pipeline Scripts v1.0
author: Claude Code
created: 2026-05-17
version: 1.0.0
tags: [diagnosis, debugging, docker, networking, progress, hang, async]
validated: true
---

> English translation of [gep-silent-progress-hang-diagnosis.md](gep-silent-progress-hang-diagnosis.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Diagnosis Method for Silent Hangs in Pipeline Scripts

## Experience

**Problem description**: When the Round 3 script accessed the BepiPred-3.0 container via `127.0.0.1`, the script process stayed alive and the container processed requests normally, but `run.log` had no progress output for 30+ minutes.

**Symptoms**:
- `pgrep -f round03` → process alive
- `docker logs bepipred3 | grep "Batch predict done"` → the container kept processing batches
- `tail -f run.log` → no new log lines
- The container had actually processed 50+ batches, but the script's `asyncio.gather` had not returned

**Root cause**: When docker-proxy (dockerd's userspace proxy) handles httpx HTTP/1.1 keep-alive long connections, requests with long execution times (BepiPred3 ~45s/batch) can have their connections hang. With Semaphore(2), one of the 2 concurrent connections hung, halving overall throughput, and `asyncio.gather` needs all 50 tasks to finish before logging anything, which aggravated the illusion of "no progress".

### Diagnosis Procedure

When a script runs but produces no log output, troubleshoot in the following order:

| Step | Command | Criterion |
|------|------|----------|
| 1. Process alive | `pgrep -f round03_heavy` | The process must be alive |
| 2. Container activity | `docker logs bepipred3 \| tail -5` | Whether there are new requests / completions |
| 3. Batch count | `docker logs bepipred3 \| grep "Batch predict done" \| wc -l` | Whether the count is growing |
| 4. Connection state | `ss -tnp \| grep $(pgrep -f round03_heavy \| head -1)` | Whether the target IP is 127.0.0.1 or 172.18.0.x |
| 5. Concurrency | `ss -tnp \| grep 8002` | Semaphore(N) should show N ESTABLISHED connections |
| 6. curl inside the container | `docker exec bepipred3 curl -s http://localhost:8002/health` | Whether the service itself is healthy |
| 7. Throughput rate | Repeat step 3 after 30 seconds, compute the batch count delta | Normal: N_concurrent × 60/batch_time |

**Key signal**: Step 4 shows the target IP as `127.0.0.1` (docker-proxy) + step 5 shows some connections with no data flowing → docker-proxy hang.

### Fix

Set the `{SERVICE}_HOST` environment variable to the container bridge IP to bypass docker-proxy:

```bash
# get the container bridge IP
docker inspect bepipred3 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
# output: 172.18.0.7

# set the environment variable and restart
export BEPIPRED3_HOST=172.18.0.7
uv run python -m main.stages2.round03_heavy
```

`service_url()` in `main/config.py` reads the environment variable with priority:

```python
def service_url(name: str) -> str:
    env_host = os.environ.get(f"{name.upper()}_HOST")
    host = env_host or SERVICES[name].get("host", SERVICE_HOST)
    # env_host="172.18.0.7" → go directly over the container network
```

### Affected Conditions

docker-proxy hangs are **selective**:
| Service | Time per batch | Affected | Reason |
|------|---------|-----------|------|
| TemStaPro | ~1.3s/batch | ❌ not affected | Requests are fast, keep-alive does not trigger the bug |
| BepiPred3 | ~45s/batch | ✅ affected | Long requests trigger docker-proxy connection state desynchronization |

**Rule**: The longer a request takes, the higher the probability of a docker-proxy keep-alive hang. Requests of ~1s are almost never affected, while ~45s requests frequently are.

### Related Files

- `main/config.py` — `service_url()` environment variable override logic
- `.agents/learnings/gep-docker-container-bridge-ip.md` — existing bridge IP solution (focused on OmegaFold)
- `main/stages2/round05_3d.py` — `_fix_omegafold_docker_network()` auto-detection implementation

### Possible Causes of Similar Symptoms

| Symptom | Possible cause | Distinction |
|------|---------|------|
| No request logs in the container | The script is stuck in an earlier stage | Check the container log timestamps |
| Container errors | Service fault / OOM | Check the container logs for errors |
| Connection count = 0 | Network unreachable | Test with `curl 127.0.0.1:PORT` |
| Connection count normal but no progress | The docker-proxy hang described in this GEP | Use `ss -tnp` to check the target IP |
