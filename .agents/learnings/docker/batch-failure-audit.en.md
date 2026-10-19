---
name: Batch Audit Strategy for Build Failures v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [debugging, methodology, efficiency, docker, ci, iGEM-silk]
validated: true
---

> English translation of [batch-failure-audit.md](batch-failure-audit.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: Batch Audit Strategy for Build Failures

## Experience

**Problem type**: The inefficient loop of fixing multi-service Docker build failures one at a time and waiting for CI to retry.

**Core strategy**: After the first build failure, immediately run a full audit scan instead of waiting for CI to report errors round by round—fixing only one thing at a time is extremely inefficient in multi-service scenarios.

**Key parameters**: The audit checklist

A full Docker build of 15 services takes 2-10 minutes per service. Fixing only one failure at a time → fix one → wait for the next build round → discover a new problem → 7-8 rounds, taking several hours.

### Audit Checklist

After the first failure, immediately scan with scripts:

1. All `dockerfile:` paths → `grep 'dockerfile:' docker-compose.yml`
2. All `COPY` statements in all Dockerfiles → `grep '^COPY' tools/*/Dockerfile`
3. All `WORKDIR` and `CMD` → `grep 'WORKDIR\|^CMD' tools/*/Dockerfile`
4. Python environment differences across all base images → check the `FROM` lines
5. All pip/uv dependency installation methods → check `RUN pip` vs `RUN uv`
6. Whether any COPY misses shared files → `tools/utils.py`, `tools/template/`

## Environment Fingerprint

- **Task domain**: Multi-service Docker project builds
- **Input characteristics**: First build or large-scale configuration changes
- **Constraints**: Builds are slow (more than 1 minute per service)
- **Not applicable**: Single-service projects, or a single error with a known root cause

## Audit Record

- **Validation method**: Summarized after a full Docker build of 15 iGEM-silk services went through 7-8 rounds of CI failures
- **Efficiency comparison**: Incremental fixing ~3 hours vs. batch fixing after a full audit ~30 minutes
- **Fix validation**: Later, when adding new services, using the audit checklist passed in one round

## Usage

- **Trigger conditions**: Two or more failures in a multi-service Docker build
- **How to invoke**: Run the audit checklist scripts → collect all problems → fix them in one pass → rebuild
- **Caveats**: The checklist should be updated continuously as new problems are found
