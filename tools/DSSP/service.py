"""
service.py
==========
DSSP 二级结构分析微服务 — PDB 结构 → beta-sheet 风险评分。

此服务是 PDB Service 模板的一个具体实现。
输入 PDB 结构文本，使用 mkdssp / DSSP 计算逐残基二级结构和 relative ASA，
返回 beta-sheet 相关风险评分、pass/reject 标签和逐残基明细。

核心工具: mkdssp
Python wrapper: Biopython Bio.PDB.DSSP

使用方式：
    cd tools/DSSP
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
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from Bio.PDB import MMCIFParser, PDBParser
from Bio.PDB.DSSP import DSSP

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


BETA_CODES = {"E", "B"}

SS_NAME_MAP: dict[str, str] = {
    "H": "alpha_helix",
    "B": "isolated_beta_bridge",
    "E": "beta_strand",
    "G": "3_10_helix",
    "I": "pi_helix",
    "T": "turn",
    "S": "bend",
    "-": "none",
    " ": "none",
}

DEFAULT_BETA_FRACTION_THRESHOLD = 0.30
DEFAULT_CONSECUTIVE_BETA_THRESHOLD = 3


class DSSPService(PdbScoringService):
    """DSSP 二级结构分析服务。

    使用 mkdssp 对 PDB/mmCIF 结构进行逐残基二级结构标注。
    输出 beta-sheet / beta-bridge residue 比例，并根据阈值给出 pass/reject。
    """

    tool_name = "dssp"
    version = "1.0.0"
    description = (
        "DSSP 二级结构分析 — 使用 mkdssp 标注逐残基 secondary structure "
        "和 relative ASA，并进行 beta-sheet 风险过滤。PDB 结构 → 评分。"
    )
    recommended_batch_size = 20

    def __init__(self):
        super().__init__()
        self._ready_message: str = "Not checked yet"

    # ── 模型加载 / 环境检查 ─────────────────────────────────────

    async def load_model(self) -> None:
        """验证 mkdssp 可用。DSSP 是纯算法服务，不需要 ML 模型。"""
        print(f"[{self.tool_name}] Checking mkdssp …")

        mkdssp_path = shutil.which("mkdssp")
        if not mkdssp_path:
            self._ready_message = (
                "mkdssp not found. Please install DSSP/mkdssp in the runtime environment."
            )
            print(f"[{self.tool_name}] {self._ready_message}")
            raise RuntimeError(self._ready_message)

        self.model = "mkdssp"
        self._ready_message = "mkdssp ready"
        self._system_info = detect_system()
        self._model_status = {
            "status": "ready",
            "engine": "mkdssp",
            "backend": "cpu",
            "executable": mkdssp_path,
            "requires_model_file": False,
        }

        print(f"[{self.tool_name}] {self._ready_message}: {mkdssp_path}")

    # ── 辅助函数 ───────────────────────────────────────────────

    @staticmethod
    def _looks_like_mmcif(pdb_content: str) -> bool:
        """粗略判断输入是否为 mmCIF。"""
        stripped = pdb_content.lstrip()
        return stripped.startswith("data_") or "_atom_site." in stripped[:5000]

    @staticmethod
    def _has_consecutive_beta(
        residues: list[dict[str, Any]],
        min_len: int = DEFAULT_CONSECUTIVE_BETA_THRESHOLD,
    ) -> bool:
        """判断是否存在连续 beta residue。"""
        count = 0

        for residue in residues:
            if residue["is_beta"]:
                count += 1
                if count >= min_len:
                    return True
            else:
                count = 0

        return False

    @staticmethod
    def _filter_by_sequence(
        residues: list[dict[str, Any]],
        sequence: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """在 DSSP 残基列表中定位功能肽序列。

        如果 sequence 提供，则在每条 chain 的单字母序列中搜索。
        返回第一个匹配片段。
        """
        target = sequence.strip().upper().replace(" ", "").replace("\n", "")
        if not target:
            return residues, None

        chains: dict[str, list[dict[str, Any]]] = {}
        for residue in residues:
            chains.setdefault(residue["chain"], []).append(residue)

        for chain, chain_residues in chains.items():
            chain_seq = "".join(r["amino_acid"].upper() for r in chain_residues)
            pos = chain_seq.find(target)

            if pos != -1:
                matched = chain_residues[pos : pos + len(target)]
                return matched, None

        available = {
            chain: "".join(r["amino_acid"].upper() for r in chain_residues)
            for chain, chain_residues in chains.items()
        }

        return [], (
            f"Sequence '{target}' not found in selected PDB residues. "
            f"Available chain sequences: {available}"
        )

    @staticmethod
    def _summarize_beta_risk(
        residues: list[dict[str, Any]],
        beta_fraction_threshold: float = DEFAULT_BETA_FRACTION_THRESHOLD,
        consecutive_beta_threshold: int = DEFAULT_CONSECUTIVE_BETA_THRESHOLD,
    ) -> dict[str, Any]:
        """根据 beta_fraction 和连续 beta residue 给出风险判断。"""
        residue_count = len(residues)
        beta_count = sum(r["is_beta"] for r in residues)
        beta_fraction = beta_count / residue_count if residue_count else 0.0

        has_consecutive_beta = DSSPService._has_consecutive_beta(
            residues,
            min_len=consecutive_beta_threshold,
        )

        if beta_fraction >= beta_fraction_threshold or has_consecutive_beta:
            label = "reject"
            reason = (
                f"High beta-sheet risk: beta_fraction >= {beta_fraction_threshold} "
                f"or at least {consecutive_beta_threshold} consecutive beta residues."
            )
        else:
            label = "pass"
            reason = "Beta-sheet risk is below the current filtering threshold."

        # PdbScoreResult 的 score 语义是 0-1，1 越好。
        # 这里将 beta risk 转为 safety score。
        beta_risk = beta_fraction + (0.30 if has_consecutive_beta else 0.0)
        beta_risk = min(1.0, beta_risk)
        safety_score = round(max(0.0, 1.0 - beta_risk), 4)

        return {
            "score": safety_score,
            "label": label,
            "reason": reason,
            "residue_count": residue_count,
            "beta_count": beta_count,
            "beta_fraction": beta_fraction,
            "has_consecutive_beta": has_consecutive_beta,
            "beta_fraction_threshold": beta_fraction_threshold,
            "consecutive_beta_threshold": consecutive_beta_threshold,
        }

    # ── PDB 评分 ──────────────────────────────────────────────

    async def score_pdb(
        self,
        pdb_content: str,
        sequence: str | None = None,
        chain_id: str | None = None,
    ) -> PdbScoreResult:
        """对 PDB/mmCIF 结构运行 DSSP，并计算 beta-sheet 风险。

        Args:
            pdb_content: PDB 或 mmCIF 格式结构文本
            sequence: 可选功能肽序列。如果提供，则只对匹配到的肽区域统计 beta risk。
            chain_id: 可选目标链 ID。如不提供，则分析所有 chain。

        Returns:
            PdbScoreResult:
                score = beta-sheet safety score，1 表示低 beta 风险
                label = "pass" / "reject" / "error"
                details = residue-level DSSP annotation + beta risk summary
        """
        is_mmcif = self._looks_like_mmcif(pdb_content)
        suffix = ".cif" if is_mmcif else ".pdb"
        file_type = "MMCIF" if is_mmcif else "PDB"

        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as f:
            f.write(pdb_content)
            tmp_path = f.name

        try:
            if is_mmcif:
                parser = MMCIFParser(QUIET=True)
            else:
                parser = PDBParser(QUIET=True)

            structure = parser.get_structure("dssp", tmp_path)
            model = structure[0]

            dssp = DSSP(
                model,
                tmp_path,
                dssp="mkdssp",
                file_type=file_type,
            )

            residues: list[dict[str, Any]] = []

            for key in dssp.keys():
                chain, residue_id = key
                dssp_tuple = dssp[key]

                residue_number = residue_id[1]
                insertion_code = residue_id[2].strip() if len(residue_id) > 2 else ""

                amino_acid = str(dssp_tuple[1]).upper()
                ss_code = dssp_tuple[2] if dssp_tuple[2] != " " else "-"
                relative_asa = float(dssp_tuple[3])

                if chain_id is not None and chain != chain_id:
                    continue

                residues.append(
                    {
                        "chain": chain,
                        "residue_number": residue_number,
                        "insertion_code": insertion_code,
                        "amino_acid": amino_acid,
                        "secondary_structure": ss_code,
                        "secondary_structure_name": SS_NAME_MAP.get(ss_code, "unknown"),
                        "relative_ASA": relative_asa,
                        "is_beta": ss_code in BETA_CODES,
                    }
                )

            if not residues:
                return PdbScoreResult(
                    score=0.0,
                    label="no_residues_found",
                    details={
                        "reason": "No residues matched the selected chain_id.",
                        "chain_id": chain_id,
                        "sequence": sequence,
                        "residues": [],
                    },
                )

            selected_residues = residues
            sequence_error: str | None = None

            if sequence:
                selected_residues, sequence_error = self._filter_by_sequence(
                    residues,
                    sequence,
                )

                if sequence_error:
                    return PdbScoreResult(
                        score=0.0,
                        label="sequence_not_found",
                        details={
                            "error": sequence_error,
                            "chain_id": chain_id,
                            "sequence": sequence,
                            "all_residues": residues,
                        },
                    )

            summary = self._summarize_beta_risk(selected_residues)

            details: dict[str, Any] = {
                "reason": summary["reason"],
                "chain_id": chain_id,
                "sequence": sequence,
                "scope": "matched_sequence" if sequence else "selected_chain_or_all",
                "residue_count": summary["residue_count"],
                "beta_count": summary["beta_count"],
                "beta_fraction": summary["beta_fraction"],
                "has_consecutive_beta": summary["has_consecutive_beta"],
                "beta_fraction_threshold": summary["beta_fraction_threshold"],
                "consecutive_beta_threshold": summary["consecutive_beta_threshold"],
                "selected_residues": selected_residues,
                "all_residues": residues,
            }

            return PdbScoreResult(
                score=summary["score"],
                label=summary["label"],
                details=details,
            )

        finally:
            os.unlink(tmp_path)

    # ── 批量预测 ──────────────────────────────────────────────

    async def predict_batch(
        self, request: PdbBatchScoreRequest
    ) -> PdbBatchScoreResponse:
        """批量 PDB 评分 — 使用模板的并发控制。"""
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

    PORT = int(os.environ.get("PORT", "8103"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    app = create_app(DSSPService)
    print(f"[dssp] Starting on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)