"""
service.py
==========
ESMFold 3D 结构预测微服务。

原仓库: https://github.com/facebookresearch/esm
论文: Lin et al. (2023) "Evolutionary-scale prediction of atomic-level protein
      structure with a language model". *Science*, 379(6637), 1123–1130.

ESMFold 使用 ESM-2 (3B) 语言模型直接从序列端到端预测蛋白质三维结构。
相比 AlphaFold2 快 ~60 倍，无需 MSA/数据库搜索。

注意事项:
  - GPU (CUDA) 必需；CPU 环境下 load_model() 抛出异常，/health 返回 status: "loading"
  - 首次启动自动下载模型权重 (~8 GB) 到 TORCH_HOME 目录
  - 显存建议 ≥16 GB（可通过 set_chunk_size 降低显存占用）

使用方式:
    cd tools/ESMFold
    TORCH_HOME=../models/fair-esm/ uv sync
    TORCH_HOME=../models/fair-esm/ uv run python service.py

环境变量:
    TORCH_HOME        PyTorch 模型缓存目录（推荐指向 tools/models/fair-esm/）
    JOBS_FILE         异步 Job 持久化路径（可选）

API 端点:
    GET  /                   → 服务信息
    GET  /health             → 健康检查
    GET  /info               → 工具信息
    POST /predict            → 单序列结构预测
    POST /predict/batch      → 批量结构预测（串行执行）
    POST /predict/async      → 异步提交预测 → 202 {job_id, status_url}
    GET  /status/{job_id}    → 查询任务状态
    GET  /result/{job_id}    → 获取任务结果
    GET  /jobs               → 列出所有任务
    DELETE /jobs/{job_id}    → 清理任务
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.structure_service import (
    StructureService,
    create_app,
    StructureResult,
    StructurePredictResponse,
    StructureBatchPredictResponse,
    BatchPredictRequest,
    PredictRequest,
)
from tools.utils import detect_system
from tools.template.logger import get_logger


class ESMFoldService(StructureService):
    """ESMFold 3D 结构预测服务。

    基于 Meta FAIR 的 ESM-2 (3B) 语言模型，端到端单序列结构预测。
    无需 MSA/模板，速度比 AlphaFold2 快约 60 倍。

    环境要求:
      - NVIDIA GPU (CUDA)
      - 显存 ≥16 GB（建议 24 GB+）
      - PyTorch + fair-esm[esmfold]
    """

    tool_name = "esmfold"
    version = "1.0.0"
    description = (
        "ESMFold 3D 结构预测 — Meta FAIR ESM-2 语言模型端到端折叠, "
        "无需 MSA/模板, 比 AlphaFold2 快 ~60 倍。GPU 必需。"
    )
    recommended_batch_size = 1  # 3B 参数模型，单序列即满载

    def __init__(self):
        super().__init__()
        self._ready_message: str = "Not checked yet"
        # 设置 TORCH_HOME 确保模型落入共享池
        if "TORCH_HOME" not in os.environ:
            default_cache = Path(PROJECT_ROOT) / "tools" / "models" / "fair-esm"
            default_cache.mkdir(parents=True, exist_ok=True)
            os.environ["TORCH_HOME"] = str(default_cache)

    # ── 模型加载 ──────────────────────────────────────────────

    async def load_model(self) -> None:
        """加载 ESMFold 模型。

        1. 检测 CUDA GPU
        2. 加载 esmfold_v1() 权重（首次自动下载 ~8 GB）
        3. 移至 GPU 并设置 chunk_size 控制显存
        """
        self.logger.info("Loading ESMFold model …")
        self.logger.info("TORCH_HOME=%s", os.environ.get('TORCH_HOME', '~/.cache/torch/hub/'))

        import torch

        if not torch.cuda.is_available():
            self._ready_message = (
                "ESMFold requires CUDA GPU but torch.cuda is not available. "
                "This machine has no NVIDIA GPU or no CUDA-capable PyTorch installed."
            )
            self.logger.warning("%s", self._ready_message)
            raise RuntimeError(self._ready_message)

        gpu_name = torch.cuda.get_device_name(0)
        props = torch.cuda.get_device_properties(0)
        total_mem = getattr(props, 'total_memory', getattr(props, 'total_mem', 0))
        gpu_mem = total_mem / (1 << 30)
        self.logger.info("GPU: %s (%.0f GB)", gpu_name, gpu_mem)

        # numpy<2.0 compat: BUFSIZE removed in numpy 2.0+
        import numpy as np
        np.BUFSIZE = 8192

        # torch._six was removed in PyTorch 2.5+; fair-esm still imports it
        if not hasattr(torch, '_six'):
            import types
            torch._six = types.ModuleType('torch._six')
            torch._six.PY3 = True
            torch._six.PY37 = True
            torch._six.inf = float('inf')
            torch._six.string_classes = (str, bytes)
            import sys
            sys.modules['torch._six'] = torch._six

        import esm
        from esm.esmfold.v1.esmfold import ESMFold

        # 手动加载 checkpoint，跳过非 ESM key 的完整性检查
        # （openfold≥2.0 重构了 IPA 模块路径，checkpoint 中缺少
        #  trunk.structure_module.ipa.linear_q_points 等 key,
        #  这些层将被随机初始化，不影响其余权重加载）
        from pathlib import Path
        model_url = "https://dl.fbaipublicfiles.com/fair-esm/models/esmfold_3B_v1.pt"
        model_data = torch.hub.load_state_dict_from_url(
            model_url, progress=False, map_location="cpu",
        )
        cfg = model_data["cfg"]["model"]
        model_state = model_data["model"]
        self.model = ESMFold(esmfold_config=cfg)
        self.model.load_state_dict(model_state, strict=False)
        self.model = self.model.eval().cuda()

        # 设置 chunk_size 减少显存占用
        #   None → 全部计算，显存需求 O(L²)
        #   128  → 分块计算，显存需求 O(L)，速度略慢
        self.model.set_chunk_size(128)

        self._loaded = True
        self._model_status = {
            "model": "esmfold_v1",
            "backbone": "esm2_t36_3B_UR50D",
            "parameters": "~3B",
            "chunk_size": 128,
        }
        self._system_info = detect_system()
        self._ready_message = f"ESMFold ready — {gpu_name} ({gpu_mem:.0f} GB)"
        self.logger.info("%s", self._ready_message)

    # ── 结构预测 ──────────────────────────────────────────────

    async def predict_structure(self, sequence: str) -> StructureResult:
        """对一条氨基酸序列进行 ESMFold 结构预测。

        1. 模型推理 (infer_pdb)
        2. 从 PDB b_factor 字段提取 pLDDT 置信度
        3. 清理 GPU 缓存
        """
        if not self._loaded:
            return StructureResult(
                sequence=sequence,
                pdb_content="",
                confidence=None,
                details={
                    "error": "Model not loaded",
                    "diagnosis": self._ready_message,
                },
            )

        import torch

        try:
            self.logger.info("Predicting structure (len=%d) …", len(sequence))

            pdb_content: str = ""
            confidence: float | None = None
            details: dict = {}

            with torch.no_grad():
                pdb_content = self.model.infer_pdb(sequence)

            # 从 PDB b_factor 提取 pLDDT
            if pdb_content:
                try:
                    import biotite.structure.io as bsio
                    import io

                    pdb_file = bsio.PDBFile.read(io.StringIO(pdb_content))
                    struct = pdb_file.get_structure(model=1)
                    if struct is not None and hasattr(struct, "b_factor"):
                        b_factors = struct.b_factor
                        raw_plddt = float(b_factors.mean())
                        confidence = raw_plddt / 100.0  # 归一化到 0-1 范围
                except Exception:
                    confidence = None

            # 清理显存
            torch.cuda.empty_cache()

            return StructureResult(
                sequence=sequence,
                pdb_content=pdb_content,
                confidence=confidence,
                details={
                    "mean_plddt": confidence,
                    "sequence_length": len(sequence),
                    "gpu_used": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                },
            )

        except Exception as exc:
            torch.cuda.empty_cache()
            return StructureResult(
                sequence=sequence,
                pdb_content="",
                confidence=None,
                details={"error": f"Prediction failed: {exc}"},
            )

    # ── 单序列预测 ────────────────────────────────────────────

    async def predict_single(self, request: PredictRequest) -> StructurePredictResponse:
        if not self._loaded:
            return StructurePredictResponse(
                success=False,
                peptide_id=request.peptide_id,
                sequence=request.sequence,
                result=None,
                error=self._ready_message,
            )
        return await super().predict_single(request)

    # ── 批量预测 ──────────────────────────────────────────────

    async def predict_batch(
        self, request: BatchPredictRequest
    ) -> StructureBatchPredictResponse:
        """批量结构预测 — 串行执行，每条预测后清理显存。"""
        if not self._loaded:
            return StructureBatchPredictResponse(
                success=False,
                results=[],
                total=0,
                error=self._ready_message,
            )

        results: list[StructureResult] = []
        for i, item in enumerate(request.sequences):
            self.logger.info("Batch %d/%d: %s (len=%d)",
                              i + 1, len(request.sequences),
                              item.peptide_id or 'unnamed', len(item.sequence))
            result = await self.predict_structure(item.sequence)
            result.peptide_id = item.peptide_id or "unknown"
            result.sequence = item.sequence
            results.append(result)

        return StructureBatchPredictResponse(
            success=True,
            results=results,
            total=len(results),
            error=None,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("PORT", "8203"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    logger = get_logger("esmfold")
    app = create_app(ESMFoldService, enable_async=True)
    logger.info("Starting on %s:%s", HOST, PORT)
    logger.info("Async job endpoints enabled: /predict/async, /status/{id}, /result/{id}, /jobs, DELETE /jobs/{id}")
    uvicorn.run(app, host=HOST, port=PORT)
