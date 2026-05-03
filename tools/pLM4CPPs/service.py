"""
service.py
==========
pLM4CPPs 微服务入口。

将现有的 pLM4CPPs 细胞穿膜肽预测工具封装为标准的微服务接口。

使用方式：
    cd tools/pLM4CPPs
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

# 将 tools/pLM4CPPs/ 目录添加到路径
TOOLS_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOLS_DIR))

# 直接导入 template 模块，避免触发 services/__init__.py 的完整初始化
from services.template.tool_service import BioToolService, create_app, ToolResult


class pLM4CPPsService(BioToolService):
    """
    pLM4CPPs 细胞穿膜肽预测服务。

    使用 ESM2 蛋白质语言模型嵌入 + 1D-CNN 分类器预测肽的穿膜能力。
    """

    tool_name = "plm4cpps"
    version = "1.0.0"
    description = "细胞穿膜肽预测工具（pLM4CPPs）- ESM2 + 1D-CNN"
    recommended_batch_size = 20  # ESM2 模型较大，限制并发

    async def load_model(self):
        """
        加载 pLM4CPPs 的 ESM2 模型和 CNN 分类器。
        """
        from predict import load_cpp_model, load_esm2_model

        # 加载 ESM2 模型
        self.esm_model, self.alphabet = load_esm2_model("esm2_t6_8M_UR50D")

        # 加载 CNN 分类器
        model_path = Path(__file__).parent / "pLM4CPPs-main" / "models" / "ESM2-320" / "best_model_320.h5"
        self.cnn_model = load_cpp_model(model_path)

        print(f"[{self.tool_name}] ESM2 + CNN model loaded, ready to predict")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        预测单条序列的穿膜能力。

        Args:
            sequence: 氨基酸序列（如 "RKKRRQRRR"）

        Returns:
            ToolResult: 包含 score（0-1 CPP 概率）和 label（CPP/non-CPP）
        """
        from predict import generate_esm2_embeddings, predict_cpp

        # 限制最小长度
        if len(sequence) < 5:
            return ToolResult(
                score=0.0,
                label="non-CPP",
                details={
                    "warning": "Sequence too short (< 5 amino acids)",
                    "length": len(sequence)
                }
            )

        # 生成 ESM2 嵌入
        embeddings = generate_esm2_embeddings(
            [("temp", sequence)],
            model=self.esm_model,
            alphabet=self.alphabet
        )

        # 使用 CNN 模型预测
        result = predict_cpp(
            [("temp", sequence)],
            model=self.cnn_model,
            embeddings=embeddings
        )

        row = result.iloc[0]
        cpp_prob = float(row['CPP_Probability'])
        label = row['Prediction_Label']

        return ToolResult(
            score=cpp_prob,
            label=label,
            details={
                "length": len(sequence),
                "prediction": label,
                "threshold": 0.5
            }
        )


# 创建 FastAPI 应用
app = create_app(pLM4CPPsService)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8006"))
    print(f"Starting pLM4CPPs service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)