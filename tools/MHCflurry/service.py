"""
service.py
==========
MHCflurry 微服务入口。

将现有的 MHCflurry MHC I类肽结合亲和力预测工具封装为标准的微服务接口。

使用方式：
    cd tools/MHCflurry
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
from tools.template.fasta_service import FastaToolService, create_app, ToolResult


class MHCflurryService(FastaToolService):
    """
    MHCflurry MHC I类肽结合亲和力预测服务。

    使用深度学习模型预测肽与MHC分子的结合强度。
    """

    tool_name = "mhcflurry"
    version = "2.0.0"
    description = "MHC I类肽结合亲和力预测工具（MHCflurry）- 深度学习模型"
    recommended_batch_size = 50

    # 默认等位基因（如果用户没有指定）
    DEFAULT_ALLELE = "HLA-A*02:01"

    async def load_model(self):
        """
        加载 MHCflurry 预测模型。
        """
        # Python 3.13+ 兼容性补丁
        if sys.version_info >= (3, 13):
            import shlex

            class FakePipes:
                @staticmethod
                def quote(s):
                    return shlex.quote(s)

            sys.modules["pipes"] = FakePipes()

        from mhcflurry import Class1AffinityPredictor

        self.predictor = Class1AffinityPredictor.load()
        print(f"[{self.tool_name}] MHCflurry model loaded, ready to predict")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """
        预测单条序列的MHC结合亲和力。

        Args:
            sequence: 氨基酸序列（如 "SIINFEKL"）

        Returns:
            ToolResult: 包含 affinity_nM（结合亲和力）和 label（强/弱/非结合剂）
        """
        # 预测亲和力（使用默认等位基因）
        affinity = self.predictor.predict(
            peptides=[sequence], alleles=[self.DEFAULT_ALLELE]
        )[0]

        # 转换亲和力为分数（0-1，越低越强）
        # IC50 <= 50nM = 强结合剂, 50-500nM = 弱结合剂, >500nM = 非结合剂
        if affinity <= 50:
            label = "Strong Binder"
            score = 1.0 - (affinity / 50) * 0.5  # 0.75-1.0
        elif affinity <= 500:
            label = "Weak Binder"
            score = 0.5 - ((affinity - 50) / 450) * 0.5  # 0.25-0.5
        else:
            label = "Non-Binder"
            score = 0.25 - (min(affinity, 5000) / 5000) * 0.25  # 0.0-0.25

        return ToolResult(
            score=float(score),
            label=label,
            details={
                "affinity_nM": round(float(affinity), 2),
                "allele": self.DEFAULT_ALLELE,
                "peptide_length": len(sequence),
            },
        )


# 创建 FastAPI 应用
app = create_app(MHCflurryService)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8005"))
    print(f"Starting MHCflurry service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
