"""
service.py
==========
GraphCPP 微服务入口 — 细胞穿膜肽 (CPP) 预测（图神经网络）。

原仓库: https://github.com/drkumarnandan/GraphCPP
论文: GraphCPP: graph neural network for cell-penetrating peptide prediction.

架构: 肽序列 → RDKit 分子图 → MolGraphConvFeaturizer (DeepChem)
      → GraphSAGE 卷积 (2层) + Topological Fingerprint (2048维)
      → Sigmoid 分类

在流水线中作为 score 型服务，权重 0.05（轻量版，低于 pLM4CPPs 的 0.10）。

使用方式：
    cd tools/GraphCPP
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
import warnings
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.fasta_service import (
    FastaToolService, create_app, ToolResult,
    BatchPredictRequest, BatchPredictResponse,
)
from tools.template.logger import get_logger
from tools.utils import detect_system


class GraphCPPService(FastaToolService):
    """GraphCPP 细胞穿膜肽预测服务（真实 GNN 模型）。

    使用 GraphSAGE + Topological Fingerprint 预测 CPP。
    原仓库: https://github.com/drkumarnandan/GraphCPP
    """

    tool_name = "graphcpp"
    version = "2.0.0"
    description = "细胞穿膜肽预测工具（GraphCPP）- GraphSAGE GNN + Morgan FP"
    recommended_batch_size = 20

    async def load_model(self):
        """加载 GraphCPP GNN 模型 (GraphSAGE + Topological Fingerprint)。

        模型: GraphSAGE 2-layer + TopologicalTorsion FP (2048维) + MLP
        Checkpoint: model/checkpoints/epoch=22-step=69.ckpt
        """
        import torch
        from graphcpp.model import GCN
        from config import BEST_PARAMETERS
        from graphcpp.dataset import featurize_fasta
        from graphcpp.fp_generators import fp_dict
        from rdkit import Chem

        self.torch = torch
        self.Chem = Chem
        self.featurize_fasta = featurize_fasta

        params = BEST_PARAMETERS.copy()

        self.device = torch.device(
            "cuda" if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available()
            else "cpu"
        )

        # 初始化 GCN 模型
        self.model = GCN(
            layers_pre_mp=params["layers_pre_mp"],
            mp_layers=params["mp_layers"],
            layers_post_mp=params["layers_post_mp"],
            hidden_channels=params["hidden_channels"],
            stage_type=params["stage_type"],
            layer_type=params["layer_type"],
            act=params["act"],
            conv_aggr=params["conv_aggr"],
            conv_dropout=params["conv_dropout"],
            has_bn=params["has_bn"],
            has_l2norm=params["has_l2norm"],
            layer_fingerprints=params["layer_fingerprints"],
            pooling=params["pooling"],
        )

        # 加载预训练权重
        ckpt_path = Path(__file__).parent / "model" / "checkpoints" / "epoch=22-step=69.ckpt"
        ckpt = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
        state_dict = {k.removeprefix("model."): v for k, v in ckpt["state_dict"].items()}
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()

        self._system_info = detect_system()

        # 指纹生成器 (topological torsion, 2048维)
        self.fp_gen = fp_dict[params["fingerprint_type"]]

        self.threshold = 0.5

        self._model_status = {
            "status": "ready",
            "model": "GraphSAGE GCN + TopologicalTorsion FP (2048-dim)",
            "checkpoint": str(ckpt_path),
            "device": str(self.device),
        }

        self.logger.info(
            "GraphSAGE GNN loaded | device=%s | threshold=%s | fingerprint=%s",
            self.device, self.threshold, params["fingerprint_type"],
        )

    def _predict_score(self, sequence: str) -> float:
        """对单条序列执行 GNN 推理，返回 CPP 概率。"""
        seq_upper = sequence.upper()

        # RDKit FASTA → Mol → SMILES
        mol = self.Chem.MolFromFASTA(seq_upper)
        if mol is None:
            return 0.0

        smiles = self.Chem.MolToSmiles(mol)

        # 分子图 featurize
        data = self.featurize_fasta(seq_upper)

        # 拓扑指纹 (2048维)
        mol_from_smiles = self.Chem.MolFromSmiles(smiles)
        data.fp = self.torch.tensor(
            [self.fp_gen.GetFingerprint(mol_from_smiles)], dtype=self.torch.float32
        )

        # 移动到设备
        data = data.to(self.device)

        with self.torch.no_grad():
            pred, _, _ = self.model(data)
            prob = self.torch.sigmoid(pred).item()

        return float(prob)

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的细胞穿透能力。

        Args:
            sequence: 氨基酸序列（如 "RKKRRQRRR"）

        Returns:
            ToolResult: score=CPP概率(0-1), label="CPP"/"non-CPP"
        """
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            prob = self._predict_score(sequence)

        label = "CPP" if prob >= self.threshold else "non-CPP"

        return ToolResult(
            score=prob,
            label=label,
            details={
                "length": len(sequence),
                "prediction": label,
                "threshold": self.threshold,
                "model_type": "GraphSAGE-GNN",
                "device": str(self.device),
            },
        )

    async def predict_batch(self, request: BatchPredictRequest) -> BatchPredictResponse:
        """批量预测。"""
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        if not request.sequences:
            return BatchPredictResponse(success=True, results=[], total=0, error=None)

        results: list[ToolResult] = []
        for item in request.sequences:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore")
                prob = self._predict_score(item.sequence)

            label = "CPP" if prob >= self.threshold else "non-CPP"
            result = ToolResult(
                score=prob,
                label=label,
                details={
                    "length": len(item.sequence),
                    "prediction": label,
                    "threshold": self.threshold,
                    "model_type": "GraphSAGE-GNN",
                    "device": str(self.device),
                },
            )
            result.peptide_id = item.peptide_id or "unknown"
            result.sequence = item.sequence
            results.append(result)

        return BatchPredictResponse(
            success=True, results=results, total=len(results), error=None
        )


app = create_app(GraphCPPService)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8009"))
    logger = get_logger("graphcpp")
    logger.info("Starting on port %d ...", port)
    uvicorn.run(app, host="0.0.0.0", port=port)
