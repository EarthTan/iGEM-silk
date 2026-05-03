"""
services/orchestrator/core.py
===============================
Orchestrator — 调度核心。

职责：
- 管理 HTTP 客户端生命周期
- 并发调用多个工具服务
- 自动重试与错误隔离
- 聚合结果并传递给 Scoring Engine
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .registry import TOOL_REGISTRY, get_p0_tools, ToolConfig


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PredictionRequest:
    """
    单条序列的预测请求。

    Attributes
    ----------
    sequence : str
        氨基酸序列
    peptide_id : str | None
        序列标识符（可选）
    tools : list[str] | None
        指定要调用的工具名称列表。None = 调用所有 P0 工具。
    """
    sequence: str
    peptide_id: str | None = None
    tools: list[str] | None = None  # None = 默认 P0 工具


@dataclass
class ToolResult:
    """
    单个工具的预测结果。

    Attributes
    ----------
    tool_name : str
        工具名称
    peptide_id : str
        对应的肽 ID
    sequence : str
        原始序列
    score : float | None
        预测分数（0-1），失败时为 None
    label : str | None
        预测标签（如 "toxic", "non-toxic"），失败时为 None
    details : dict
        附加信息（如各机制分数字典）
    latency_ms : float
        该工具调用耗时（毫秒）
    error : str | None
        错误信息，失败时为具体错误描述
    """
    tool_name: str
    peptide_id: str
    sequence: str
    score: float | None = None
    label: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    error: str | None = None


@dataclass
class FusionResult:
    """
    融合后的完整预测结果。

    Attributes
    ----------
    peptide_id : str
        肽 ID
    sequence : str
        氨基酸序列
    tool_results : list[ToolResult]
        各工具的原始结果
    fused_score : float | None
        融合评分（0-1）
    fused_label : str | None
        融合标签
    total_latency_ms : float
        总处理时间（毫秒）
    scoring_details : dict | None
        融合评分的详细分解（来自 Scoring Engine）
    """
    peptide_id: str
    sequence: str
    tool_results: list[ToolResult] = field(default_factory=list)
    fused_score: float | None = None
    fused_label: str | None = None
    total_latency_ms: float = 0.0
    scoring_details: dict[str, Any] | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Orchestrator 主类
# ═══════════════════════════════════════════════════════════════════════════

class Orchestrator:
    """
    调度核心。

    使用方式
    --------
    orchestrator = Orchestrator()
    result = await orchestrator.predict_single(
        PredictionRequest(sequence="YVPLPNVPQG", peptide_id="pep_001")
    )
    await orchestrator.close()

    Notes
    -----
    - 默认调用所有 P0 工具（anoxpepred, toxipred3, hemopi2）
    - 通过 tools 参数可指定调用特定工具
    - 并发控制：全局限制 5 个并发请求
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        concurrency: int = 5
    ):
        """
        Parameters
        ----------
        timeout : float
            默认 HTTP 请求超时（秒）
        max_retries : int
            失败重试次数
        concurrency : int
            全局最大并发数
        """
        self.default_timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(concurrency)

    # ── 生命周期管理 ───────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端（延迟创建）"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.default_timeout),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
            )
        return self._client

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "Orchestrator":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    # ── 核心调用逻辑 ───────────────────────────────────────

    async def call_tool(
        self,
        tool: ToolConfig,
        sequence: str,
        peptide_id: str | None = None
    ) -> ToolResult:
        """
        调用单个工具服务。

        Parameters
        ----------
        tool : ToolConfig
            工具配置（URL、超时、重试策略）
        sequence : str
            氨基酸序列
        peptide_id : str | None
            肽 ID

        Returns
        -------
        ToolResult
            标准化后的工具结果（失败时包含 error 字段）
        """
        async with self._semaphore:
            client = await self._get_client()
            url = f"{tool.url}/predict"
            payload = {"sequence": sequence, "peptide_id": peptide_id}

            last_error: str | None = None

            for attempt in range(tool.max_retries if hasattr(tool, 'max_retries') else self.max_retries):
                try:
                    start = time.perf_counter()
                    response = await client.post(
                        url,
                        json=payload,
                        timeout=tool.timeout
                    )
                    latency_ms = (time.perf_counter() - start) * 1000

                    if response.status_code == 200:
                        data = response.json()
                        if data.get("success"):
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
                            last_error = data.get("error", "Unknown error")
                    else:
                        last_error = f"HTTP {response.status_code}"

                except httpx.TimeoutException:
                    last_error = f"Timeout after {tool.timeout}s"
                except httpx.RequestError as e:
                    last_error = f"Request error: {e}"
                except Exception as e:
                    last_error = f"Unexpected error: {e}"

                # 重试前等待
                if attempt < (tool.max_retries if hasattr(tool, 'max_retries') else self.max_retries) - 1:
                    retry_delay = tool.retry_delay if hasattr(tool, 'retry_delay') else 1.0
                    await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避

            # 所有重试都失败
            return ToolResult(
                tool_name=tool.name,
                peptide_id=peptide_id or "unknown",
                sequence=sequence,
                error=last_error
            )

    # ── 预测入口 ─────────────────────────────────────────

    async def predict_single(
        self,
        request: PredictionRequest
    ) -> FusionResult:
        """
        对单条序列执行多工具预测。

        Parameters
        ----------
        request : PredictionRequest
            包含序列、ID、和要调用的工具列表

        Returns
        -------
        FusionResult
            包含所有工具结果和融合评分
        """
        # 确定要调用的工具
        if request.tools:
            tools_to_call = [
                TOOL_REGISTRY[name]
                for name in request.tools
                if name in TOOL_REGISTRY
            ]
            if not tools_to_call:
                tools_to_call = get_p0_tools()
        else:
            tools_to_call = get_p0_tools()

        # 并发调用所有工具
        start = time.perf_counter()
        tasks = [
            self.call_tool(tool, request.sequence, request.peptide_id)
            for tool in tools_to_call
        ]
        tool_results = await asyncio.gather(*tasks)
        total_latency_ms = (time.perf_counter() - start) * 1000

        # 传递所有结果（包括失败的），让 Scoring Engine 处理
        fusion_result = FusionResult(
            peptide_id=request.peptide_id or "unknown",
            sequence=request.sequence,
            tool_results=list(tool_results),
            total_latency_ms=total_latency_ms
        )

        # 应用融合评分（延迟导入避免循环依赖）
        scoring_module = __import__('services.orchestrator.scoring', fromlist=['compute_fused_score'])
        fused_score, fused_label, scoring_details = scoring_module.compute_fused_score(tool_results)
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

        内部自动控制并发（每次最多同时处理 3 条序列），
        每条序列内部并发调用所有工具。

        Parameters
        ----------
        requests : list[PredictionRequest]
            批量请求列表
        tools : list[str] | None
            指定工具列表（如果提供，会覆盖每个 request 中的 tools 字段）

        Returns
        -------
        list[FusionResult]
            每条序列的融合结果
        """
        # 限制同时处理的序列数（避免内存压力）
        semaphore = asyncio.Semaphore(3)

        async def bounded_predict(req: PredictionRequest) -> FusionResult:
            async with semaphore:
                if tools is not None:
                    req.tools = tools
                return await self.predict_single(req)

        tasks = [bounded_predict(req) for req in requests]
        return await asyncio.gather(*tasks)


# ═══════════════════════════════════════════════════════════════════════════
# CLI 入口（用于快速测试）
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    """简单的 CLI 测试"""
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
    asyncio.run(main())