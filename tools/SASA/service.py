"""
service.py
==========
SASA 溶剂可及表面积微服务 — PDB 结构 → 暴露度评分。

此服务是 PDB Service 模板的第一个具体实现。
输入 PDB 结构，使用 FreeSASA 计算逐残基溶剂可及表面积 (SASA)，
返回综合暴露度评分和逐残基明细。用于评估功能肽在融合蛋白中的表面暴露程度。

核心库: FreeSASA (https://freesasa.github.io/)
算法: Lee-Richards 滚动探针 (Shrake-Rupley)，默认探针半径 1.4 Å

使用方式：
    cd tools/SASA
    source .venv/bin/activate
    python service.py

API 端点：
    GET  /              → 服务信息
    GET  /health        → 健康检查
    GET  /info          → 工具信息
    POST /predict       → 单次 PDB 评分
    POST /predict/batch → 批量 PDB 评分
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.pdb_service import (
    PdbScoringService,
    create_app,
    PdbScoreResult,
    PdbScoreResponse,
    PdbBatchScoreResponse,
    PdbScoreRequest,
    PdbBatchScoreRequest,
)
from tools.utils import detect_system

# ═══════════════════════════════════════════════════════════════════════════════
# 标准氨基酸最大 SASA 参考值 (Å²)
# Tien et al. (2013) "Maximum allowed solvent accessibilities"
# 用于计算相对暴露度 (relative SASA = observed / max)
# ═══════════════════════════════════════════════════════════════════════════════

MAX_SASA: dict[str, float] = {
    "ALA": 121.0, "ARG": 265.0, "ASN": 187.0, "ASP": 187.0,
    "CYS": 148.0, "GLN": 214.0, "GLU": 214.0, "GLY": 97.0,
    "HIS": 216.0, "ILE": 195.0, "LEU": 191.0, "LYS": 230.0,
    "MET": 203.0, "PHE": 228.0, "PRO": 154.0, "SER": 143.0,
    "THR": 163.0, "TRP": 264.0, "TYR": 255.0, "VAL": 165.0,
}

# 标准三字母 → 单字母
AA3_TO_1: dict[str, str] = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}

DEFAULT_PROBE_RADIUS = 1.4
DEFAULT_EXPOSURE_THRESHOLD = 0.25  # relative SASA > 0.25 = exposed


class SASAService(PdbScoringService):
    """SASA 溶剂可及表面积分析服务。

    基于 FreeSASA Lee-Richards 算法，计算 PDB 结构中每个残基的
    溶剂可及表面积。返回综合暴露度评分 (0-1) 和逐残基明细。
    """

    tool_name = "sasa"
    version = "1.0.0"
    description = (
        "SASA 溶剂可及表面积分析 — FreeSASA Lee-Richards 算法, "
        "逐残基暴露度量化。PDB 结构 → 评分。"
    )
    recommended_batch_size = 50

    def __init__(self):
        super().__init__()
        self._ready_message: str = "Not checked yet"

    # ── 模型加载 ──────────────────────────────────────────────

    async def load_model(self) -> None:
        """验证 FreeSASA 库可用 (无需加载 ML 模型, 纯算法)。"""
        print(f"[{self.tool_name}] Checking FreeSASA …")
        try:
            import freesasa  # noqa: F401
            self._ready_message = "FreeSASA ready"
            self._system_info = detect_system()
            self._model_status = {
                "status": "ready",
                "engine": "FreeSASA (Lee-Richards)",
                "backend": "cpu",
            }
            print(f"[{self.tool_name}] {self._ready_message}")
        except ImportError:
            self._ready_message = (
                "FreeSASA not installed. Run: pip install freesasa"
            )
            print(f"[{self.tool_name}] {self._ready_message}")
            raise RuntimeError(self._ready_message)

    # ── 辅助: 在 PDB 残基列表中定位肽序列 ────────────────────

    @staticmethod
    def _locate_peptide_in_residues(
        residues: list[dict[str, Any]], peptide_seq: str
    ) -> tuple[list[int], str | None]:
        """在残基列表中匹配肽序列，返回匹配的 residue_id 列表。

        按序拼接 PDB 残基的单字母码，搜索 peptide_seq 的所有匹配位置。
        取第一个匹配，返回其 residue_id 列表。
        """
        seq_parts = [r["residue_code"] for r in residues]
        pdb_seq = "".join(seq_parts)

        start = 0
        while True:
            pos = pdb_seq.find(peptide_seq, start)
            if pos == -1:
                break
            # 提取匹配段的 residue_id
            matched_ids = [residues[i]["residue_id"] for i in range(pos, pos + len(peptide_seq))]
            return matched_ids, None
        return [], f"Peptide '{peptide_seq}' not found in PDB chain sequence '{pdb_seq}'"

    # ── PDB 评分 ──────────────────────────────────────────────

    async def score_pdb(
        self,
        pdb_content: str,
        sequence: str | None = None,
        chain_id: str | None = None,
    ) -> PdbScoreResult:
        """对 PDB 结构计算 SASA，聚焦功能肽区域暴露度。

        Args:
            pdb_content: PDB 格式结构文本
            sequence: 功能肽序列 (单字母, 如 "YWDHINNPEVYF")。
                      服务在 PDB 残基中自动定位，只对肽区域做统计。
                      不传则只返回逐残基原始数据，score=0。
            chain_id: 目标链 ID (默认 "A")

        Returns:
            PdbScoreResult: score = 功能肽区域平均相对 SASA,
                            details = 全结构逐残基 + 肽区域汇总
        """
        import freesasa
        from Bio.PDB.PDBParser import PDBParser

        chain = chain_id or "A"

        with tempfile.NamedTemporaryFile(
            suffix=".pdb", mode="w", delete=False
        ) as f:
            f.write(pdb_content)
            tmp_path = f.name

        try:
            # 1. FreeSASA 全结构计算
            fs_struct = freesasa.Structure(tmp_path)
            fs_result = freesasa.calc(fs_struct)

            # 2. Biopython 解析残基
            parser = PDBParser(QUIET=True)
            structure = parser.get_structure("sasa", tmp_path)
            model = structure[0]

            if chain not in model:
                available = list(model.child_dict.keys())
                chain = available[0] if available else chain

            chain_obj = model[chain]  # type: ignore[index]

            # 3. 逐残基 SASA 提取
            residues: list[dict[str, Any]] = []
            for res in chain_obj:
                if res.id[0] != " ":  # 跳过 HETATM / 水
                    continue

                rid = res.id[1]
                resname = res.resname.upper()

                sel = freesasa.selectArea(
                    [("residue", f"resi {rid} and chain {chain}")],
                    fs_struct, fs_result,
                )
                sasa_val = sel.get("residue", 0.0)

                max_ref = MAX_SASA.get(resname, 200.0)
                rel_sasa = min(sasa_val / max_ref, 1.0) if max_ref > 0 else 0.0

                residues.append({
                    "residue_id": rid,
                    "residue_name": resname,
                    "residue_code": AA3_TO_1.get(resname, "X"),
                    "sasa": round(sasa_val, 3),
                    "relative_sasa": round(rel_sasa, 3),
                    "is_exposed": rel_sasa > DEFAULT_EXPOSURE_THRESHOLD,
                })

            # 4. 定位功能肽
            peptide_ids: list[int] = []
            locate_error: str | None = None
            if sequence:
                peptide_ids, locate_error = self._locate_peptide_in_residues(
                    residues, sequence
                )
                if locate_error:
                    return PdbScoreResult(
                        score=0.0,
                        label="error",
                        details={
                            "error": locate_error,
                            "chain": chain,
                            "residues": residues,
                        },
                    )

            # 5. 筛选肽区域残基
            if peptide_ids:
                peptide_set = set(peptide_ids)
                peptide_residues = [r for r in residues if r["residue_id"] in peptide_set]
                n_pep = len(peptide_residues)
                pep_exposed = sum(1 for r in peptide_residues if r["is_exposed"])
                pep_mean_rel = (
                    sum(r["relative_sasa"] for r in peptide_residues) / n_pep
                    if n_pep else 0.0
                )
                pep_total_sasa = sum(r["sasa"] for r in peptide_residues)
                pep_exposure_ratio = pep_exposed / n_pep if n_pep else 0.0

                score = round(pep_mean_rel, 4)
                label = "exposed" if pep_exposure_ratio > 0.6 else ("partial" if pep_exposure_ratio > 0.3 else "buried")
            else:
                peptide_residues = []
                n_pep = 0
                pep_exposed = 0
                pep_mean_rel = 0.0
                pep_total_sasa = 0.0
                pep_exposure_ratio = 0.0
                score = 0.0
                label = "no_target"

            # 6. 组装响应
            details: dict[str, Any] = {
                "chain": chain,
                "probe_radius": DEFAULT_PROBE_RADIUS,
                "exposure_threshold": DEFAULT_EXPOSURE_THRESHOLD,
                "peptide": {
                    "sequence": sequence,
                    "num_residues": n_pep,
                    "num_exposed": pep_exposed,
                    "total_sasa": round(pep_total_sasa, 3),
                    "mean_relative_sasa": round(pep_mean_rel, 3),
                    "exposure_ratio": round(pep_exposure_ratio, 3),
                    "residue_ids": peptide_ids,
                    "residues": peptide_residues,
                },
                "all_residues": residues,
            }

            return PdbScoreResult(
                score=score,
                label=label,
                details=details,
            )

        finally:
            os.unlink(tmp_path)

    # ── 批量预测 ──────────────────────────────────────────────

    async def predict_batch(
        self, request: PdbBatchScoreRequest
    ) -> PdbBatchScoreResponse:
        """批量 PDB 评分 — 使用模板的并发控制 (semaphore=10)。"""
        return await super().predict_batch(request)

    # ── 单次预测 ──────────────────────────────────────────────

    async def predict_single(self, request: PdbScoreRequest) -> PdbScoreResponse:
        """单次 PDB 评分。"""
        if not self._loaded:
            return PdbScoreResponse(
                success=False,
                peptide_id=request.peptide_id,
                result=None,
                error=self._ready_message,
            )
        return await super().predict_single(request)


# ═══════════════════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("PORT", "8101"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    app = create_app(SASAService)
    print(f"[sasa] Starting on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
