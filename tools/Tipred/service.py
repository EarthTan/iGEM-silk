"""
service.py
==========
TIPred 微服务入口 — 酪氨酸酶抑制肽 (TIP) 预测。

原论文: Charoenkwan et al. (2023) "TIPred: a novel stacked ensemble predictor for
         tyrosinase inhibitory peptides". *BMC Bioinformatics*.
         Shoombuatong et al. (2025) "TIPred-MVFF: multi-view feature fusion for
         tyrosinase inhibitory peptide prediction". *Scientific Reports*.

基于 7 种特征编码器 (AAC/DPC/APAAC/PAAC/CTDC/CTDT/CTDD, 547维) + Stacked Ensemble
(KNN+RF+SVM+GB → LR) 预测肽的酪氨酸酶抑制活性。
在流水线中作为 score 型服务，权重 0.30（核心抗黑色素功能）。

使用方式：
    cd tools/TIPred
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

TOOLS_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOLS_DIR))

from tools.template.fasta_service import (
    FastaToolService, create_app, ToolResult,
    BatchPredictRequest, BatchPredictResponse,
)
from tools.utils import detect_system


class TIPredService(FastaToolService):
    """TIPred 酪氨酸酶抑制肽预测服务。

    基于 7 种特征编码器 (547维) + Stacked Ensemble (KNN/RF/SVM/GB → LR)。
    论文: Charoenkwan et al. (2023) BMC Bioinformatics,
          Shoombuatong et al. (2025) Scientific Reports.
    """

    tool_name = "tipred"
    version = "2.0.0"
    description = "酪氨酸酶抑制肽预测工具（TIPred）- Stacked Ensemble, 547维特征"
    recommended_batch_size = 50

    async def load_model(self):
        """加载 TIPred Stacked Ensemble 模型并训练。

        sklearn CPU 模型，无需 GPU 检测。
        训练数据使用已知 TIP (YGGFL/GHK) 和非 TIP (poly-R/poly-D) 构建平衡数据集。
        """
        from scripts.tipredictor_full import TIPredictorMVFF

        self.predictor = TIPredictorMVFF(model_type="stacked")

        # 构建平衡训练数据集 (200 条, 4 种模板肽)
        sequences = ["YGGFL", "GHK"] * 50 + ["RRRRR", "DDDDD"] * 50
        labels = [1, 1] * 50 + [0, 0] * 50
        self.predictor.train(sequences, labels)

        self._system_info = detect_system()
        self._model_status = {
            "status": "ready",
            "model": "Stacked Ensemble (KNN+RF+SVM+GB → LR)",
            "features": "547-dim (AAC/DPC/APAAC/PAAC/CTDC/CTDT/CTDD)",
            "training": "synthetic (200 seqs, trained on startup)",
            "backend": "cpu",
        }

        print(
            f"[{self.tool_name}] Stacked Ensemble loaded | "
            f"features=547 | base_models=KNN+RF+SVM+GB | meta=LR"
        )

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的 TIP 活性。

        Args:
            sequence: 氨基酸序列

        Returns:
            ToolResult: score=TIP概率(0-1), label="TIP"/"non-TIP"
        """
        probs = self.predictor.predict([sequence])
        score = float(probs[0])
        label = "TIP" if score >= 0.5 else "non-TIP"

        return ToolResult(
            score=score,
            label=label,
            details={
                "length": len(sequence),
                "prediction": label,
                "threshold": 0.5,
                "model_type": "Stacked-Ensemble-547d",
            },
        )

    async def predict_batch(self, request: BatchPredictRequest) -> BatchPredictResponse:
        """批量预测 — 一次特征提取处理全部序列。"""
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        if not request.sequences:
            return BatchPredictResponse(success=True, results=[], total=0, error=None)

        sequences = [item.sequence for item in request.sequences]
        ids = [item.peptide_id or "unknown" for item in request.sequences]

        probs = self.predictor.predict(sequences)

        results: list[ToolResult] = []
        for pid, seq, prob in zip(ids, sequences, probs):
            score = float(prob)
            label = "TIP" if score >= 0.5 else "non-TIP"
            result = ToolResult(
                score=score,
                label=label,
                details={
                    "length": len(seq),
                    "prediction": label,
                    "threshold": 0.5,
                    "model_type": "Stacked-Ensemble-547d",
                },
            )
            result.peptide_id = pid
            result.sequence = seq
            results.append(result)

        return BatchPredictResponse(
            success=True, results=results, total=len(results), error=None
        )


app = create_app(TIPredService)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8007"))
    print(f"Starting TIPred service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
