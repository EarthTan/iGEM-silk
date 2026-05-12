"""
service.py
==========
pLM4CPPs 微服务入口 — 细胞穿膜肽 (CPP) 预测。

原仓库: https://github.com/drkumarnandan/pLM4CPPs
论文: Kumar et al. (2025) "pLM4CPPs: Protein Language Model-Based Predictor
      for Cell Penetrating Peptides". *J. Chem. Inf. Model.*
      DOI: 10.1021/acs.jcim.4c01338

基于 ESM-2 (t6 8M) 蛋白质语言模型嵌入 + 1D-CNN 分类器预测肽的细胞穿膜能力。
在流水线中作为 score 型服务，权重 0.10。

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
from tools.template.fasta_service import (
    FastaToolService, create_app, ToolResult,
    BatchPredictRequest, BatchPredictResponse,
)
from tools.utils import detect_gpu, detect_system


class pLM4CPPsService(FastaToolService):
    """pLM4CPPs 细胞穿膜肽预测服务。

    使用 ESM-2 蛋白质语言模型嵌入 + 1D-CNN 分类器预测肽的穿膜能力。
    原仓库: https://github.com/drkumarnandan/pLM4CPPs
    论文: Kumar et al. (2025) J. Chem. Inf. Model.
    """

    tool_name = "plm4cpps"
    version = "1.0.0"
    description = "细胞穿膜肽预测工具（pLM4CPPs）- ESM2 + 1D-CNN"
    recommended_batch_size = 20  # ESM2 模型较大，限制并发

    # 优化后的阈值 (MCC-optimized on KELM external dataset)
    THRESHOLD = 0.15

    async def load_model(self):
        """加载 pLM4CPPs 的 ESM-2 模型和 CNN 分类器。"""
        from predict import load_cpp_model, load_esm2_model, generate_esm2_embeddings
        from sklearn.preprocessing import MinMaxScaler
        import numpy as np

        self.gpu_info = detect_gpu()
        self._system_info = detect_system()
        print(f"[{self.tool_name}] {self.gpu_info['message']}")

        # 将 ESM-2 模型缓存指向共享目录 (tools/models/fair-esm/)
        os.environ["TORCH_HOME"] = str(
            Path(__file__).parent.parent / "models" / "fair-esm"
        )

        # 加载 ESM-2 模型 (首次启动自动下载 ~8 MB)
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

        # 加载预拟合的 MinMaxScaler 参数（从训练数据生成）
        scaler_path = model_path.parent / "scaler_params.npz"
        if scaler_path.exists():
            params = np.load(scaler_path)
            self._scaler = MinMaxScaler()
            self._scaler.data_min_ = params["data_min"]
            self._scaler.data_max_ = params["data_max"]
            self._scaler.feature_range = tuple(params["feature_range"])
            self._scaler.n_features_in_ = len(params["data_min"])
            # 手动计算 scale_ 和 min_ 派生属性（sklearn transform 需要）
            data_range = self._scaler.data_max_ - self._scaler.data_min_
            data_range[data_range == 0] = 1e-12  # 避免零除
            fmin, fmax = self._scaler.feature_range
            self._scaler.scale_ = (fmax - fmin) / data_range
            self._scaler.min_ = fmin - self._scaler.data_min_ * self._scaler.scale_
        else:
            raise FileNotFoundError(
                f"Scaler params not found at {scaler_path}. "
                "Run scaler generation script first."
            )

        # 保存 generate_esm2_embeddings 供 predict_impl 使用
        self._generate_embeddings = generate_esm2_embeddings

        esm_checkpoint = (
            Path(__file__).parent.parent / "models" / "fair-esm"
            / "hub" / "checkpoints" / "esm2_t6_8M_UR50D.pt"
        )
        self._model_status = {
            "status": "ready",
            "components": {
                "esm2": {
                    "model": "esm2_t6_8M_UR50D",
                    "source": "fair-esm (torch.hub, Facebook CDN)",
                    "cache_path": str(esm_checkpoint),
                },
                "cnn": {"path": str(model_path)},
                "scaler": {"path": str(scaler_path)},
            },
            "backend": self.gpu_info["backend"],
        }

        print(
            f"[{self.tool_name}] ESM-2 + CNN model loaded | "
            f"scaler fitted on training data | "
            f"backend={self.gpu_info['backend']}"
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
                "gpu_backend": self.gpu_info.get("backend", "unknown"),
            },
        )

    async def predict_batch(self, request: BatchPredictRequest) -> BatchPredictResponse:
        """批量预测 — 一次 ESM-2 前向传播处理全部序列。

        覆盖基类逐条 predict_impl 方式，避免 N 次 ESM-2 编码开销。
        """
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        if not request.sequences:
            return BatchPredictResponse(success=True, results=[], total=0, error=None)

        peptides = [(item.peptide_id or "unknown", item.sequence) for item in request.sequences]

        # 一次生成全部 ESM-2 嵌入
        embeddings = self._generate_embeddings(
            peptides, model=self.esm_model, alphabet=self.alphabet
        )

        # 标准化
        X = self._scaler.transform(embeddings.values)
        X = X.reshape(X.shape[0], X.shape[1], 1)

        # 一次 CNN 批量推理
        probs = self.cnn_model.predict(X, verbose=0).flatten()

        results: list[ToolResult] = []
        for (pid, seq), prob in zip(peptides, probs):
            cpp_prob = float(prob)
            label = "CPP" if cpp_prob >= self.THRESHOLD else "non-CPP"
            result = ToolResult(
                score=cpp_prob,
                label=label,
                details={
                    "length": len(seq),
                    "prediction": label,
                    "threshold": self.THRESHOLD,
                    "model_type": "ESM2-320_CNN",
                    "gpu_backend": self.gpu_info.get("backend", "unknown"),
                },
            )
            result.peptide_id = pid
            result.sequence = seq
            results.append(result)

        return BatchPredictResponse(
            success=True, results=results, total=len(results), error=None
        )


# 创建 FastAPI 应用
app = create_app(pLM4CPPsService)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8006"))
    print(f"Starting pLM4CPPs service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
