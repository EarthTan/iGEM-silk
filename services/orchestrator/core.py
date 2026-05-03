"""
services/orchestrator/core.py
==============================

【这个文件是什么？】
--------------------
core.py 是整个微服务架构的"调度中心"（Orchestrator）。

想象一下：如果你是餐厅的领班（Orchestrator），来了一位客人要点餐（输入一条肽序列）：

1. 你先查查菜单（TOOL_REGISTRY），看看需要哪些厨师（工具服务）
   - 默认情况下，你需要叫来 3 个 P0 厨师：做抗氧化菜的、做毒性检测的、做溶血检测的

2. 你同时给这 3 个厨师下订单（并发调用）
   - 不需要等厨师 A 做完了再叫厨师 B
   - 3 个厨师同时工作，效率最大化

3. 厨师们各自完成工作，返回结果
   - 抗氧化厨师：分数 0.82
   - 毒性检测厨师：分数 0.15（低毒性，安全）
   - 溶血检测厨师：分数 0.22（低溶血，安全）

4. 你把结果汇总（tool_results），交给评分员（scoring.py）
   - 评分员会综合所有结果，计算出一个"融合分数"

5. 你把最终结果返回给客人（FusionResult）
   - 包含：原始序列、融合分数、各工具的详细结果、总耗时

【为什么叫"Orchestrator"（指挥家）？】
------------------------------------
一个交响乐团需要一个指挥家（Conductor）来协调各个乐器（工具）。
没有指挥家，乐手们各弹各的，音乐会乱成一团。

Orchestrator 就是这个指挥家：
  - 它知道有哪些"乐器"可用（通过 registry.py 查询）
  - 它同时指挥所有"乐器"一起演奏（并发调用）
  - 它把各个"乐器"的声音汇总成最终的"乐章"（融合结果）

【什么是"并发"？】
----------------
"并发"（Concurrency）不同于"并行"（Parallelism）。

想象你在做一桌菜：

  顺序执行（一个人做）：
    1. 洗菜（5分钟）
    2. 切菜（5分钟）
    3. 炒菜（10分钟）
    4. 装盘（2分钟）
    总计：22分钟

  并发执行（但还是一个人做）：
    1. 洗菜的时候，锅里烧着水（等待时可以同时做其他事）
    2. 但实际上还是一个人，只能一件事一件事做

  并行执行（多个人一起做）：
    1. 洗菜阿姨洗菜（5分钟）
    2. 切菜叔叔切菜（5分钟）
    3. 炒菜厨师炒菜（10分钟）
    同时进行，总计：10分钟（最慢的那个决定了总时间）

在这个系统里：
  - "并发调用"指的是：同时向多个工具服务发请求（不用等待）
  - httpx.AsyncClient 可以在等待某个工具响应的同时，向另一个工具发请求
  - 这样可以大大减少总等待时间

【什么是"异步"（async/await）？】
--------------------------------
Python 的 async/await 是一种"不阻塞等待"的编程方式。

传统方式（阻塞）：
  result = requests.post(url)  # 这行代码会"卡住"，等服务器返回才继续
  print(result)               # 只有等上面的请求完成，才会执行这里

异步方式（非阻塞）：
  result = await client.post(url)  # 这行代码会"发起请求"然后立刻返回
  # 在等待服务器响应的过程中，可以执行其他代码
  print(result)                   # 当服务器返回时，这行代码才会执行

简单理解：
  - await = "等待，但等待的时候可以去做别的事"
  - 好处：充分利用等待时间做其他事情，提高效率

【核心类和数据结构】
------------------
这个文件定义了 3 个核心数据结构：

  1. PredictionRequest（预测请求）
     - 输入：用户要预测的序列、肽 ID、要调用哪些工具
     - 就像点菜单：客人要点什么菜（序列）、给菜品起什么名字（ID）、要哪些厨师做（tools）

  2. ToolResult（工具结果）
     - 输出：每个工具的预测分数、标签、耗时、错误信息
     - 就像厨师的做菜结果：这个菜做的怎么样（分数）、叫什么名字（标签）、做了多久（latency）

  3. FusionResult（融合结果）
     - 输出：综合所有工具结果后的最终答案
     - 就像领班汇总的结果：客人最终的评分（fused_score）、总耗时（total_latency_ms）

  核心类：Orchestrator（调度器）
     - predict_single()：预测单条序列
     - predict_batch()：批量预测多条序列
     - call_tool()：调用单个工具服务
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .registry import TOOL_REGISTRY, get_p0_tools, ToolConfig


# ═══════════════════════════════════════════════════════════════════════════════
# 第一部分：数据模型（Dataclass）
# ═══════════════════════════════════════════════════════════════════════════════
#
#【什么是 dataclass？】
#--------------------
# dataclass 是 Python 的一种"数据容器"。
# 它适合存放"一组相关的数据"，比如一个预测请求包含：序列、ID、工具列表。
#
# 用 dataclass 的好处：
#   1. 代码更简洁：不需要手写 __init__
#   2. 自动生成 __repr__：打印对象时可以看到所有字段
#   3. 类型提示清晰：每个字段是什么类型一目了然
#
#【为什么需要这些数据结构？】
#---------------------------
# 在复杂的系统里，"数据"和"逻辑"是分开的。
# 数据结构只负责"存放数据"，不负责"处理数据"。
# 这样代码更清晰，也更容易测试。

@dataclass
class PredictionRequest:
    """
    预测请求：用户想要预测一条肽序列。

    【什么时候用？】
    当用户输入一条序列，想要知道它的抗氧化能力、毒性等指标时，
    会创建这样一个请求对象。

    【字段说明】
    ─────────────────────────────────────────────────────────────────────────
    sequence      | 要预测的氨基酸序列，比如 "YVPLPNVPQG"
                   | 不能为空，长度 1-5000 个字符
    ─────────────────────────────────────────────────────────────────────────
    peptide_id    | 这条序列的名字/编号（可选）
                   | 如果不提供，默认是 "unknown"
                   | 比如可以设成 "pep_001"、"sample_20240101" 等
    ─────────────────────────────────────────────────────────────────────────
    tools         | 指定要调用哪些工具（可选）
                   | 如果是 None，默认调用所有 P0 工具（anoxpepred, toxipred3, hemopi2）
                   | 可以指定比如 ["anoxpepred", "mhcflurry"] 只调用这两个

    【使用例子】
    ─────────────────────────────────────────────────────────────────────────
    # 预测单条序列，使用默认工具
    request = PredictionRequest(
        sequence="YVPLPNVPQG",
        peptide_id="pep_001"
    )

    # 预测单条序列，指定工具
    request = PredictionRequest(
        sequence="YVPLPNVPQG",
        peptide_id="pep_001",
        tools=["anoxpepred", "toxipred3", "tipred"]  # 只看抗氧化、毒性、酪氨酸酶抑制
    )
    """

    sequence: str
    """要预测的氨基酸序列"""

    peptide_id: str | None = None
    """肽序列的标识符（可选，默认 None → 设为 "unknown"）"""

    tools: list[str] | None = None
    """要调用的工具名称列表。None = 默认调用所有 P0 工具"""


@dataclass
class ToolResult:
    """
    单个工具的预测结果。

    【什么时候用？】
    当 Orchestrator 调用完一个工具服务后，会得到这样一个结果对象。
    它包含了工具返回的所有信息。

    【字段说明】
    ─────────────────────────────────────────────────────────────────────────
    tool_name     | 工具的名称，比如 "anoxpepred"、"toxipred3"
                   | 用于标识这个结果是哪个工具返回的
    ─────────────────────────────────────────────────────────────────────────
    peptide_id    | 对应的肽 ID（与请求中的 peptide_id 一致）
    ─────────────────────────────────────────────────────────────────────────
    sequence      | 原始的氨基酸序列
    ─────────────────────────────────────────────────────────────────────────
    score         | 预测分数，范围 0.0 ~ 1.0
                   | 如果调用失败，则是 None
                   | 不同工具的分数含义可能不同：
                   |   - 抗氧化：分数越高越好（0.8 = 很强的抗氧化能力）
                   |   - 毒性：分数越低越好（0.1 = 几乎无毒）
                   |   - 溶血：分数越低越好（0.2 = 不容易溶血）
    ─────────────────────────────────────────────────────────────────────────
    label         | 预测的标签，比如 "antioxidant"、"non-toxic"
                   | 如果调用失败，则是 None
    ─────────────────────────────────────────────────────────────────────────
    details       | 附加详细信息（字典格式）
                   | 不同工具可能返回不同的额外信息
                   | 比如可能包含置信度、预测方法的说明等
    ─────────────────────────────────────────────────────────────────────────
    latency_ms    | 这次工具调用花了多少毫秒
                   | 用于性能监控和优化
    ─────────────────────────────────────────────────────────────────────────
    error         | 错误信息
                   | 如果调用成功，则是 None
                   | 如果调用失败，这个字段会包含具体的错误原因

    【使用例子】
    ─────────────────────────────────────────────────────────────────────────
    tool_result = ToolResult(
        tool_name="anoxpepred",
        peptide_id="pep_001",
        sequence="YVPLPNVPQG",
        score=0.82,
        label="antioxidant",
        details={"confidence": 0.95},
        latency_ms=125.5,
        error=None
    )
    """

    tool_name: str
    """工具的名称"""

    peptide_id: str
    """对应的肽 ID"""

    sequence: str
    """原始氨基酸序列"""

    score: float | None = None
    """预测分数（0.0 ~ 1.0），失败时为 None"""

    label: str | None = None
    """预测标签，失败时为 None"""

    details: dict[str, Any] = field(default_factory=dict)
    """附加详细信息（字典）"""

    latency_ms: float = 0.0
    """工具调用耗时（毫秒）"""

    error: str | None = None
    """错误信息，失败时为具体错误描述"""


@dataclass
class FusionResult:
    """
    融合结果：综合所有工具的预测结果后得到的最终答案。

    【什么时候用？】
    当 Orchestrator 完成了所有工具的调用，并且已经计算出融合分数后，
    会返回这样一个结果对象给用户。

    【字段说明】
    ─────────────────────────────────────────────────────────────────────────
    peptide_id       | 肽 ID（与请求中的 peptide_id 一致）
    ─────────────────────────────────────────────────────────────────────────
    sequence         | 原始氨基酸序列
    ─────────────────────────────────────────────────────────────────────────
    tool_results     | 各工具的原始结果（ToolResult 列表）
                      | 包含了每个工具的详细预测信息
                      | 比如第一个工具返回了什么分数、第二个工具返回了什么标签
    ─────────────────────────────────────────────────────────────────────────
    fused_score      | 综合所有工具计算出的融合分数（0.0 ~ 1.0）
                      | 如果所有工具都调用失败，则是 None
                      | 这是用户最关心的"最终评分"
    ─────────────────────────────────────────────────────────────────────────
    fused_label      | 综合所有工具的标签投票得出的最终标签
                      | 比如 "antioxidant" 或 "non-antioxidant"
                      | 如果无法确定，则是 "unknown"
    ─────────────────────────────────────────────────────────────────────────
    total_latency_ms | 处理这个请求总共用时多少毫秒
                      | 包括：所有工具调用的时间 + 评分计算的时间
    ─────────────────────────────────────────────────────────────────────────
    scoring_details  | 融合评分的详细分解（字典）
                      | 包含：基础分数、惩罚乘数、各工具的加权分数等
                      | 用于调试和分析

    【使用例子】
    ─────────────────────────────────────────────────────────────────────────
    fusion_result = FusionResult(
        peptide_id="pep_001",
        sequence="YVPLPNVPQG",
        tool_results=[tool_result_1, tool_result_2, tool_result_3],
        fused_score=0.73,
        fused_label="antioxidant",
        total_latency_ms=523.5,
        scoring_details={
            "base_score": 0.82,
            "penalty_multiplier": 0.89,
            "score_components": {...}
        }
    )
    """

    peptide_id: str
    """肽 ID"""

    sequence: str
    """氨基酸序列"""

    tool_results: list[ToolResult] = field(default_factory=list)
    """各工具的原始结果列表"""

    fused_score: float | None = None
    """融合评分（0.0 ~ 1.0）"""

    fused_label: str | None = None
    """融合标签"""

    total_latency_ms: float = 0.0
    """总处理时间（毫秒）"""

    scoring_details: dict[str, Any] | None = None
    """评分详细分解"""


# ═══════════════════════════════════════════════════════════════════════════════
# 第二部分：Orchestrator 主类
# ═══════════════════════════════════════════════════════════════════════════════
#
#【Orchestrator 是做什么的？】
#----------------------------
# Orchestrator（调度器）是整个系统的大脑。它的职责包括：
#
#   1. 管理 HTTP 客户端的生命周期
#      - 创建和复用连接（避免重复创建 TCP 连接的开销）
#      - 设置超时、并发限制
#
#   2. 并发调用多个工具服务
#      - 同时向 anoxpepred、toxipred3、hemopi2 发请求
#      - 不用等一个完成再叫下一个
#
#   3. 自动重试与错误隔离
#      - 如果某个工具暂时不可用（比如网络抖动），自动重试
#      - 如果某个工具彻底失败（比如服务器宕机），不影响其他工具
#
#   4. 聚合结果并传递给 Scoring Engine
#      - 把所有工具的结果汇总
#      - 交给 scoring.py 计算融合分数

class Orchestrator:
    """
    调度核心：协调多个工具服务，完成肽序列预测。

    【使用方式】
    ─────────────────────────────────────────────────────────────────────────
    # 方式一：使用 async with（推荐，自动管理资源）
    orchestrator = Orchestrator()
    async with orchestrator:
        result = await orchestrator.predict_single(
            PredictionRequest(sequence="YVPLPNVPQG", peptide_id="pep_001")
        )
        print(result.fused_score)

    # 方式二：手动管理生命周期
    orchestrator = Orchestrator()
    try:
        result = await orchestrator.predict_single(
            PredictionRequest(sequence="YVPLPNVPQG", peptide_id="pep_001")
        )
    finally:
        await orchestrator.close()

    【核心参数】
    ─────────────────────────────────────────────────────────────────────────
    timeout      | 默认 HTTP 请求超时（秒）。如果工具超过这个时间没响应，就算超时
                  | 默认 30 秒。如果工具较慢（比如 bepipred3），可能需要设长一点
    max_retries  | 失败最大重试次数。如果工具返回错误，会自动重试
                  | 默认 3 次。如果 3 次都失败，就放弃
    concurrency  | 全局最大并发数。同时最多处理多少个请求
                  | 默认 5。如果设得太大，可能会把服务器挤爆

    【关于默认工具（P0）】
    ─────────────────────────────────────────────────────────────────────────
    如果不指定 tools 参数，默认会调用以下 P0 工具：
      1. anoxpepred  - 抗氧化肽预测
      2. toxipred3   - 毒性检测
      3. hemopi2     - 溶血活性检测

    这三个工具覆盖了"功效"和"安全性"两个核心维度。
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        concurrency: int = 5
    ):
        """
        初始化 Orchestrator。

        【参数说明】
        - timeout: 默认 HTTP 超时时间（秒）
        - max_retries: 失败重试次数
        - concurrency: 全局最大并发数

        【内部初始化】
        - _client: httpx.AsyncClient 实例（延迟创建，按需创建）
        - _semaphore: 信号量，用于限制并发数
        """
        self.default_timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None  # HTTP 客户端（延迟创建）
        self._semaphore = asyncio.Semaphore(concurrency)  # 并发控制信号量

    # ── 生命周期管理 ─────────────────────────────────────────────────────────
    #
    #【为什么要延迟创建客户端？】
    #----------------------------
    # Orchestrator 创建的时候，不一定马上要发请求。
    # 如果提前创建 HTTP 客户端，但一直没用到，会浪费资源。
    # 所以采用"延迟创建"策略：第一次真正需要发请求的时候，才创建客户端。
    #
    #【什么是"上下文管理器"（async with）？】
    #---------------------------------------
    # async with 是一种"自动管理资源"的方式。
    # 就像 try-finally 一样，不管代码是否抛出异常，退出时都会执行清理代码。
    # 使用 async with 的好处：
    #   - 自动关闭 HTTP 客户端
    #   - 代码更简洁，不需要手动调用 close()

    async def _get_client(self) -> httpx.AsyncClient:
        """
        获取或创建 HTTP 客户端（延迟创建）。

        【调用时机】
        在需要发送 HTTP 请求之前调用。

        【实现逻辑】
        1. 如果客户端已经存在且没关闭，直接返回
        2. 如果客户端不存在或已关闭，创建新的

        【连接池配置】
        - max_connections=100：最多同时建立 100 个连接
        - max_keepalive_connections=20：保持 20 个长连接（避免频繁创建/销毁连接）
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.default_timeout),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
            )
        return self._client

    async def close(self) -> None:
        """
        关闭 HTTP 客户端。

        【什么时候调用？】
        - Orchestrator 使用完毕后
        - 或者程序退出前

        【为什么需要手动关闭？】
        HTTP 客户端会占用网络连接和内存。
        如果不关闭，这些资源会一直占用，直到被垃圾回收器回收。
        显式关闭可以立即释放资源。
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "Orchestrator":
        """
        进入上下文管理器时调用（async with orchestrator: 时触发）。
        直接返回 self，这样用户可以开始使用这个对象。
        """
        return self

    async def __aexit__(self, *args) -> None:
        """
        退出上下文管理器时调用（离开 with 块时触发）。
        自动关闭 HTTP 客户端，释放资源。
        """
        await self.close()

    # ── 核心调用逻辑 ─────────────────────────────────────────────────────────
    #
    #【call_tool 是做什么的？】
    #-------------------------
    # call_tool 负责"调用单个工具服务"。
    #
    # 内部流程：
    #   1. 获取 HTTP 客户端
    #   2. 构建请求 URL 和 payload
    #   3. 发送 POST 请求
    #   4. 处理响应（成功/失败）
    #   5. 如果失败，自动重试（最多 max_retries 次）
    #   6. 返回标准化的 ToolResult
    #
    #【什么是"信号量"（Semaphore）？】
    #--------------------------------
    # 想象一下：餐厅有 5 个服务员，同时最多只能服务 5 位客人。
    # 第 6 位客人来了，只能等其中一位空出来。
    #
    # asyncio.Semaphore(5) 就是这个作用：
    #   - 限制同时执行的操作数（这里是 5 个）
    #   - 如果超过 5 个，新的请求会等待之前的完成
    #   - 这样可以防止系统过载

    async def call_tool(
        self,
        tool: ToolConfig,
        sequence: str,
        peptide_id: str | None = None
    ) -> ToolResult:
        """
        调用单个工具服务。

        【参数】
        - tool: 工具配置（包含 URL、超时、重试策略等）
        - sequence: 要预测的氨基酸序列
        - peptide_id: 肽 ID（可选）

        【返回值】
        - ToolResult：标准化的工具结果
          - 如果成功：包含 score、label、details、latency_ms
          - 如果失败：包含 error 字段，score 和 label 为 None

        【内部流程】
        ════════════════════════════════════════════════════════════════════
        ║ Step 1: 获取信号量（限制并发数）                               ║
        ║          如果超过 5 个并发，这个调用会等待                      ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 2: 获取 HTTP 客户端                                       ║
        ║          如果客户端还没创建，这一步会创建                        ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 3: 构建请求                                                ║
        ║          URL = tool.url + "/predict"                            ║
        ║          payload = {"sequence": ..., "peptide_id": ...}        ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 4: 发送请求（可能失败 → 重试）                             ║
        ║          最多重试 max_retries 次                                ║
        ║          每次失败后等待 retry_delay 秒（指数退避）              ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 5: 解析响应                                                ║
        ║          - 如果 HTTP 200 且 success=true → 返回 ToolResult     ║
        ║          - 如果 HTTP 非 200 或 success=false → 记录错误，重试   ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 6: 所有重试都失败 → 返回包含 error 的 ToolResult           ║
        ╚═══════════════════════════════════════════════════════════════════

        【请求格式示例】
        ════════════════════════════════════════════════════════════════════
        POST http://localhost:8001/predict
        Content-Type: application/json

        {
            "sequence": "YVPLPNVPQG",
            "peptide_id": "pep_001"
        }
        ════════════════════════════════════════════════════════════════════

        【响应格式示例】
        ════════════════════════════════════════════════════════════════════
        {
            "success": true,
            "peptide_id": "pep_001",
            "sequence": "YVPLPNVPQG",
            "result": {
                "score": 0.82,
                "label": "antioxidant",
                "details": {"confidence": 0.95}
            },
            "error": null
        }
        ════════════════════════════════════════════════════════════════════
        """
        # 获取信号量（限制并发数）
        async with self._semaphore:
            # 获取 HTTP 客户端
            client = await self._get_client()

            # 构建请求 URL 和 payload
            url = f"{tool.url}/predict"
            payload = {"sequence": sequence, "peptide_id": peptide_id}

            last_error: str | None = None

            # 获取重试次数（优先使用 tool 的配置，否则使用默认值）
            retries = tool.max_retries if hasattr(tool, 'max_retries') else self.max_retries

            # ── 重试循环 ──────────────────────────────────────────────────
            # 最多重试 retries 次。每次失败后等一段时间再试。
            # 等待时间采用"指数退避"策略：第1次等1秒，第2次等2秒...

            for attempt in range(retries):
                try:
                    # 记录开始时间（用于计算延迟）
                    start = time.perf_counter()

                    # 发送 POST 请求
                    response = await client.post(
                        url,
                        json=payload,
                        timeout=tool.timeout  # 使用工具指定的超时时间
                    )

                    # 计算这次调用花了多少毫秒
                    latency_ms = (time.perf_counter() - start) * 1000

                    # ── 解析响应 ────────────────────────────────────────

                    # HTTP 200 表示请求成功
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("success"):
                            # 成功！提取结果数据
                            result_data = data["result"]
                            return ToolResult(
                                tool_name=tool.name,
                                peptide_id=peptide_id or "unknown",
                                sequence=sequence,
                                score=result_data.get("score"),
                                label=result_data.get("label"),
                                details=result_data.get("details", {}),
                                latency_ms=latency_ms
                            )
                        else:
                            # HTTP 200，但业务逻辑失败（比如模型加载失败）
                            last_error = data.get("error", "Unknown error")
                    else:
                        # HTTP 非 200（比如 404、500）
                        last_error = f"HTTP {response.status_code}"

                # ── 异常处理 ──────────────────────────────────────────

                except httpx.TimeoutException:
                    # 请求超时（比如工具响应太慢）
                    last_error = f"Timeout after {tool.timeout}s"

                except httpx.RequestError as e:
                    # 网络错误（比如连接被拒绝、无法解析域名）
                    last_error = f"Request error: {e}"

                except Exception as e:
                    # 其他未知错误（比如工具服务崩溃、返回了非 JSON）
                    last_error = f"Unexpected error: {e}"

                # ── 重试前等待 ────────────────────────────────────────

                # 如果还有重试机会，等一段时间再试
                if attempt < retries - 1:
                    # 获取重试间隔（优先使用 tool 的配置）
                    retry_delay = tool.retry_delay if hasattr(tool, 'retry_delay') else 1.0
                    # 指数退避：第1次等1秒，第2次等2秒，第3次等3秒
                    await asyncio.sleep(retry_delay * (attempt + 1))

            # ── 所有重试都失败 ─────────────────────────────────────────

            # 如果走到这里，说明所有重试都失败了
            # 返回一个包含错误信息的 ToolResult
            return ToolResult(
                tool_name=tool.name,
                peptide_id=peptide_id or "unknown",
                sequence=sequence,
                error=last_error
            )

    # ── 预测入口 ───────────────────────────────────────────────────────────
    #
    #【predict_single 是做什么的？】
    #------------------------------
    # predict_single 处理"单条序列"的预测请求。
    #
    # 内部流程：
    #   1. 决定要调用哪些工具（根据 request.tools 或默认 P0）
    #   2. 并发调用所有工具（同时向多个工具发请求）
    #   3. 收集所有工具的结果
    #   4. 计算融合分数（调用 scoring.py）
    #   5. 返回 FusionResult

    async def predict_single(
        self,
        request: PredictionRequest
    ) -> FusionResult:
        """
        对单条序列执行多工具预测。

        【参数】
        - request: PredictionRequest 对象，包含序列、ID、要调用的工具列表

        【返回值】
        - FusionResult：包含所有工具结果和融合评分

        【内部流程】
        ════════════════════════════════════════════════════════════════════
        ║ Step 1: 决定要调用哪些工具                                       ║
        ║          - 如果 request.tools 有值，使用指定的工具              ║
        ║          - 如果 request.tools 为 None，使用默认 P0 工具         ║
        ║          - 如果指定的工具不存在，回退到 P0                     ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 2: 并发调用所有工具                                         ║
        ║          asyncio.gather(*tasks) 同时执行所有任务                ║
        ║          这比顺序执行快很多（3个工具同时跑，而不是排队跑）       ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 3: 收集结果                                                ║
        ║          tool_results = [result_1, result_2, result_3]          ║
        ║          其中可能包含失败的结果（error != None）               ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 4: 计算融合分数                                             ║
        ║          调用 scoring.py 的 compute_fused_score() 函数          ║
        ║          输入：tool_results（所有工具结果）                     ║
        ║          输出：(fused_score, fused_label, scoring_details)      ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 5: 返回 FusionResult                                        ║
        ╚═══════════════════════════════════════════════════════════════════

        【实际调用例子】
        ════════════════════════════════════════════════════════════════════

        orchestrator = Orchestrator()
        async with orchestrator:
            # 创建预测请求
            request = PredictionRequest(
                sequence="YVPLPNVPQG",
                peptide_id="pep_001"
            )

            # 发起预测
            result = await orchestrator.predict_single(request)

            # 查看结果
            print(f"融合分数: {result.fused_score}")      # 比如 0.73
            print(f"融合标签: {result.fused_label}")     # 比如 "antioxidant"
            print(f"总耗时: {result.total_latency_ms}ms")  # 比如 523.5ms

            # 查看每个工具的结果
            for tr in result.tool_results:
                print(f"{tr.tool_name}: score={tr.score}, label={tr.label}")

        ════════════════════════════════════════════════════════════════════
        """
        # Step 1: 确定要调用的工具

        if request.tools:
            # 如果请求指定了工具列表，过滤出存在的工具
            tools_to_call = [
                TOOL_REGISTRY[name]
                for name in request.tools
                if name in TOOL_REGISTRY
            ]
            # 如果指定的工具都不存在，回退到 P0
            if not tools_to_call:
                tools_to_call = get_p0_tools()
        else:
            # 如果没有指定工具，使用默认 P0
            tools_to_call = get_p0_tools()

        # Step 2: 并发调用所有工具
        start = time.perf_counter()

        # 为每个工具创建一个"调用任务"
        tasks = [
            self.call_tool(tool, request.sequence, request.peptide_id)
            for tool in tools_to_call
        ]

        # asyncio.gather(*tasks) 同时执行所有任务
        # 这会等所有任务完成后才返回
        tool_results = await asyncio.gather(*tasks)

        # 计算总延迟
        total_latency_ms = (time.perf_counter() - start) * 1000

        # Step 3: 创建 FusionResult（此时还没计算融合分数）
        fusion_result = FusionResult(
            peptide_id=request.peptide_id or "unknown",
            sequence=request.sequence,
            tool_results=list(tool_results),
            total_latency_ms=total_latency_ms
        )

        # Step 4: 计算融合分数（调用 Scoring Engine）
        # 使用延迟导入避免循环依赖（scoring.py 导入了 core.py 的 ToolResult）
        scoring_module = __import__('services.orchestrator.scoring', fromlist=['compute_fused_score'])
        fused_score, fused_label, scoring_details = scoring_module.compute_fused_score(tool_results)

        # 将计算结果填充到 FusionResult
        fusion_result.fused_score = fused_score
        fusion_result.fused_label = fused_label
        fusion_result.scoring_details = scoring_details

        return fusion_result

    async def predict_batch(
        self,
        requests: list[PredictionRequest],
        tools: list[str] | None = None
    ) -> list[FusionResult]:
        """
        批量预测多条序列。

        【参数】
        - requests: 多个 PredictionRequest 对象（比如 100 条序列）
        - tools: 指定工具列表（如果提供，会覆盖每个 request 中的 tools 字段）

        【返回值】
        - list[FusionResult]：每个请求的预测结果

        【内部流程】
        ════════════════════════════════════════════════════════════════════
        ║ Step 1: 创建信号量限制并发数（避免同时处理太多序列）            ║
        ║          semaphore = asyncio.Semaphore(3)                        ║
        ║          意思是：同时最多处理 3 条序列                          ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 2: 为每条序列创建"预测任务"                                ║
        ║          tasks = [bounded_predict(req1), bounded_predict(req2), ...]
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 3: 并发执行所有任务                                         ║
        ║          asyncio.gather(*tasks)                                 ║
        ╠═══════════════════════════════════════════════════════════════════
        ║ Step 4: 返回所有结果                                            ║
        ╚═══════════════════════════════════════════════════════════════════

        【为什么需要限制"批量并发数"？】
        ───────────────────────────────────────────────────────────────────
        假设有 100 条序列要预测：
        - 如果没有限制，会同时向工具服务发 100 个请求
        - 工具服务可能会被挤爆（内存不足、连接数过多）
        - 限制为 3 意味着：同时最多处理 3 条，第 4 条要等前面的完成

        【实际调用例子】
        ════════════════════════════════════════════════════════════════════

        orchestrator = Orchestrator()
        async with orchestrator:
            # 创建 100 条序列的批量请求
            requests = [
                PredictionRequest(sequence=f"SEQUENCE_{i}", peptide_id=f"pep_{i}")
                for i in range(100)
            ]

            # 批量预测
            results = await orchestrator.predict_batch(requests)

            # 查看前 10 个结果
            for i, result in enumerate(results[:10]):
                print(f"{i}: score={result.fused_score}")

        ════════════════════════════════════════════════════════════════════
        """
        # 创建信号量限制同时处理的序列数
        # 为什么限制？因为太多并发可能会把工具服务挤爆
        semaphore = asyncio.Semaphore(3)

        async def bounded_predict(req: PredictionRequest) -> FusionResult:
            """
            在信号量限制下执行预测。

            使用 async with semaphore 确保：
              - 同时最多有 3 个预测在执行
              - 其他预测会等待
            """
            async with semaphore:
                # 如果提供了 tools 参数，覆盖 request 中的 tools
                if tools is not None:
                    req.tools = tools
                return await self.predict_single(req)

        # 为每条序列创建预测任务
        tasks = [bounded_predict(req) for req in requests]

        # 并发执行所有任务
        return await asyncio.gather(*tasks)


# ═══════════════════════════════════════════════════════════════════════════════
# 第三部分：CLI 入口（用于快速测试）
# ═══════════════════════════════════════════════════════════════════════════════
#
#【这段代码什么时候用？】
#----------------------
# 当你想直接运行这个文件来测试 Orchestrator 时，这段代码会生效。
# 比如：`python services/orchestrator/core.py`
#
# 它会：
#   1. 创建 Orchestrator 实例
#   2. 发送一条测试序列 "YVPLPNVPQG"
#   3. 打印所有工具的预测结果
#   4. 打印融合分数

async def main():
    """
    简单的 CLI 测试：预测一条序列并打印结果。

    【使用方式】
    python services/orchestrator/core.py

    【预期输出】
    肽: YVPLPNVPQG
    融合分数: 0.73
    融合标签: antioxidant
    总延迟: 523ms

    各工具结果:
      ✅ anoxpepred: score=0.82, label=antioxidant, latency=125ms
      ✅ toxipred3: score=0.15, label=non-toxic, latency=89ms
      ✅ hemopi2: score=0.22, label=non-hemolytic, latency=156ms
    """
    async with Orchestrator() as orchestrator:
        result = await orchestrator.predict_single(
            PredictionRequest(
                sequence="YVPLPNVPQG",
                peptide_id="test_pep_001"
            )
        )

        print(f"肽: {result.sequence}")
        print(f"融合分数: {result.fused_score}")
        print(f"融合标签: {result.fused_label}")
        print(f"总延迟: {result.total_latency_ms:.0f}ms")
        print("\n各工具结果:")
        for tr in result.tool_results:
            status = "✅" if tr.error is None else "❌"
            print(f"  {status} {tr.tool_name}: score={tr.score}, label={tr.label}, latency={tr.latency_ms:.0f}ms, error={tr.error}")


if __name__ == "__main__":
    # 运行 main() 函数
    asyncio.run(main())