"""
service.py
==========
MHCflurry 微服务入口 — MHC I 类肽结合亲和力预测。

原仓库: https://github.com/openvax/mhcflurry
论文: O'Donnell et al. (2018) "MHCflurry". *Cell Systems*, 7(1), 129-132.
      O'Donnell et al. (2020) "MHCflurry 2.0". *J Immunol*, 204(1 Supplement), 86.18.

基于 PyTorch 神经网络模型预测肽与 MHC I 类分子的结合亲和力 (IC50 nM)。
支持 14,883 种 MHC 等位基因，肽长度 5-15 aa。

注意: 此服务在流水线中作为"反向指标"——MHC 结合力越强 = 免疫原性风险越高，
在最终评分中被反转 (adjusted = 1.0 - raw)。

使用方式：
    cd tools/MHCflurry
    source .venv/bin/activate
    python service.py

API 端点：
    GET  /           → 服务信息
    GET  /health     → 健康检查
    GET  /info       → 工具信息
    POST /predict    → 单序列预测
    POST /predict/batch → 批量预测
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.fasta_service import (
    FastaToolService, create_app, ToolResult,
    BatchPredictRequest, BatchPredictResponse,
)
from tools.utils import detect_gpu


class MHCflurryService(FastaToolService):
    """MHCflurry MHC I 类肽结合亲和力预测服务。

    使用 PyTorch 神经网络预测肽与 MHC 分子结合强度。
    原仓库: https://github.com/openvax/mhcflurry

    流水线中使用: 反向指标 (SCORE_INVERT)，高亲和力 = 高免疫原性风险。
    """

    tool_name = "mhcflurry"
    version = "2.0.0"
    description = "MHC I 类肽结合亲和力预测（MHCflurry）- 神经网络模型，14,883 等位基因"
    recommended_batch_size = 50

    DEFAULT_ALLELE = "HLA-A*02:01"

    async def load_model(self):
        """加载 MHCflurry 预测器。

        Python 3.13+ 兼容: pipes 模块已在 3.13 中移除，mhcflurry 间接引用它。
        """
        self.gpu_info = detect_gpu()
        print(f"[{self.tool_name}] {self.gpu_info['message']}")

        # Python 3.13+ 兼容性补丁 — pipes 模块已在 Python 3.13 中移除
        if sys.version_info >= (3, 13):
            import shlex

            class _FakePipes:
                @staticmethod
                def quote(s):
                    return shlex.quote(s)

            sys.modules["pipes"] = _FakePipes()

        from mhcflurry import Class1AffinityPredictor

        self.predictor = Class1AffinityPredictor.load()
        self._allele_count = len(self.predictor.supported_alleles)

        print(
            f"[{self.tool_name}] MHCflurry loaded | "
            f"alleles={self._allele_count} | "
            f"default_allele={self.DEFAULT_ALLELE} | "
            f"backend={self.gpu_info['backend']}"
        )

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的 MHC 结合亲和力。

        Args:
            sequence: 氨基酸序列 (5-15 aa)

        Returns:
            ToolResult: score=结合强度(0-1，越高越强), label=Strong/Weak/Non-Binder
        """
        affinity = float(
            self.predictor.predict(
                peptides=[sequence], allele=self.DEFAULT_ALLELE
            )[0]
        )

        score, label = self._affinity_to_score(affinity)

        return ToolResult(
            score=score,
            label=label,
            details={
                "affinity_nM": round(affinity, 2),
                "allele": self.DEFAULT_ALLELE,
                "peptide_length": len(sequence),
                "gpu_backend": self.gpu_info.get("backend", "unknown"),
            },
        )

    async def predict_batch(self, request: BatchPredictRequest) -> BatchPredictResponse:
        """批量预测 — 单次 predict() 调用处理全部序列。

        覆盖基类逐条 predict_impl 方式，避免 N 次 DataFrame 构造开销。
        """
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        if not request.sequences:
            return BatchPredictResponse(success=True, results=[], total=0, error=None)

        peptides = [item.sequence for item in request.sequences]
        ids = [item.peptide_id or "unknown" for item in request.sequences]

        affinities = self.predictor.predict(peptides=peptides, allele=self.DEFAULT_ALLELE)

        results: list[ToolResult] = []
        for pid, seq, aff in zip(ids, peptides, affinities):
            score, label = self._affinity_to_score(float(aff))
            result = ToolResult(
                score=score,
                label=label,
                details={
                    "affinity_nM": round(float(aff), 2),
                    "allele": self.DEFAULT_ALLELE,
                    "peptide_length": len(seq),
                    "gpu_backend": self.gpu_info.get("backend", "unknown"),
                },
            )
            result.peptide_id = pid
            result.sequence = seq
            results.append(result)

        return BatchPredictResponse(
            success=True, results=results, total=len(results), error=None
        )

    def _affinity_to_score(self, affinity: float) -> tuple[float, str]:
        """将 IC50 (nM) 转换为 [0,1] 分数和标签。

        IC50 ≤ 50nM  → 强结合剂 (score 0.5-1.0)
        50-500nM     → 弱结合剂 (score 0.25-0.5)
        > 500nM      → 非结合剂 (score 0.0-0.25)
        """
        if affinity <= 50:
            label = "Strong Binder"
            score = 1.0 - (affinity / 50) * 0.5
        elif affinity <= 500:
            label = "Weak Binder"
            score = 0.5 - ((affinity - 50) / 450) * 0.5
        else:
            label = "Non-Binder"
            score = max(0.0, 0.25 - (min(affinity, 5000) / 5000) * 0.25)

        return round(float(score), 6), label


# 创建 FastAPI 应用
app = create_app(MHCflurryService)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8005"))
    print(f"Starting MHCflurry service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
