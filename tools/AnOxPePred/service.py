"""
service.py
==========
AnOxPePred 微服务入口。

将现有的 AnOxPePred 抗氧化肽预测工具封装为标准的微服务接口。

使用方式：
    cd tools/AnOxPePred
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

# 向上跳 2 级目录，作为根路径
root_path = Path(__file__).parents[2]
sys.path.insert(0, str(root_path))

from tools.template.fasta_service import FastaToolService, create_app, ToolResult
from tools.utils import detect_gpu, detect_system


class AnOxPePredService(FastaToolService):
    """
    AnOxPePred 抗氧化肽预测服务。

    基于深度学习模型预测肽序列的抗氧化活性，
    支持两种机制：自由基清除（FRS）和金属螯合（Chel）。
    """

    tool_name = "anoxpepred"
    version = "1.1.0"
    description = "抗氧化肽预测工具（AnOxPePred）- 基于 CNN 深度学习模型"
    recommended_batch_size = 50

    async def load_model(self):
        """
        加载 AnOxPePred 模型。

        初始化 anoxpepred_integration.py 中的预测器。
        模型在服务运行期间保持加载状态，不重复加载。
        """
        gpu_info = detect_gpu()
        self._system_info = detect_system()

        import sys
        sys.path.insert(0, str(Path(__file__).parent / "anoxpepred_sdk"))
        import anoxpepred_integration
        from anoxpepred_integration import AnOxPePredIntegration

        self.model = AnOxPePredIntegration(verbose=True, gpu_info=gpu_info)

        self._model_status = {
            "status": "ready" if self.model.model_mode == "cnn" else "degraded",
            "model_mode": self.model.model_mode,
            "weights_path": str(anoxpepred_integration.WEIGHTS_FILE),
            "backend": self.model.gpu_info.get("backend", "unknown"),
            "load_error": self.model._load_error,
        }

        self.logger.info("Model loaded (mode=%s), ready to predict", self.model.model_mode)

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        预测单条序列的抗氧化活性。

        Args:
            sequence: 氨基酸序列（如 "YVPLPNVPQG"）

        Returns:
            ToolResult: 包含 score（0-1）和 label（antioxidant/non-antioxidant）
        """
        # 调用原有的预测逻辑
        result = self.model.predict_single(sequence)

        # 转换为标准化的 ToolResult
        # score: 综合抗氧化分数（0-1），越大抗氧化能力越强
        # label: 分类标签（Antioxidant / Non-antioxidant）
        return ToolResult(
            score=result.overall_score,
            label=result.overall_class,
            details={
                "frs_score": round(result.frs_score, 4),
                "chel_score": round(result.chel_score, 4),
                "confidence": result.confidence,
                "is_antioxidant": result.is_antioxidant,
                "model_mode": self.model.model_mode,
                "gpu_backend": self.model.gpu_info.get("backend", "unknown"),
                "gpu_count": self.model.gpu_info.get("gpu_count", 0),
            },
        )


# 创建 FastAPI 应用
app = create_app(AnOxPePredService)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    from tools.template.logger import get_logger as _get_logger

    port = int(os.environ.get("PORT", "8001"))
    logger = _get_logger("anoxpepred")
    logger.info("Starting on port %d ...", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
