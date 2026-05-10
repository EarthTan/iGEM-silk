# tools/template/__init__.py
# 工具服务模板包 —— 三类微服务模板

# ── fasta_service：序列 → 评分 ────────────────────────────
from .fasta_service import (
    BatchPredictRequest,
    BatchPredictResponse,
    FastaToolService,
    HealthResponse,
    InfoResponse,
    PredictRequest,
    PredictResponse,
    ToolResult,
    create_app as create_fasta_app,
)

# ── structure_service：序列 → 3D 结构 ──────────────────────
from .structure_service import (
    StructureService,
    StructureResult,
    StructurePredictResponse,
    StructureBatchPredictResponse,
    create_app as create_structure_app,
)

# ── pdb_service：PDB 结构 → 评分 ──────────────────────────
from .pdb_service import (
    PdbScoringService,
    PdbScoreRequest,
    PdbBatchScoreRequest,
    PdbScoreResult,
    PdbScoreResponse,
    PdbBatchScoreResponse,
    create_app as create_pdb_app,
)

__all__ = [
    # fasta_service
    "FastaToolService",
    "create_fasta_app",
    "ToolResult",
    "PredictRequest",
    "PredictResponse",
    "BatchPredictRequest",
    "BatchPredictResponse",
    # structure_service
    "StructureService",
    "create_structure_app",
    "StructureResult",
    "StructurePredictResponse",
    "StructureBatchPredictResponse",
    # pdb_service
    "PdbScoringService",
    "create_pdb_app",
    "PdbScoreRequest",
    "PdbBatchScoreRequest",
    "PdbScoreResult",
    "PdbScoreResponse",
    "PdbBatchScoreResponse",
    # shared
    "HealthResponse",
    "InfoResponse",
]
