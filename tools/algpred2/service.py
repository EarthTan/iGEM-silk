"""
service.py
==========
AlgPred2 微服务入口 — 肽/蛋白过敏原性风险预测。

原仓库: https://github.com/raghavagps/algpred2
论文: Sharma et al. "AlgPred 2.0: a web server and standalone package for
      predicting allergenic proteins and mapping of IgE epitopes".

基于氨基酸组成 (AAC) + 随机森林 (Random Forest) 模型预测过敏原性。
在流水线中作为 filter 型服务，阈值 0.3，≥ 0.3 直接淘汰（一票否决）。

使用方式：
    cd tools/AlgPred2
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
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.fasta_service import (
    FastaToolService, create_app, ToolResult,
    BatchPredictRequest, BatchPredictResponse,
)


class AlgPred2Service(FastaToolService):
    """AlgPred2 过敏原性风险预测服务。

    基于 AAC (20维) + Random Forest 预测过敏原性。
    原仓库: https://github.com/raghavagps/algpred2
    流水线: filter 型，阈值 0.3，一票否决。
    """

    tool_name = "algpred2"
    version = "1.4"
    description = "过敏原性风险预测工具（AlgPred2）- Random Forest, AAC特征"
    recommended_batch_size = 50

    # 标准氨基酸顺序 (AlgPred2 AAC 使用 19 个，不含 B/J/O/U/X/Z)
    STD_AA = list("ACDEFGHIKLMNPQRSTVWY")

    async def load_model(self):
        """加载 AlgPred2 Random Forest 模型 (sklearn 0.19.2 训练, joblib 持久化)。"""
        import algpred2 as ap2
        import joblib

        pkg_dir = Path(ap2.__path__[0])
        model_path = pkg_dir / "model" / "rf_model"

        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        # 抑制 sklearn 版本不匹配警告 (模型用 0.19.2 训练, 当前用 1.x 加载)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Trying to unpickle estimator")
            self.model = joblib.load(str(model_path))

        print(
            f"[{self.tool_name}] Model loaded from: {model_path} | "
            f"model=RandomForest | threshold=0.3"
        )

    def _compute_aac(self, sequence: str) -> list[float]:
        """计算氨基酸组成 (AAC) — 19 维特征向量。

        对应 algpred2.aac_comp() 的算法。
        """
        seq = sequence.strip()
        length = len(seq)
        aac_values = []
        for aa in self.STD_AA:
            count = seq.count(aa)
            composition = (count / length) * 100 if length > 0 else 0
            aac_values.append(composition)
        return aac_values

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的过敏原性。

        Args:
            sequence: 氨基酸序列

        Returns:
            ToolResult: score=过敏原概率(0-1), label="Allergen"/"Non-Allergen"
        """
        import numpy as np

        aac_values = self._compute_aac(sequence)
        X = np.array(aac_values).reshape(1, -1)

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Trying to unpickle estimator")
            y_p_score = self.model.predict_proba(X)

        ml_score = float(y_p_score[0][1])
        threshold = 0.3
        prediction = "Allergen" if ml_score >= threshold else "Non-Allergen"

        return ToolResult(
            score=ml_score,
            label=prediction,
            details={
                "sequence_length": len(sequence),
                "model": "Random Forest (AAC)",
                "threshold": threshold,
            },
        )

    async def predict_batch(self, request: BatchPredictRequest) -> BatchPredictResponse:
        """批量预测 — 一次特征矩阵处理全部序列。"""
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        if not request.sequences:
            return BatchPredictResponse(success=True, results=[], total=0, error=None)

        import numpy as np

        sequences = [item.sequence for item in request.sequences]
        ids = [item.peptide_id or "unknown" for item in request.sequences]

        # 批量构建 AAC 特征矩阵
        X = np.array([self._compute_aac(seq) for seq in sequences])

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="Trying to unpickle estimator")
            probs = self.model.predict_proba(X)[:, 1]

        threshold = 0.3
        results: list[ToolResult] = []
        for pid, seq, prob in zip(ids, sequences, probs):
            score = float(prob)
            label = "Allergen" if score >= threshold else "Non-Allergen"
            result = ToolResult(
                score=score,
                label=label,
                details={
                    "sequence_length": len(seq),
                    "model": "Random Forest (AAC)",
                    "threshold": threshold,
                },
            )
            result.peptide_id = pid
            result.sequence = seq
            results.append(result)

        return BatchPredictResponse(
            success=True, results=results, total=len(results), error=None
        )


app = create_app(AlgPred2Service)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8008"))
    print(f"Starting AlgPred2 service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
