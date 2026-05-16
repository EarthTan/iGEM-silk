---
name: 多层依赖链排错方法论 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [troubleshooting, dependencies, python, docker, methodology]
validated: true
supersedes: dependency-version-troubleshooting.md
---

# Gene Capsule: 多层依赖链排错方法论

## Experience

**问题类型**: Python Docker 微服务构建/运行时，深层依赖链（4+ 层）的版本冲突排查与修复。

**核心策略**:
1. **读完整错误栈，不从最后一行猜** — 倒数第 1-2 行通常是症状（如 `ImportError`），根因在更前面（如 `KeyError` from checkpoint loading）
2. **排除法确认无关组件** — 先确定哪些包与报错无关（如 pydantic/fastapi 报错但实际不是根因），缩小范围
3. **锁定关键冲突后双向尝试** — 降级 vs 升级两个方向。降级走不通再升级（如 openfold v1 → CUDA 编译失败，才走 v2 + `strict=False`）
4. **连锁依赖升级一次性搞定** — 当升级 A 包导致 B/C/D 不兼容时，查出 B/C/D 的兼容版本列表，一次性升级全部，不要一个个试（避免每改一个就触发一遍 Docker 重编译）
5. **运行时补丁兜底** — 当某个包不能升级时（如被其他依赖锁死），运行时 monkey-patch 可以解封。如 `numpy.BUFSIZE = 8192`、`torch._six` shim

**关键参数**:
- 典型依赖链深度: 4+ 层（如 `fair-esm → openfold → deepspeed → pydantic → fastapi`）
- 每次 Docker 重编译 cost: ~12min（openfold CUDA 编译）
- 根因定位时间: 从 1-2h（试错法）压缩到 ~15min（完整栈追踪 + 排除法）

## Environment Fingerprint

- **任务域**: Python Docker 微服务，GPU/CUDA 环境，科学计算/ML 依赖管理
- **输入特征**: 深层依赖链（4+ 层），跨包 API 变动（重构/改名），CUDA 版本约束
- **约束条件**: 每次重试成本高（Docker 层缓存 + CUDA 编译）；包与包之间无 explicit 兼容性声明
- **不适用**:
  - 单层依赖（直接 `pip install` 就能解决）
  - 纯前端/JS 项目（npm 的依赖解析不同）
  - 已有现成 Docker 镜像的场景（直接用别人的镜像）
  - 依赖链短且确定（<=2 层时直接试更快）
- **关键信号**:
  - 看到 `missing keys` 或 `KeyError` in checkpoint loading → 锁定版本不匹配（openfold/fair-esm 问题）
  - 看到 `'module' has no attribute 'X'` → 包版本过老/过新（deepspeed.comm）
  - 看到 `nvcc fatal: Unsupported gpu architecture` → CUDA 版本不兼容（sm_37 deprecated）

## Audit Record

- **验证方式**: 在 ESMFold 微服务 Docker 构建中实际应用并验证
- **测试用例**:
  1. openfold IPA key mismatch → 完整栈追踪发现 `linear_q_points` → 双向尝试（降 openfold vs 升 fair-esm）→ 降走不通 → `strict=False`
  2. `deepspeed.comm` missing → 排除 pydantic/fastapi → 锁定 deepspeed 版本过老 → 升级发现 pydantic v2 冲突 → 一次性升级 fastapi + pydantic + deepspeed
  3. `numpy.BUFSIZE` removed → 追溯到 deepspeed import → pin `numpy<2` 在 Layer 1 解决
- **成功率**: 100%（3/3 问题均在该方法论指导下解决）
- **局限性**: 高度依赖读错误栈的能力——只看最后一行会漏关键信息；不适用于编译型语言（Go/Rust）的依赖管理

## Usage

- **触发条件**: 任何非平凡的 Python 依赖版本冲突（>2 层依赖链，或涉及 CUDA/native 编译）
- **调用方式**: 遇到 ImportError/RuntimeError 时：读完整栈 → 定位根因组件 → 双向尝试版本 → 连锁升级一次性搞定 → 运行时补丁兜底
- **注意事项**:
  - 官方文档可能过时（ESMFold 说 Python≤3.9，实际 3.10 可用）
  - Docker 缓存可能误导（`docker compose build` 和 `docker build -f Dockerfile` 缓存策略不同）
  - 参考具体案例: `gep-esmfold-dependency-matrix.md`（版本矩阵）和 `gep-esmfold-docker-build.md`（Docker 构建）
