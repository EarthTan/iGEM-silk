"""
service.py
==========
HemoPI2 微服务入口。

将现有的 HemoPI2 溶血性预测工具封装为标准的微服务接口。

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

# 将项目根目录添加到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 直接导入 template 模块，避免触发 services/__init__.py 的完整初始化
from services.template.tool_service import BioToolService, create_app, ToolResult


class HemoPI2Service(BioToolService):
    """
    HemoPI2 肽溶血性预测服务。

    使用 ESM-2 蛋白质语言模型预测肽序列的溶血活性。
    """

    tool_name = "hemopi2"
    version = "1.3.0"
    description = "肽溶血性预测工具（HemoPI2）- ESM-2 蛋白质语言模型"
    recommended_batch_size = 20  # ESM-2 模型较大，限制并发

    async def load_model(self):
        """
        加载 HemoPI2 的 ESM-2 模型。
        """
        import hemopi2
        import torch

        # 获取 hemopi2 包路径
        hp_path = list(hemopi2.__path__)[0]
        model_dir = os.path.join(hp_path, 'Model')

        # 导入 hemopi2_classification 中的模型和 tokenizer
        sys.path.insert(0, os.path.join(hp_path, 'python_scripts'))
        import hemopi2_classification as hc

        # 加载 ESM-2 模型
        self.model = hc.model
        self.tokenizer = hc.tokenizer
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        print(f"[{self.tool_name}] ESM-2 model loaded on {self.device}, ready to predict")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        预测单条序列的溶血活性。

        Args:
            sequence: 氨基酸序列（如 "KWKLFKKIGAVLKVL"）

        Returns:
            ToolResult: 包含 score（0-1 溶血分数）和 label（Hemolytic/Non-Hemolytic）
        """
        import torch
        from transformers import AutoTokenizer

        # 限制序列长度
        if len(sequence) > 40:
            sequence = sequence[:40]

        # 使用 ESM-2 模型预测
        device = self.device
        inputs = self.tokenizer([sequence], padding=True, truncation=True, return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}

        self.model.to(device)
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=1)[:, 1].cpu().numpy()

        score = float(probs[0])
        threshold = 0.55  # ESM 模型默认阈值
        prediction = "Hemolytic" if score >= threshold else "Non-Hemolytic"

        return ToolResult(
            score=score,
            label=prediction,
            details={
                "length": len(sequence),
                "prediction": prediction,
                "threshold": threshold,
                "model_type": "ESM-2"
            }
        )


# 创建 FastAPI 应用
app = create_app(HemoPI2Service)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8004"))
    print(f"Starting HemoPI2 service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)