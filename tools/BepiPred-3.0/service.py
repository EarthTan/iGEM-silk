"""
service.py - BepiPred-3.0 微服务入口

线性 B 细胞表位预测工具 - 基于 ESM-2 蛋白质语言模型

原仓库: https://github.com/UberClifford/BepiPred-3.0
PyPI:   bp3==0.0.12.7

使用方式：
    cd tools/BepiPred-3.0
    source .venv/bin/activate
    python service.py

注意：BepiPred-3.0 需要 ESM-2 模型编码，首次运行会下载模型（约 2.5GB）
"""

from __future__ import annotations

import sys
import os
import tempfile
from pathlib import Path

# 向上跳 2 级目录，作为根路径
root_path = Path(__file__).parents[2]
sys.path.insert(0, str(root_path))

from tools.template.fasta_service import (
    FastaToolService, create_app, ToolResult,
    BatchPredictRequest, BatchPredictResponse, PredictRequest,
)
from tools.utils import detect_gpu


class BepiPred3Service(FastaToolService):
    """BepiPred-3.0 B 细胞表位预测服务"""

    tool_name = "bepipred3"
    version = "0.0.12.7"
    description = "B 细胞表位预测工具 - 基于 ESM-2 蛋白质语言模型的线性表位预测"
    recommended_batch_size = 10

    def __init__(self):
        super().__init__()
        self.antigens_class = None
        self.predictor_class = None
        self.esm_dir = None
        self._model_loaded = False
        self.gpu_info: dict = {}

    async def load_model(self):
        """加载 BepiPred-3.0 模型和 ESM-2 编码器"""
        from bp3 import bepipred3

        self.antigens_class = bepipred3.Antigens
        self.predictor_class = bepipred3.BP3EnsemblePredict

        self.esm_dir = Path(__file__).parent / "esm_cache"
        self.esm_dir.mkdir(exist_ok=True)

        self.gpu_info = detect_gpu()
        print(f"[bepipred3] {self.gpu_info['message']}")
        print(f"[bepipred3] BepiPred-3.0 loaded, ESM cache: {self.esm_dir}")
        print(f"[bepipred3] Note: First run will download ESM-2 model (~2.5GB)")
        self._model_loaded = True

    async def predict_impl(self, sequence: str) -> ToolResult:
        """预测单条序列的 B 细胞表位

        Args:
            sequence: 氨基酸序列字符串

        Returns:
            ToolResult: 包含 epitope_score (0-1), predicted_epitope (bool), per_residue_scores
        """
        if not self._model_loaded:
            await self.load_model()

        # 创建临时 FASTA 文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as f:
            f.write(f">PEP\n{sequence}\n")
            fasta_path = Path(f.name)

        # 创建临时输出目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)

            try:
                # ESM-2 编码
                antigens = self.antigens_class(
                    fasta_file=fasta_path,
                    esm_encoding_dir=self.esm_dir,
                    add_seq_len=False,
                )

                # 预测
                predictor = self.predictor_class(
                    antigens, rolling_window_size=7, top_pred_pct=0.2
                )
                predictor.run_bp3_ensemble()

                # 计算平均表位分数
                # antigens.ensemble_probs: list of list of tensors (5 models x residues)
                # 每个 ensemble_prob[i] 是第 i 个模型的概率 tensor
                all_probs = []
                for ensemble_prob in antigens.ensemble_probs:
                    # ensemble_prob 是 5 个模型的概率 tensor 列表，每个 tensor 形状 [num_residues]
                    for prob_tensor in ensemble_prob:
                        # 转换为 Python 列表
                        prob_list = prob_tensor.detach().cpu().flatten().tolist()
                        all_probs.extend(prob_list)

                if len(all_probs) == 0:
                    raise ValueError("No predictions generated")

                # 取整个肽的平均表位分数（所有模型所有残差的平均值）
                epitope_score = float(sum(all_probs) / len(all_probs))

                # 预测标签阈值
                threshold = 0.1512

                # 计算线性表位分数（滚动平均）- 使用 numpy
                rolling_scores = self._compute_rolling_mean(all_probs, window=7)

                # 预测标签：average score >= 0.1512 则为表位
                predicted_epitope = bool(epitope_score >= threshold)

                # 计算最大表位分数
                max_score = float(max(all_probs))
                max_rolling_score = (
                    float(max(rolling_scores))
                    if rolling_scores and len(rolling_scores) > 0
                    else max_score
                )

                return ToolResult(
                    score=float(epitope_score),
                    label="Epitope" if predicted_epitope else "Non-epitope",
                    details={
                        "sequence_length": int(len(sequence)),
                        "average_epitope_score": round(float(epitope_score), 4),
                        "max_epitope_score": round(float(max_score), 4),
                        "max_linear_epitope_score": round(float(max_rolling_score), 4),
                        "threshold": float(threshold),
                        "num_residues_predicted": int(len(all_probs)),
                        "model": str("ESM-2 + DenseNet Ensemble"),
                        "gpu_backend": self.gpu_info.get("backend", "unknown"),
                    },
                )

            finally:
                # 清理临时文件
                if fasta_path.exists():
                    os.remove(fasta_path)

    async def predict_batch(self, request: BatchPredictRequest) -> BatchPredictResponse:
        """批量预测 — 将所有序列写入一个 FASTA，一次编码一次预测。

        覆盖基类的逐条 predict_impl 调用方式，避免 N 次 temp 文件 I/O
        和 N 次 ESM-2 模型加载。
        """
        if not self._loaded:
            async with self._lock:
                if not self._loaded:
                    await self.load_model()
                    self._loaded = True

        if not request.sequences:
            return BatchPredictResponse(success=True, results=[], total=0, error=None)

        # 写入一个临时 FASTA（全部序列）
        with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as f:
            for item in request.sequences:
                pid = item.peptide_id or "unknown"
                f.write(f">{pid}\n{item.sequence}\n")
            fasta_path = Path(f.name)

        try:
            antigens = self.antigens_class(
                fasta_file=fasta_path,
                esm_encoding_dir=self.esm_dir,
                add_seq_len=False,
            )
            predictor = self.predictor_class(
                antigens, rolling_window_size=7, top_pred_pct=0.2
            )
            predictor.run_bp3_ensemble()

            # 按序列提取结果 — ensemble_probs[i] shape: [num_models, num_residues]
            results: list[ToolResult] = []
            threshold = 0.1512

            for i, item in enumerate(request.sequences):
                pid = item.peptide_id or "unknown"
                seq = item.sequence

                all_probs = []
                ensemble_prob = antigens.ensemble_probs[i]
                for prob_tensor in ensemble_prob:
                    prob_list = prob_tensor.detach().cpu().flatten().tolist()
                    all_probs.extend(prob_list)

                if not all_probs:
                    continue

                epitope_score = sum(all_probs) / len(all_probs)
                predicted_epitope = epitope_score >= threshold
                rolling_scores = self._compute_rolling_mean(all_probs, window=7)
                max_score = max(all_probs)
                max_rolling = max(rolling_scores) if rolling_scores else max_score

                result = ToolResult(
                    score=float(epitope_score),
                    label="Epitope" if predicted_epitope else "Non-epitope",
                    details={
                        "sequence_length": len(seq),
                        "average_epitope_score": round(epitope_score, 4),
                        "max_epitope_score": round(max_score, 4),
                        "max_linear_epitope_score": round(max_rolling, 4),
                        "threshold": threshold,
                        "num_residues_predicted": len(all_probs),
                        "model": "ESM-2 + DenseNet Ensemble",
                        "gpu_backend": self.gpu_info.get("backend", "unknown"),
                    },
                )
                result.peptide_id = pid
                result.sequence = seq
                results.append(result)

            return BatchPredictResponse(
                success=True,
                results=results,
                total=len(results),
                error=None,
            )

        finally:
            if fasta_path.exists():
                os.remove(fasta_path)

    def _compute_rolling_mean(self, values, window=7):
        """计算滚动平均"""
        import numpy as np

        values_list = list(values)
        if len(values_list) < window:
            return values_list
        result = np.convolve(values_list, np.ones(window), "same") / window
        return result.tolist()


# 创建 FastAPI 应用
app = create_app(BepiPred3Service)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8002"))
    print(f"Starting BepiPred-3.0 service on port {port}...")
    print(f"Note: First run will download ESM-2 model (~2.5GB)")
    uvicorn.run(app, host="0.0.0.0", port=port)
