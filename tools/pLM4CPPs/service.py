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
from tools.template.fasta_service import BioToolService, create_app, ToolResult


class pLM4CPPsService(BioToolService):
    """
    pLM4CPPs 细胞穿膜肽预测服务。

    使用 ESM2 蛋白质语言模型嵌入 + 1D-CNN 分类器预测肽的穿膜能力。
    模型: ESM2-320 embeddings + CNN (from Kumar et al., J. Chem. Inf. Model. 2025)
    """

    tool_name = "plm4cpps"
    version = "1.0.0"
    description = "细胞穿膜肽预测工具（pLM4CPPs）- ESM2 + 1D-CNN"
    recommended_batch_size = 20  # ESM2 模型较大，限制并发

    # 优化后的阈值 (MCC-optimized on KELM external dataset)
    THRESHOLD = 0.15

    async def load_model(self):
        """
        加载 pLM4CPPs 的 ESM2 模型和 CNN 分类器。
        """
        from predict import load_cpp_model, load_esm2_model, generate_esm2_embeddings
        from sklearn.preprocessing import MinMaxScaler
        import pandas as pd

        # 加载 ESM2 模型
        self.esm_model, self.alphabet = load_esm2_model("esm2_t6_8M_UR50D")

        # 加载 CNN 分类器
        model_path = (
            Path(__file__).parent
            / "pLM4CPPs-main"
            / "models"
            / "ESM2-320"
            / "best_model_320.h5"
        )
        self.cnn_model = load_cpp_model(model_path)

        # 加载训练数据的嵌入并拟合 MinMaxScaler
        # 注意：必须使用训练数据的嵌入来 fit scaler，以确保与模型训练时一致
        emb_path = (
            Path(__file__).parent
            / "pLM4CPPs-main"
            / "embedded_data"
            / "whole_sample_dataset_esm2_t6_8M_UR50D_unified_320_dimension.csv"
        )
        emb_df = pd.read_csv(emb_path, header=0, index_col=0)

        self._scaler = MinMaxScaler()
        self._scaler.fit(emb_df.values)

        # 保存 generate_esm2_embeddings 供 predict_impl 使用
        self._generate_embeddings = generate_esm2_embeddings

        print(
            f"[{self.tool_name}] ESM2 + CNN model loaded, scaler fitted on training data"
        )

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        预测单条序列的穿膜能力。

        Args:
            sequence: 氨基酸序列（如 "RKKRRQRRR"）

        Returns:
            ToolResult: 包含 score（0-1 CPP 概率）和 label（CPP/non-CPP）
        """
        # 限制最小长度
        if len(sequence) < 5:
            return ToolResult(
                score=0.0,
                label="non-CPP",
                details={
                    "warning": "Sequence too short (< 5 amino acids)",
                    "length": len(sequence),
                },
            )

        # 生成 ESM2 嵌入
        embeddings = self._generate_embeddings(
            [("temp", sequence)], model=self.esm_model, alphabet=self.alphabet
        )

        # 使用训练时拟合的 MinMaxScaler 标准化
        X = self._scaler.transform(embeddings.values)

        # 重塑为 1D-CNN 输入 (batch, 320, 1)
        X = X.reshape(X.shape[0], X.shape[1], 1)

        # 使用 CNN 模型预测
        probs = self.cnn_model.predict(X, verbose=0).flatten()
        cpp_prob = float(probs[0])
        label = "CPP" if cpp_prob >= self.THRESHOLD else "non-CPP"

        return ToolResult(
            score=cpp_prob,
            label=label,
            details={
                "length": len(sequence),
                "prediction": label,
                "threshold": self.THRESHOLD,
                "model_type": "ESM2-320_CNN",
            },
        )


# 创建 FastAPI 应用
app = create_app(pLM4CPPsService)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8006"))
    print(f"Starting pLM4CPPs service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
