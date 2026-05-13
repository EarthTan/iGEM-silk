---
name: ESMFold 依赖版本矩阵 v1.0
author: Claude Code
created: 2026-05-13
version: 1.0.0
tags: [esmfold, docker, dependencies, openfold, fair-esm, cuda]
validated: true
---

# Gene Capsule: ESMFold 依赖版本矩阵

## Experience

**问题类型**: ESMFold 微服务 Docker 构建时依赖版本冲突的排查与修复

**核心策略**:
1. 从完整错误栈追踪根因，不要从最后一行猜测
2. 用排除法确认无直接关系的版本（pydantic/fastapi 不是关键）
3. 一旦发现关键冲突（openfold IPA key 不匹配），从两个方向解决：降 openfold 或升 fair-esm
4. 降 openfold 走不通（CUDA 12.x 不支持 sm_37）→ 走 `strict=False` 路线
5. 连锁依赖升级一次性搞定，不要一个个试（deepspeed→pydantic→fastapi 三条一起升）

**关键参数**:

| 组件 | 可用版本 | 最终选择 | 原因 |
|---|---|---|---|
| openfold | v1.0.1 (IPA 兼容, CUDA 12 编译失败), v2.2.0 (编译通过, IPA 不兼容) | **v2.2.0** + `strict=False` | IPA 缺失层随机初始化，不影响模型其余部分 |
| fair-esm | 2.0.0 (PyPI 与 checkpoint 匹配), GitHub HEAD (IPA 路径更新但更不兼容) | **2.0.0** | 唯一与 `esmfold_3B_v1.pt` 匹配的版本 |
| deepspeed | 0.5.9 (太老, 缺 `deepspeed.comm`), ≥0.9 (支持新 API) | **≥0.9.0** | openfold v2.2.0 需要 |
| fastapi + pydantic | 0.99 + 1.x (deepspeed≥0.9 不兼容), ≥0.100 + 2.x (兼容) | **≥0.100 + ≥2.0** | deepspeed≥0.9 强制升级 pydantic v2 |

## Environment Fingerprint

- **任务域**: Python Docker 微服务构建，GPU/CUDA 环境
- **输入特征**: 多层依赖链 `fair-esm → openfold → deepspeed → pydantic → fastapi`
- **约束条件**: CUDA 12.1 + Python 3.10 + Ubuntu 22.04 基础镜像
- **关键信号**: 看到 `linear_q_points.linear.weight` missing keys → 立即锁定 openfold 版本问题
- **不适用**: Python 3.11+（openfold 有 `not` 参数名冲突）；CPU-only 环境（ESMFold 必须 GPU）

## Audit Record

- **验证方式**: Docker 构建 + 容器内 `POST /predict` 结构预测验证
- **测试用例**:
  1. 构建: `docker build -f tools/ESMFold/Dockerfile -t igem-silk/esmfold:latest .` → 成功 (12.7GB)
  2. 启动: `docker run --gpus all igem-silk/esmfold:latest` → uvicorn 启动, 模型 75s 加载完毕
  3. 预测: 6 残基肽 YDFYTP → 2.3s 返回 PDB, `confidence=0.556`
- **成功率**: 100% (3/3 验证通过)
- **局限性**: IPA 投影层权重随机初始化，结构预测质量未做定量对标（见 Issue #15）

## Usage

- **触发条件**: 任何 ESMFold 相关微服务的 Dockerfile/pyproject 修改
- **调用方式**: 参考 `tools/ESMFold/Dockerfile` 的三层结构和 `tools/ESMFold/service.py` 的模型加载逻辑
- **注意事项**: 永远不要用 `esm.pretrained.esmfold_v1()`，用直接构造 `ESMFold` + `strict=False` 的方式
