"""
服务依赖地图 — 每个 pipeline step 需要的微服务。

每个 step 是一个 pipeline 阶段（step1 ~ step5），按需启动对应微服务。

Step 0 是纯本地预处理，不依赖任何微服务。
Step 6（最终排名）也只做数据聚合，不依赖微服务。

Profile 来源: tools/docker-compose.yml 中的实际配置。
⚠️ 实际 profile 与 PLAN.md 不同：大多数评分服务都在 gpu profile 下。
"""

from __future__ import annotations

from typing import Any

# ──────────────────────────────────────────────────────────────────
# Step 服务依赖定义
# ──────────────────────────────────────────────────────────────────

STEP_SERVICES: dict[str, dict[str, Any]] = {
    "step0": {
        "services": [],
        "profiles": [],
        "desc": "数据预处理（长度筛选 + AA 过滤 + DB 写入，纯本地）",
    },
    "step1": {
        "services": ["anoxpepred", "algpred2"],
        "profiles": ["gpu", "cpu"],
        "desc": "轻量初筛 — AnOxPePred(抗氧化) + AlgPred2(过敏原排除)",
    },
    "step2": {
        "services": [
            "anoxpepred",
            "bepipred3",
            "plm4cpps",
            "graphcpp",
            "temstapro",
            "sodope",
            "mhcflurry",
            "toxinpred3",
            "hemopi2",
        ],
        "profiles": ["gpu", "cpu"],
        "desc": "全量评分 — 9 个服务 + 方差感知权重",
    },
    "step3": {
        "services": ["sodope", "temstapro"],
        "profiles": ["cpu", "gpu"],
        "desc": "构造枚举 — SoDoPE(溶解度) + TemStaPro(热稳定性)",
    },
    "step4": {
        "services": ["omegafold"],
        "profiles": ["gpu"],
        "desc": "3D 结构预测 — OmegaFold",
    },
    "step5": {
        "services": ["sasa", "aggrescan3d"],
        "profiles": ["cpu"],
        "desc": "PDB 评估 — SASA(溶剂可及性) + Aggrescan3D(聚集倾向)",
    },
    "step6": {
        "services": [],
        "profiles": [],
        "desc": "最终排名 — 方差感知权重 + 综合报告",
    },
}


def get_step_services(step: str) -> dict[str, Any]:
    """查询指定 step 依赖的服务信息。"""
    info = STEP_SERVICES.get(step)
    if info is None:
        raise KeyError(f"Unknown step: {step!r}. Valid: {list(STEP_SERVICES.keys())}")
    return info


def validate_step(step: str) -> bool:
    """检查 step 名是否有效。"""
    return step in STEP_SERVICES
