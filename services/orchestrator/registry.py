"""
services/orchestrator/registry.py
==================================

【这个文件是什么？】
--------------------
registry.py 是整个系统的"通讯录"和"配置中心"。

想象一下：如果要在一家大公司里找某个部门的同事，你需要：
  1. 知道这个人叫什么名字（name）
  2. 知道他的办公室在哪（url）
  3. 知道他的专长是什么（type）
  4. 知道找他需要多久（timeout）

这个文件就是干这件事的：把系统中所有"工具"的配置信息集中管理起来。

【为什么需要单独一个文件来存储这些配置？】
------------------------------------------
这样做有几个好处：

  1. 集中管理：如果要修改某个工具的 URL，只需要改这一个地方
  2. 不重复：所有地方都从这个文件读取配置，不会出现不一致
  3. 解耦：Orchestrator 不需要"知道"具体有哪些工具，它只需要问 Registry 要配置
  4. 易于扩展：要加新工具？在这个文件里加一行就行

【类比】
-------
想象一下餐厅的"座位表"：
  - 每个厨师（在 tools/ 目录下）都有自己的"工位"（运行在特定端口）
  - 这个 registry.py 就是"座位表"，记录着"1号桌是谁、2号桌是谁..."
  - Orchestrator（领班）只需要查这个表，就知道该把任务交给谁

【核心概念：ToolConfig 是什么？】
---------------------------------
ToolConfig 就像是一张"名片"，上面记录了一个工具的所有信息：

  - name     : 这个工具叫什么名字（用于标识，比如 "anoxpepred"）
  - url      : 这个工具的"办公室电话"（HTTP 地址）
  - type     : 这个工具是干什么的（分类，用于后续评分）
  - timeout  : 等这个工具回复，最多等多久（超过就放弃）
  - priority : 这个工具有多重要（0=必须用，1=推荐用，2=可选）

【TOOL_REGISTRY 是什么？】
--------------------------
TOOL_REGISTRY 是一个"字典"（dict）。

在 Python 里，字典就像是一个"标签盒子"：
  - 左边是"标签"（key），比如 "anoxpepred"
  - 右边是"东西"（value），比如一个 ToolConfig 对象

所以 TOOL_REGISTRY 的意思是：
  "当我需要找 'anoxpepred' 时，去这个位置拿它的配置"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ═══════════════════════════════════════════════════════════════════════════════
# 第一部分：ToolConfig 数据类
# ═══════════════════════════════════════════════════════════════════════════════
#
# 【什么是 dataclass？】
# --------------------
# dataclass 是 Python 3.7 引入的一个"装饰器"。
# 它的作用是：自动帮你生成 __init__, __repr__, __eq__ 等方法。
# 简单来说：让你少写很多样板代码。
#
# 【比如普通类要这样写：】
#   class ToolConfig:
#       def __init__(self, name, url, type, ...):
#           self.name = name
#           self.url = url
#           ...
#
# 【用 dataclass 只需要这样：】
#   @dataclass
#   class ToolConfig:
#       name: str
#       url: str
#       ...
#
# 效果是一样的，但代码更简洁。
#
# 【ClassVar 是什么意思？】
# -------------------------
# ClassVar 表示这是一个"类变量"，而不是"实例变量"。
# 简单理解：
#   - 实例变量：每个对象都有自己的值
#   - 类变量：所有对象共享同一个值
# 这里用 ClassVar 是因为 tool_name、version 等属于"类"本身，不属于某个对象


@dataclass
class ToolConfig:
    """
    单个工具的"名片"，包含了工具的所有配置信息。

    【什么时候用？】
    当 Orchestrator 需要调用某个工具时，它会从 TOOL_REGISTRY 里拿到这个对象，
    然后读取 name、url、timeout 等信息，决定怎么调用这个工具。

    【字段说明】
    ─────────────────────────────────────────────────────────
    name          | 工具的唯一标识符，比如 "anoxpepred"
                   | 在代码里用这个名字来引用这个工具
    ─────────────────────────────────────────────────────────
    url           | 工具服务的 HTTP 地址
                   | 比如 "http://localhost:8001"
                   | 如果工具在另一台机器上运行，IP 也要改
    ─────────────────────────────────────────────────────────
    type          | 工具的功能类型，用于 Scoring Engine 的惩罚逻辑
                   | 可选值：
                   |   - "toxicity"         = 毒性检测
                   |   - "antioxidant"       = 抗氧化预测
                   |   - "hemolytic"        = 溶血检测
                   |   - "mhc"              = MHC 结合预测
                   |   - "cpp"              = 细胞穿膜肽
                   |   - "bcell_epitope"   = B 细胞表位
                   |   - "allergenicity"    = 过敏原性
                   |   - "tyrosinase_inhibitor" = 酪氨酸酶抑制
    ─────────────────────────────────────────────────────────
    timeout       | 等待这个工具回复的最大时间（秒）
                   | 如果超过这个时间还没回复，就当它"失败了"
                   | 默认 30 秒，复杂的模型可能需要更久（如 bepipred3 需要 180 秒）
    ─────────────────────────────────────────────────────────
    max_retries   | 失败后最多重试几次
                   | 如果工具返回错误（比如服务器崩溃），可以自动重试
    ─────────────────────────────────────────────────────────
    retry_delay   | 重试之前等多久（秒）
                   | 比如设置为 1.0，表示失败后等 1 秒再试
    ─────────────────────────────────────────────────────────
    batch_size    | 推荐每次批量预测的最大数量
                   | 如果一次发太多请求，服务器可能扛不住
    ─────────────────────────────────────────────────────────
    requires_gpu  | 这个工具是否需要 GPU 才能运行
                   | 如果是 True，系统会确保这个工具被分配到有 GPU 的机器上
    ─────────────────────────────────────────────────────────
    priority      | 工具的优先级（数字越小越重要）
                   |   0 = 必须调用（P0）
                   |   1 = 推荐调用（P1）
                   |   2 = 可选（P2）
    ─────────────────────────────────────────────────────────
    description   | 工具的描述信息，用于日志和文档
    """

    # ── 必填字段（创建 ToolConfig 时必须提供）────────────────────────

    name: str
    """工具的唯一标识符，比如 "anoxpepred" """

    url: str
    """工具服务的 HTTP 地址，比如 "http://localhost:8001" """

    type: Literal[
        "toxicity",  # 毒性检测
        "antioxidant",  # 抗氧化预测
        "cpp",  # 细胞穿膜肽
        "mhc",  # MHC 结合亲和力
        "hemolytic",  # 溶血活性
        "bcell_epitope",  # B 细胞表位
        "allergenicity",  # 过敏原性
        "tyrosinase_inhibitor",  # 酪氨酸酶抑制
        "general",  # 通用工具
    ]
    """工具的功能分类，用于 Scoring Engine 的惩罚逻辑"""

    # ── 可选字段（有默认值，可以不填）───────────────────────────────

    timeout: float = 30.0
    """单次请求超时时间（秒）。超过这个时间没响应就当失败"""

    max_retries: int = 3
    """失败后最多重试几次"""

    retry_delay: float = 1.0
    """重试间隔时间（秒）"""

    batch_size: int = 50
    """推荐批量大小（每个请求多少条序列）"""

    requires_gpu: bool = False
    """是否需要 GPU 才能运行"""

    priority: int = 1
    """优先级：0=必须(P0), 1=推荐(P1), 2=可选(P2)"""

    description: str = ""
    """工具描述，用于日志和文档"""


# ═══════════════════════════════════════════════════════════════════════════════
# 第二部分：工具注册表（TOOL_REGISTRY）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 【什么是字典（dict）？】
# -----------------------
# 字典就像是一个"标签盒"。
# 左边放"标签"（key），右边放"东西"（value）。
# 找东西的时候，只需要说"我要找标签 X"，就能拿到东西。
#
# 比如：TOOL_REGISTRY["anoxpepred"] 就能拿到"anoxpepred 工具的配置"
#
# 【TOOL_REGISTRY 的结构】
# ------------------------
# {
#     "anoxpepred": ToolConfig(...),    # 抗氧化预测工具
#     "toxipred3": ToolConfig(...),     # 毒性检测工具
#     "hemopi2": ToolConfig(...),       # 溶血检测工具
#     ...
# }
#
# 当 Orchestrator 需要调用"anoxpepred"时，它会：
#   1. 问 Registry："anoxpepred 在哪里？" → 得到 url="http://localhost:8001"
#   2. 问 Registry："anoxpepred 是什么类型？" → 得到 type="antioxidant"
#   3. 问 Registry："调用它要等多久？" → 得到 timeout=60.0
#
# 【端口分配】
# -----------
# 每个工具运行在不同的端口上：
#   8000: Orchestrator（调度中心）
#   8001: anoxpepred（抗氧化）
#   8002: bepipred3（B 细胞表位）
#   8003: toxipred3（毒性）
#   8004: hemopi2（溶血）
#   8005: mhcflurry（MHC）
#   8006: plm4cpps（细胞穿膜）
#   8007: tipred（酪氨酸酶抑制）
#   8008: algpred2（过敏原性）
#   8009: graphcpp（细胞穿膜）
#   8010: mlcpp（细胞穿膜）

TOOL_REGISTRY: dict[str, ToolConfig] = {
    # ═══════════════════════════════════════════════════════════════════════
    # P0 工具：融合引擎核心，必须调用
    # ═══════════════════════════════════════════════════════════════════════
    #
    # 【什么是 P0？】
    # ---------------
    # P0 = Priority 0，意思是"最高优先级"。
    # 这三个工具是必须要调用的，因为它们决定了融合分数的核心维度：
    #   - 抗氧化活性（anoxpepred）
    #   - 安全性：毒性（toxipred3）和溶血性（hemopi2）
    #
    # 如果某个 P0 工具调用失败，整个预测可能会被认为"不完整"
    "anoxpepred": ToolConfig(
        name="anoxpepred",
        url="http://localhost:8001",
        type="antioxidant",
        timeout=60.0,  # 抗氧化模型可能较复杂，多给点时间
        priority=0,  # P0 = 必须调用
        description="抗氧化肽预测（AnOxPePred, TensorFlow CNN）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # AnOxPePred 使用 TensorFlow CNN 模型，输入氨基酸序列，输出 0-1 的抗氧化分数
    # 如果 score > 0.5，通常认为有抗氧化活性
    "toxipred3": ToolConfig(
        name="toxipred3",
        url="http://localhost:8003",
        type="toxicity",
        timeout=30.0,  # 毒性检测通常较快
        priority=0,  # P0 = 必须调用
        description="肽毒性预测（ToxinPred3, Extra Trees + MERCI）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # ToxinPred3 使用 Extra Trees + MERCI 分类器
    # 如果预测为"toxic"，会在 Scoring Engine 里扣分
    "hemopi2": ToolConfig(
        name="hemopi2",
        url="http://localhost:8004",
        type="hemolytic",
        timeout=60.0,  # RF/ESM-2 模型需要较长时间
        priority=0,  # P0 = 必须调用
        description="肽溶血性预测（HemoPI2, RF/ESM-2）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # HemoPI2 使用随机森林 + ESM-2 嵌入
    # 溶血性高的话会降低融合分数的安全性评分
    # ═══════════════════════════════════════════════════════════════════════
    # P1 工具：重要，融合引擎应调用
    # ═══════════════════════════════════════════════════════════════════════
    #
    # 【什么是 P1？】
    # ---------------
    # P1 = Priority 1，意思是"推荐调用"。
    # 这些工具可以提供更全面的评估，但如果调用失败（比如服务器忙），
    # 不会完全阻止预测流程，只是分数可能不那么准确。
    "mhcflurry": ToolConfig(
        name="mhcflurry",
        url="http://localhost:8005",
        type="mhc",
        timeout=30.0,
        priority=1,  # P1 = 推荐调用
        description="MHC I 类结合亲和力预测（MHCflurry, 深度学习）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # MHCflurry 使用深度学习预测肽与 MHC 分子的结合亲和力
    # 对于护肤肽来说，这个指标相对不那么关键（主要看抗氧化和安全性）
    "plm4cpps": ToolConfig(
        name="plm4cpps",
        url="http://localhost:8006",
        type="cpp",
        timeout=120.0,  # ESM-2 模型较大，需要更长时间
        requires_gpu=False,  # 但可以用 CPU 运行（8M 参数模型）
        priority=1,  # P1 = 推荐调用
        description="细胞穿膜肽预测（pLM4CPPs, ESM-2 + 1D-CNN）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # pLM4CPPs 使用 ESM-2 嵌入 + 1D-CNN 分类器
    # 这个工具用于预测肽能否穿透细胞膜，对于功效肽很重要
    "tipred": ToolConfig(
        name="tipred",
        url="http://localhost:8007",
        type="tyrosinase_inhibitor",
        timeout=30.0,
        priority=1,  # P1 = 推荐调用
        description="酪氨酸酶抑制肽预测（TIPred, Stacked Ensemble）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # TIPred 使用 Stacked Ensemble 模型预测酪氨酸酶抑制活性
    # 对于抗黑色素沉积的护肤品设计，这个指标很重要
    "algpred2": ToolConfig(
        name="algpred2",
        url="http://localhost:8008",
        type="allergenicity",
        timeout=30.0,
        priority=1,  # P1 = 推荐调用
        description="肽过敏原性预测（AlgPred2, sklearn）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # AlgPred2 使用 sklearn 的机器学习方法预测过敏原性
    # 如果预测为过敏原，会严重影响肽的安全性评分
    # ═══════════════════════════════════════════════════════════════════════
    # P2 工具：可选/备选
    # ═══════════════════════════════════════════════════════════════════════
    #
    # 【什么是 P2？】
    # ---------------
    # P2 = Priority 2，意思是"可选"。
    # 这些工具提供额外的参考信息，但如果调用失败，完全不影响主流程。
    # 通常用于科研场景，或者当主工具不可用时的备份。
    "bepipred3": ToolConfig(
        name="bepipred3",
        url="http://localhost:8002",
        type="bcell_epitope",
        timeout=180.0,  # ESM-2 模型非常重，需要很长时间
        requires_gpu=True,  # 必须用 GPU，否则跑不动
        priority=2,  # P2 = 可选
        description="线性 B 细胞表位预测（BepiPred-3.0, ESM-2）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # BepiPred-3.0 使用 ESM-2 蛋白质语言模型
    # 这个工具对于护肤肽设计来说优先级较低（B 细胞表位与功效关系不大）
    "graphcpp": ToolConfig(
        name="graphcpp",
        url="http://localhost:8009",
        type="cpp",
        timeout=60.0,
        requires_gpu=False,
        priority=2,  # P2 = 可选
        description="细胞穿膜肽预测（图神经网络，GraphSAGE）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # GraphCPP 使用图神经网络（GraphSAGE）预测细胞穿膜能力
    # 可以作为 plm4cpps 的备选，但优先级较低
    "mlcpp": ToolConfig(
        name="mlcpp",
        url="http://localhost:8010",
        type="cpp",
        timeout=30.0,
        priority=2,  # P2 = 可选
        description="细胞穿膜肽预测（机器学习方法，RF/SVM）",
    ),
    # ───────────────────────────────────────────────────────────────────
    # MLCPP 使用传统的随机森林或 SVM 方法预测细胞穿膜能力
    # 速度较快，可以作为快速的初步筛选
}


# ═══════════════════════════════════════════════════════════════════════════════
# 第三部分：查询辅助函数
# ═══════════════════════════════════════════════════════════════════════════════
#
# 【这些函数是做什么的？】
# -----------------------
# TOOL_REGISTRY 是一个字典，查询起来是这样的：
#   tool = TOOL_REGISTRY["anoxpepred"]
#
# 但有时候我们不知道具体名字，只知道"类型"或"优先级"。
# 这时候就需要这些辅助函数来帮我们"筛选"和"查找"。
#
# 【函数命名规则】
# ----------------
#   get_xxx()      → 获取单个，如果找不到返回 None
#   get_all_xxx()  → 获取所有满足条件的，返回一个列表


def get_tool(name: str) -> ToolConfig | None:
    """
    根据工具名称获取配置。

    【使用场景】
    已知工具名字（比如 "anoxpepred"），想要获取它的完整配置。

    【参数】
    - name: 工具的名称，比如 "anoxpepred"

    【返回值】
    - ToolConfig 对象（如果找到）
    - None（如果没找到）

    【例子】
    tool = get_tool("anoxpepred")
    if tool:
        print(f"URL: {tool.url}")
    """
    return TOOL_REGISTRY.get(name)


def get_tools_by_type(tool_type: str) -> list[ToolConfig]:
    """
    获取指定类型的所有工具。

    【使用场景】
    想把所有"毒性检测"相关的工具都找出来。

    【参数】
    - tool_type: 工具类型，比如 "toxicity"、"antioxidant" 等

    【返回值】
    - 满足条件的所有 ToolConfig 对象（列表）

    【例子】
    toxic_tools = get_tools_by_type("toxicity")
    for tool in toxic_tools:
        print(f"{tool.name}: {tool.url}")
    """
    return [t for t in TOOL_REGISTRY.values() if t.type == tool_type]


def get_all_tools() -> dict[str, ToolConfig]:
    """
    获取所有工具配置的副本。

    【使用场景】
    想遍历系统中所有工具，或者想知道总共有多少个工具。

    【返回值】
    - TOOL_REGISTRY 的拷贝（字典）
    注意：返回的是拷贝，不是原件，这样修改不会影响原注册表

    【例子】
    all_tools = get_all_tools()
    print(f"共有 {len(all_tools)} 个工具")
    """
    return TOOL_REGISTRY.copy()


def get_p0_tools() -> list[ToolConfig]:
    """
    获取 P0 优先级工具（必须调用的工具）。

    【使用场景】
    初始化 Orchestrator 时，需要确保这些工具都能正常工作。

    【返回值】
    - 所有 priority=0 的 ToolConfig 对象（列表）

    【例子】
    p0_tools = get_p0_tools()
    for tool in p0_tools:
        print(f"P0 工具: {tool.name} (url={tool.url})")
    """
    return [t for t in TOOL_REGISTRY.values() if t.priority == 0]


def get_p1_tools() -> list[ToolConfig]:
    """
    获取 P1 优先级工具（推荐调用的工具）。

    【返回值】
    - 所有 priority=1 的 ToolConfig 对象（列表）
    """
    return [t for t in TOOL_REGISTRY.values() if t.priority == 1]


def get_gpu_tools() -> list[ToolConfig]:
    """
    获取需要 GPU 才能运行的工具。

    【使用场景】
    部署服务时，需要确保有 GPU 的机器来运行这些工具。

    【返回值】
    - 所有 requires_gpu=True 的 ToolConfig 对象（列表）

    【例子】
    gpu_tools = get_gpu_tools()
    if gpu_tools:
        print(f"需要 GPU 的工具: {[t.name for t in gpu_tools]}")
    """
    return [t for t in TOOL_REGISTRY.values() if t.requires_gpu]


def get_cpu_tools() -> list[ToolConfig]:
    """
    获取可用 CPU 运行工具（不需要 GPU）。

    【使用场景】
    在资源有限的机器上部署时，可以先跑这些工具。

    【返回值】
    - 所有 requires_gpu=False 的 ToolConfig 对象（列表）
    """
    return [t for t in TOOL_REGISTRY.values() if not t.requires_gpu]

