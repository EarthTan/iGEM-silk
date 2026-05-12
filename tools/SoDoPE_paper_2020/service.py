"""
service.py
==========
SoDoPE 微服务入口。

Solubility-Weighted Index (SWI) 蛋白质溶解度预测工具 —
基于原作预计算氨基酸溶解度权重表的快速预测方法。

使用方式：
    cd SoDoPE_paper_2020
    source .venv/bin/activate
    python service.py

API 端点：
    GET  /              → 服务信息
    GET  /health        → 健康检查
    GET  /info          → 工具信息
    POST /predict       → 单序列预测
    POST /predict/batch → 批量预测
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

SERVICE_DIR = Path(__file__).parent
PROJECT_ROOT = SERVICE_DIR.parent.parent
sys.path.insert(0, str(SERVICE_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.fasta_service import FastaToolService, create_app, ToolResult
from tools.utils import detect_gpu, detect_system

sys.path.insert(0, str(Path(__file__).parent / "tools"))
from sodope_integration import SoDoPEIntegration


class SoDoPEService(FastaToolService):
    """
    SoDoPE 蛋白质溶解度预测服务。

    基于 SWI (Solubility-Weighted Index) 方法：
    对序列中每个氨基酸查找预计算的溶解度权重，取均值作为 SWI 分数，
    再通过逻辑回归映射到溶解概率。

    特点：
    - 纯 Python 实现，无需 GPU，无需模型文件
    - 极快：单序列预测 < 1 ms
    - 仅支持 20 种标准氨基酸
    """

    tool_name = "sodope"
    version = "1.0.0"
    description = (
        "蛋白质溶解度预测工具（SoDoPE）- "
        "基于 Solubility-Weighted Index (SWI) 的快速序列溶解度评分"
    )
    recommended_batch_size = 500  # SWI 极轻量，支持大批量

    async def load_model(self):
        """
        加载 SWI 权重表（纯内存操作，无外部模型文件）。
        """
        # GPU/环境检测
        gpu_info = detect_gpu()
        self._system_info = detect_system()
        print(f"[{self.tool_name}] {gpu_info['message']}")

        self.model = SoDoPEIntegration(verbose=True)

        self._model_status = {
            "status": "loaded",
            "method": "SWI (Solubility-Weighted Index)",
            "backend": gpu_info.get("backend", "cpu"),
            "gpu_info": gpu_info,
        }
        print(f"[{self.tool_name}] SWI weights loaded, ready to predict")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        预测单条蛋白质序列的溶解度。

        Args:
            sequence: 氨基酸序列

        Returns:
            ToolResult: score = 溶解概率 (0-1), label = Soluble / Insoluble
        """
        result = self.model.predict_single(sequence)

        return ToolResult(
            score=result["probability"],
            label=result["label"],
            details={
                "swi": result["swi"],
                "probability": result["probability"],
                "sequence_length": result["sequence_length"],
            },
        )


# 创建 FastAPI 应用
app = create_app(SoDoPEService)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8012"))
    print(f"Starting SoDoPE service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
