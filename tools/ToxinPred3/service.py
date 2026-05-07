"""
service.py
==========
ToxinPred3 微服务入口。

将现有的 ToxinPred3 毒性预测工具封装为标准的微服务接口。

使用方式：
    cd tools/ToxinPred3
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

# 将 tools/ 目录添加到路径，以便导入 toxinpred_features
TOOLS_DIR = Path(__file__).parent
sys.path.insert(0, str(TOOLS_DIR))

# 直接导入 template 模块，避免触发 services/__init__.py 的完整初始化
from tools.template.fasta_service import BioToolService, create_app, ToolResult


class ToxinPred3Service(BioToolService):
    """
    ToxinPred3 肽毒性预测服务。

    基于 Extra Trees 分类器预测肽序列的毒性。
    直接加载模型，避免 toxinpred3 包的 CLI bug。
    """

    tool_name = "toxipred3"
    version = "1.0.0"
    description = "肽毒性预测工具（ToxinPred3）- Extra Trees 分类器"
    recommended_batch_size = 50

    async def load_model(self):
        """加载 ToxinPred3 模型"""
        import toxinpred3
        import joblib
        import os

        # 获取 toxinpred3 包路径
        tp3_path = list(toxinpred3.__path__)[0]
        model_path = os.path.join(tp3_path, "model", "toxinpred3.0_model.pkl")

        # 直接加载 ExtraTreesClassifier
        self.model = joblib.load(model_path)

        # 导入特征提取函数
        from toxinpred_features import extract_features

        # 保存特征提取函数
        self.extract_features = extract_features

        print(f"[{self.tool_name}] Model loaded, ready to predict")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        预测单条序列的毒性。

        Args:
            sequence: 氨基酸序列（如 "KWKLFKKIGAVLKVL"）

        Returns:
            ToolResult: 包含 score（0-1 毒性分数）和 label（Toxin/Non-Toxin）
        """
        import numpy as np

        # 提取 AAC + DPC 特征 (420维)
        features = self.extract_features([sequence])

        # 转换为 numpy 数组
        X = features.values

        # 预测毒性分数（概率）
        score = self.model.predict_proba(X)[0][1]  # 取 class 1 (Toxin) 的概率

        # 预测标签
        prediction = "Toxin" if score >= 0.38 else "Non-Toxin"

        return ToolResult(
            score=float(score),
            label=prediction,
            details={
                "length": len(sequence),
                "prediction": prediction,
                "threshold": 0.38,
            },
        )


# 创建 FastAPI 应用
app = create_app(ToxinPred3Service)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8003"))
    print(f"Starting ToxinPred3 service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)

