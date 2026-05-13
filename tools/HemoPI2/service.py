"""
service.py
==========
HemoPI2 微服务入口 — 肽溶血性预测。

原仓库: https://github.com/raghavagps/HemoPI2
论文: Rathore et al. (2025) "HemoPI2". *Communications Biology*, 8, 176.
PyPI:  https://pypi.org/project/hemopi2/

使用 Model 3 (ESM-2 t6) — 基于 ESM-2 蛋白质语言模型的深度学习预测。
Model 1/2 (RF/MERCI) 和 Model 4 (Hybrid2) 需要 perl 运行时，不在此服务中提供。

使用方式：
    cd tools/HemoPI2
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

from tools.template.fasta_service import FastaToolService, create_app, ToolResult
from tools.template.logger import get_logger
from tools.utils import detect_gpu, detect_system


class HemoPI2Service(FastaToolService):
    """HemoPI2 肽溶血性预测服务。

    使用 Model 3 (ESM-2 t6) — ESM-2 蛋白质语言模型 + 序列分类头。
    原仓库: https://github.com/raghavagps/HemoPI2
    """

    tool_name = "hemopi2"
    version = "2.0.0"
    description = "肽溶血性预测工具（HemoPI2）- ESM-2 蛋白质语言模型"
    recommended_batch_size = 20

    async def load_model(self):
        """加载 HemoPI2 ESM-2 模型（Model 3: ESM-2 t6）。

        hemopi2_classification 在 import 时触发模块级 ESM-2 加载（from_pretrained）。
        之后移动模型到检测到的设备 (CUDA > MPS > CPU)。
        """
        import hemopi2
        import torch

        self.gpu_info = detect_gpu()
        self._system_info = detect_system()
        self.logger.info("%s", self.gpu_info["message"])

        hp_path = list(hemopi2.__path__)[0]
        sys.path.insert(0, os.path.join(hp_path, "python_scripts"))
        import hemopi2_classification as hc

        self.model = hc.model
        self.tokenizer = hc.tokenizer

        # 设备选择: CUDA > MPS > CPU
        device_str = "cpu"
        if torch.cuda.is_available():
            device_str = "cuda"
        elif torch.backends.mps.is_available():
            device_str = "mps"
        self.device = torch.device(device_str)

        # 一次性移动模型到设备
        self.model.to(self.device)
        self.model.eval()

        self._model_status = {
            "status": "ready",
            "model": "ESM-2 t6 (Model 3)",
            "model_source": "HuggingFace (facebook/esm2_t6_8M_UR50D)",
            "device": str(self.device),
            "backend": self.gpu_info["backend"],
        }

        self.logger.info(
            "ESM-2 loaded | device=%s | backend=%s",
            self.device, self.gpu_info["backend"],
        )

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的溶血活性。

        Args:
            sequence: 氨基酸序列（如 "KWKLFKKIGAVLKVL"）

        Returns:
            ToolResult: score=溶血概率(0-1), label="Hemolytic"/"Non-Hemolytic"
        """
        import torch

        # 截断长序列（ESM-2 输入限制）
        if len(sequence) > 40:
            sequence = sequence[:40]

        inputs = self.tokenizer(
            [sequence], padding=True, truncation=True, return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)[:, 1].cpu().numpy()

        score = float(probs[0])
        threshold = 0.55
        prediction = "Hemolytic" if score >= threshold else "Non-Hemolytic"

        return ToolResult(
            score=score,
            label=prediction,
            details={
                "length": len(sequence),
                "threshold": threshold,
                "model": "ESM-2 t6 (Model 3)",
                "device": str(self.device),
                "gpu_backend": self.gpu_info.get("backend", "unknown"),
            },
        )


# 创建 FastAPI 应用
app = create_app(HemoPI2Service)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8004"))
    logger = get_logger("hemopi2")
    logger.info("Starting on port %d ...", port)
    uvicorn.run(app, host="0.0.0.0", port=port)

