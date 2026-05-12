"""
SoDoPE 集成适配层 — Solubility-Weighted Index (SWI) 蛋白质溶解度预测。

将原作 swi.py / functions.py 的 SWI 算法封装为可调用类，
供 service.py 的 FastaToolService 使用。

核心算法：
    SWI = mean(per-residue solubility weights)
    Prob = sigmoid(A * SWI + B)

论文引用:
    Bhandari, B.K., Gardner, P.P. and Lim, C.S. (2020).
    Solubility-Weighted Index: fast and accurate prediction of protein solubility.
    Bioinformatics, DOI: 10.1093/bioinformatics/btaa578
"""

from __future__ import annotations

import re

import numpy as np

# ── Solubility-Weighted Index 权重（20 种标准氨基酸）───────────
# 来源: Bhandari et al. (2020), functions.py / swi.py
# 数值通过 eSOL 数据集对数回归优化得到，值越大 → 溶解度越高
SWI_WEIGHTS = {
    "A": 0.8356471476582918,
    "C": 0.5208088354857734,
    "E": 0.9876987431418378,
    "D": 0.9079044671339564,
    "G": 0.7997168496420723,
    "F": 0.5849790194237692,
    "I": 0.6784124413866582,
    "H": 0.8947913996466419,
    "K": 0.9267104557513497,
    "M": 0.6296623675420369,
    "L": 0.6554221515081433,
    "N": 0.8597433107431216,
    "Q": 0.789434648348208,
    "P": 0.8235328714705341,
    "S": 0.7440908318492778,
    "R": 0.7712466317693457,
    "T": 0.8096922697856334,
    "W": 0.6374678690957594,
    "V": 0.7357837119163659,
    "Y": 0.6112801822947587,
}

# ── 逻辑回归常数（eSOL 数据集拟合）─────────────────────────────
# prob = 1 / (1 + exp(-(A * SWI + B)))
A = 81.0581
B = -62.7775

# ── 序列验证 ───────────────────────────────────────────────────
_VALID_AA = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$")


class SoDoPEIntegration:
    """
    SoDoPE (Solubility-Weighted Index) 蛋白质溶解度预测器。

    只需氨基酸序列，不需要模型文件、GPU 或外部依赖。
    预测基于原作论文的预计算氨基酸溶解度权重表。
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose

    def predict_single(self, sequence: str) -> dict:
        """
        预测单条蛋白序列的溶解度。

        Args:
            sequence: 氨基酸序列（大小写均可）

        Returns:
            dict: {"swi": ..., "probability": ..., "sequence_length": ..., "label": ...}

        Raises:
            ValueError: 序列包含非标准氨基酸字符或为空
        """
        seq = sequence.strip().upper()

        if not seq:
            raise ValueError("序列为空")

        if not _VALID_AA.match(seq):
            invalid_chars = set(seq) - set(SWI_WEIGHTS.keys())
            raise ValueError(
                f"序列包含非标准氨基酸字符: {invalid_chars}. "
                f"仅支持 20 种标准氨基酸 (ACDEFGHIKLMNPQRSTVWY)"
            )

        swi = float(np.mean([SWI_WEIGHTS[aa] for aa in seq]))
        prob = float(1.0 / (1.0 + np.exp(-(A * swi + B))))
        # 截断到 [0, 1] 避免数值精度溢出
        prob = max(0.0, min(1.0, prob))

        return {
            "swi": swi,
            "probability": prob,
            "sequence_length": len(seq),
            "label": "Soluble" if prob >= 0.5 else "Insoluble",
        }

    def predict_batch(self, sequences: list[str]) -> list[dict]:
        """
        预测多条序列的溶解度。

        Args:
            sequences: 氨基酸序列列表

        Returns:
            list[dict]: 每条序列的预测结果
        """
        return [self.predict_single(seq) for seq in sequences]
