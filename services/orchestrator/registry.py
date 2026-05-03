"""
services/orchestrator/registry.py
=================================
Tool Registry — 系统的"配置中心"。

所有工具的 URL、类型、超时、重试策略都集中在这里。
Orchestrator 完全依赖 Registry，不硬编码任何工具信息。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ═══════════════════════════════════════════════════════════════════════════
# ToolConfig 数据类
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ToolConfig:
    """
    单个工具的配置信息。

    Attributes
    ----------
    name : str
        工具唯一名称（与目录名一致）
    url : str
        HTTP 服务地址
    type : str
        功能分类（用于 Scoring Engine 惩罚逻辑）
    timeout : float
        单次请求超时（秒）
    max_retries : int
        失败最大重试次数
    retry_delay : float
        重试间隔（秒）
    batch_size : int
        推荐批量大小
    requires_gpu : bool
        是否需要 GPU
    priority : int
        优先级（0=最高，2=最低）
    description : str
        工具描述
    """

    name: str
    url: str
    type: Literal[
        "toxicity",
        "antioxidant",
        "cpp",
        "mhc",
        "hemolytic",
        "bcell_epitope",
        "allergenicity",
        "tyrosinase_inhibitor",
        "general"
    ]
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    batch_size: int = 50
    requires_gpu: bool = False
    priority: int = 1  # 0=必须, 1=重要, 2=可选
    description: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# 工具注册表
# ═══════════════════════════════════════════════════════════════════════════

TOOL_REGISTRY: dict[str, ToolConfig] = {

    # ══════════════════════════════════════════════════════════════════════
    # P0 工具（融合引擎核心，必须调用）
    # ══════════════════════════════════════════════════════════════════════

    "anoxpepred": ToolConfig(
        name="anoxpepred",
        url="http://localhost:8001",
        type="antioxidant",
        timeout=60.0,
        priority=0,
        description="抗氧化肽预测（AnOxPePred, TensorFlow CNN）"
    ),

    "toxipred3": ToolConfig(
        name="toxipred3",
        url="http://localhost:8003",
        type="toxicity",
        timeout=30.0,
        priority=0,
        description="肽毒性预测（ToxinPred3, Extra Trees + MERCI）"
    ),

    "hemopi2": ToolConfig(
        name="hemopi2",
        url="http://localhost:8004",
        type="hemolytic",
        timeout=60.0,
        priority=0,
        description="肽溶血性预测（HemoPI2, RF/ESM-2）"
    ),

    # ══════════════════════════════════════════════════════════════════════
    # P1 工具（重要，融合引擎应调用）
    # ══════════════════════════════════════════════════════════════════════

    "mhcflurry": ToolConfig(
        name="mhcflurry",
        url="http://localhost:8005",
        type="mhc",
        timeout=30.0,
        priority=1,
        description="MHC I 类结合亲和力预测（MHCflurry, 深度学习）"
    ),

    "plm4cpps": ToolConfig(
        name="plm4cpps",
        url="http://localhost:8006",
        type="cpp",
        timeout=120.0,
        requires_gpu=False,  # 可用 CPU 运行 8M 模型
        priority=1,
        description="细胞穿膜肽预测（pLM4CPPs, ESM-2 + 1D-CNN）"
    ),

    "tipred": ToolConfig(
        name="tipred",
        url="http://localhost:8007",
        type="tyrosinase_inhibitor",
        timeout=30.0,
        priority=1,
        description="酪氨酸酶抑制肽预测（TIPred, Stacked Ensemble）"
    ),

    "algpred2": ToolConfig(
        name="algpred2",
        url="http://localhost:8008",
        type="allergenicity",
        timeout=30.0,
        priority=1,
        description="肽过敏原性预测（AlgPred2, sklearn）"
    ),

    # ══════════════════════════════════════════════════════════════════════
    # P2 工具（可选/备选）
    # ══════════════════════════════════════════════════════════════════════

    "bepipred3": ToolConfig(
        name="bepipred3",
        url="http://localhost:8002",
        type="bcell_epitope",
        timeout=180.0,
        requires_gpu=True,  # ESM-2 模型较重
        priority=2,
        description="线性 B 细胞表位预测（BepiPred-3.0, ESM-2）"
    ),

    "graphcpp": ToolConfig(
        name="graphcpp",
        url="http://localhost:8009",
        type="cpp",
        timeout=60.0,
        requires_gpu=False,
        priority=2,
        description="细胞穿膜肽预测（图神经网络，GraphSAGE）"
    ),

    "mlcpp": ToolConfig(
        name="mlcpp",
        url="http://localhost:8010",
        type="cpp",
        timeout=30.0,
        priority=2,
        description="细胞穿膜肽预测（机器学习方法，RF/SVM）"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# 查询辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_tool(name: str) -> ToolConfig | None:
    """根据名称获取工具配置"""
    return TOOL_REGISTRY.get(name)


def get_tools_by_type(tool_type: str) -> list[ToolConfig]:
    """获取指定类型的所有工具"""
    return [t for t in TOOL_REGISTRY.values() if t.type == tool_type]


def get_all_tools() -> dict[str, ToolConfig]:
    """获取所有工具配置的副本"""
    return TOOL_REGISTRY.copy()


def get_p0_tools() -> list[ToolConfig]:
    """获取 P0 优先级工具（必须调用）"""
    return [t for t in TOOL_REGISTRY.values() if t.priority == 0]


def get_p1_tools() -> list[ToolConfig]:
    """获取 P1 优先级工具（推荐调用）"""
    return [t for t in TOOL_REGISTRY.values() if t.priority == 1]


def get_primary_cpp_tool() -> ToolConfig | None:
    """获取主 CPP 工具（pLM4CPPs 是 P1 中 CPP 预测的首选）"""
    cpp_tools = [t for t in TOOL_REGISTRY.values() if t.type == "cpp"]
    return min(cpp_tools, key=lambda t: t.priority) if cpp_tools else None


def get_gpu_tools() -> list[ToolConfig]:
    """获取需要 GPU 的工具"""
    return [t for t in TOOL_REGISTRY.values() if t.requires_gpu]


def get_cpu_tools() -> list[ToolConfig]:
    """获取可用 CPU 运行工具"""
    return [t for t in TOOL_REGISTRY.values() if not t.requires_gpu]