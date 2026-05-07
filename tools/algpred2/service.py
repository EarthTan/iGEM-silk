"""
service.py - AlgPred2 微服务入口

过敏原性风险预测工具 - 基于随机森林模型的蛋白过敏原性预测

使用方式：
    cd tools/AlgPred2
    source .venv/bin/activate
    python service.py
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# 将项目根目录添加到路径（用于导入 services.template）
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.fasta_service import BioToolService, create_app, ToolResult


class AlgPred2Service(BioToolService):
    """AlgPred2 过敏原性风险预测服务"""

    tool_name = "algpred2"  # 必须与 registry.py 中的 name 一致
    version = "1.4"  # 版本号
    description = "过敏原性风险预测工具 - 基于随机森林模型的蛋白过敏原性预测"
    recommended_batch_size = 50  # 推荐批量大小

    def __init__(self):
        super().__init__()
        self.model = None
        self._model_loaded = False

    async def load_model(self):
        """加载 AlgPred2 模型"""
        import algpred2 as ap2
        import joblib

        # 获取 algpred2 包路径
        pkg_dir = Path(ap2.__path__[0])
        model_path = pkg_dir / "model" / "rf_model"

        # 检查模型文件
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        self.model = joblib.load(str(model_path))
        print(f"[algpred2] Model loaded from: {model_path}")
        self._model_loaded = True

    def _compute_aac(self, sequence: str) -> list[float]:
        """计算氨基酸组成 (Amino Acid Composition)

        对应 algpred2.py 中的 aac_comp() 函数
        标准氨基酸顺序: ACDEFGHIKLMNPQRSTVWY (19个，不含Y的计数在最后)
        """
        std = list("ACDEFGHIKLMNPQRSTVWY")
        seq = sequence.strip()

        aac_values = []
        for aa in std:
            count = sum(1 for s in seq if s == aa)
            composition = (count / len(seq)) * 100 if len(seq) > 0 else 0
            aac_values.append(composition)

        return aac_values

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的过敏原性风险

        Args:
            sequence: 氨基酸序列字符串

        Returns:
            ToolResult: 包含 ML_Score (0-1) 和 Prediction (Allergen/Non-Allergen)
        """
        if not self._model_loaded:
            await self.load_model()

        # 计算 AAC 特征
        aac_values = self._compute_aac(sequence)

        # 转换为 2D numpy 数组 (sklearn 需要)
        import numpy as np

        X_test = np.array(aac_values).reshape(1, -1)

        # 预测
        y_p_score = self.model.predict_proba(X_test)

        # 取第二个类 (Allergen) 的概率
        ml_score = float(y_p_score[0][1])
        threshold = 0.3
        prediction = "Allergen" if ml_score >= threshold else "Non-Allergen"

        return ToolResult(
            score=ml_score,
            label=prediction,
            details={
                "sequence_length": len(sequence),
                "model": "Random Forest",
                "threshold": threshold,
            },
        )


# 创建 FastAPI 应用
app = create_app(AlgPred2Service)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8008"))
    print(f"Starting AlgPred2 service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)

