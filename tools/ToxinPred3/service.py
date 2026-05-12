"""
service.py
==========
ToxinPred3 微服务入口 — 肽毒性预测。

原仓库: https://github.com/raghavagps/toxinpred3
论文: Rathore AS, et al. (2024) "ToxinPred3.0". *Computers in Biology and Medicine*.

基于 Extra Trees 分类器 + AAC(20维)/DPC(400维) 特征。
使用 Model 1 (ML only)，不依赖 MERCI/Perl 杂交路径。

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
from tools.template.fasta_service import FastaToolService, create_app, ToolResult
from tools.utils import detect_system


class ToxinPred3Service(FastaToolService):
    """ToxinPred3 肽毒性预测服务。

    基于 Extra Trees 分类器 + AAC(20维)/DPC(400维) 特征。
    使用 Model 1 (纯 ML)，不依赖 MERCI 杂交路径（该路径在已知毒素上产生假阴性）。

    原仓库: https://github.com/raghavagps/toxinpred3
    """

    tool_name = "toxinpred3"
    version = "2.0.0"
    description = "肽毒性预测工具（ToxinPred3）- Extra Trees 分类器 + AAC/DPC 特征"
    recommended_batch_size = 50

    async def load_model(self):
        """加载 ToxinPred3 ExtraTrees 模型和特征提取器。

        直接 joblib.load 加载 sklearn 模型（绕过 toxinpred3 CLI 的 pandas 兼容性 bug）。
        特征提取使用本地 AAC + DPC 实现（与原始包对齐，420 维）。
        """
        import toxinpred3
        import joblib
        import sklearn
        import os

        self._sklearn_ver = sklearn.__version__

        tp3_path = list(toxinpred3.__path__)[0]
        model_path = os.path.join(tp3_path, "model", "toxinpred3.0_model.pkl")
        self.model = joblib.load(model_path)

        from toxinpred_features import extract_features
        self.extract_features = extract_features

        self._system_info = detect_system()
        self._model_status = {
            "status": "ready",
            "model": "sklearn ExtraTreesClassifier (AAC+DPC, 420-dim)",
            "model_path": model_path,
            "backend": "cpu",
        }

        print(f"[{self.tool_name}] ExtraTreesClassifier loaded | sklearn={self._sklearn_ver} | path={model_path}")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的毒性。

        Args:
            sequence: 氨基酸序列（如 "KWKLFKKIGAVLKVL"）

        Returns:
            ToolResult: score=毒性概率(0-1), label="Toxin"/"Non-Toxin"
        """
        import warnings

        features = self.extract_features([sequence])

        # 抑制 sklearn 特征名称警告（列名对齐已验证）
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="X does not have valid feature names")
            score = float(self.model.predict_proba(features)[0][1])

        prediction = "Toxin" if score >= 0.38 else "Non-Toxin"

        return ToolResult(
            score=score,
            label=prediction,
            details={
                "length": len(sequence),
                "threshold": 0.38,
                "model": "ExtraTreesClassifier (Model 1: AAC+DPC)",
                "sklearn_version": self._sklearn_ver,
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

