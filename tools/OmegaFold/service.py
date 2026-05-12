"""
service.py
==========
OmegaFold 3D 结构预测微服务。

原仓库: https://github.com/HeliXonProtein/OmegaFold
论文: Wu et al. (2022) "High-resolution de novo structure prediction from
      primary sequence". bioRxiv, 2022.07.21.500999.

OmegaFold 是一种基于预训练蛋白质语言模型和几何变换器的单序列结构预测方法。
支持 GPU/CUDA、Apple MPS 和 CPU 三种后端。

注意事项:
  - 首次启动自动下载模型权重 (release1.pt ~1.5 GB) 到缓存目录
  - 支持 model 1 和 model 2 两个版本（通过环境变量 OMEGAFOLD_MODEL 选择）
  - GPU 推荐；无 GPU 时自动退回到 CPU/MPS（速度较慢）

使用方式:
    cd tools/OmegaFold
    uv sync
    uv run python service.py

环境变量:
    OMEGAFOLD_MODEL      模型版本: 1 或 2 (默认: 1)
    OMEGAFOLD_CACHE      权重缓存目录 (默认: ~/.cache/omegafold_ckpt/)
    OMEGAFOLD_NUM_CYCLE  循环次数 (默认: 10)
    OMEGAFOLD_SUBBATCH   subbatch 大小控制显存 (默认: 序列全长)
    JOBS_FILE            异步 Job 持久化路径 (可选)

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
import tempfile
import uuid
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


class OmegaFoldService(StructureService):
    """OmegaFold 3D 结构预测服务。

    基于 HeliXon 的 OmegaFold 模型，使用预训练蛋白质语言模型和几何变换器
    进行单序列结构预测。支持 GPU / CPU / MPS 三种后端。

    环境要求:
      - GPU 推荐（CUDA 或 Apple MPS）
      - 无 GPU 时 CPU 也可运行（速度较慢）
      - 显存建议 ≥8 GB（可通过 subbatch 降低）
    """

    tool_name = "omegafold"
    version = "1.0.0"
    description = (
        "OmegaFold 3D 结构预测 — HeliXon 预训练 PLM + 几何变换器, "
        "支持 GPU/CPU/MPS, 无需 MSA/模板。"
    )
    recommended_batch_size = 1

    def __init__(self):
        super().__init__()
        self._ready_message: str = "Not checked yet"
        self._model_idx: int = int(os.environ.get("OMEGAFOLD_MODEL", "1"))
        self._num_cycle: int = int(os.environ.get("OMEGAFOLD_NUM_CYCLE", "10"))
        self._subbatch: int | None = (
            int(v) if (v := os.environ.get("OMEGAFOLD_SUBBATCH")) else None
        )
        self._cache_dir: str = os.environ.get(
            "OMEGAFOLD_CACHE",
            os.path.expanduser("~/.cache/omegafold_ckpt/"),
        )

    # ── 模型加载 ──────────────────────────────────────────────

    async def load_model(self) -> None:
        """加载 OmegaFold 模型。

        1. 检测可用设备 (cuda / mps / cpu)
        2. 下载/加载权重
        3. 构建并初始化 OmegaFold 模型
        """
        print(f"[{self.tool_name}] Loading OmegaFold (model {self._model_idx}) …")

        import torch

        # 选择设备
        if torch.cuda.is_available():
            device = "cuda"
            gpu_name = torch.cuda.get_device_name(0)
            print(f"[{self.tool_name}] GPU: {gpu_name}")
        elif torch.backends.mps.is_available():
            device = "mps"
            print(f"[{self.tool_name}] Using Apple MPS")
        else:
            device = "cpu"
            print(f"[{self.tool_name}] No GPU found, falling back to CPU")

        import omegafold as of
        from omegafold import pipeline

        # 下载权重 (复用 OmegaFold 内置的下载逻辑)
        if self._model_idx == 1:
            weights_url = "https://helixon.s3.amazonaws.com/release1.pt"
            weights_file = os.path.join(self._cache_dir, "model.pt")
        else:
            weights_url = "https://helixon.s3.amazonaws.com/release2.pt"
            weights_file = os.path.join(self._cache_dir, "model2.pt")

        os.makedirs(self._cache_dir, exist_ok=True)

        print(f"[{self.tool_name}] Weights: {weights_file}")
        state_dict = pipeline._load_weights(weights_url, weights_file)

        # 构建模型
        self.model = of.OmegaFold(of.make_config(self._model_idx))
        self.model.load_state_dict(state_dict)
        self.model.eval()
        self.model.to(device)

        self._loaded = True
        self._model_status = {
            "model_version": self._model_idx,
            "device": device,
            "num_cycle": self._num_cycle,
            "subbatch_size": self._subbatch,
            "weights": weights_file,
        }
        self._system_info = detect_system()
        self._ready_message = (
            f"OmegaFold ready — model {self._model_idx} on {device}"
        )
        print(f"[{self.tool_name}] {self._ready_message}")

    # ── 结构预测 ──────────────────────────────────────────────

    async def predict_structure(self, sequence: str) -> StructureResult:
        """对一条氨基酸序列进行 OmegaFold 结构预测。

        1. 将序列写入临时 FASTA 文件
        2. 用 OmegaFold pipeline 处理为模型输入
        3. 模型推理
        4. 将结果 PDB 读回内存
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
        import omegafold as of
        from omegafold import pipeline
        import tempfile
        import os

        device = next(self.model.parameters()).device
        job_id = uuid.uuid4().hex[:8]

        with tempfile.TemporaryDirectory(prefix=f"omegafold_{job_id}_") as tmpdir:
            try:
                # 1. 写入临时 FASTA
                fasta_path = os.path.join(tmpdir, "input.fasta")
                seq_name = f"seq_{job_id}"
                with open(fasta_path, "w") as f:
                    f.write(f">{seq_name}\n{sequence}\n")

                # 2. 处理输入
                output_dir = os.path.join(tmpdir, "output")
                os.makedirs(output_dir, exist_ok=True)

                # 预处理模型的 forward config
                fwd_cfg = type(
                    "FwdCfg", (), {
                        "subbatch_size": self._subbatch,
                        "num_recycle": self._num_cycle,
                    }
                )()

                # 逐序列预测
                for input_data, save_path in pipeline.fasta2inputs(
                    fasta_path,
                    num_pseudo_msa=15,
                    output_dir=output_dir,
                    device=device,
                    mask_rate=0.12,
                    num_cycle=self._num_cycle,
                ):
                    seq_in_data: list[dict] = [d.to(device) if hasattr(d, "to") else d
                                                for d in input_data]

                    output = self.model(
                        input_data,
                        predict_with_confidence=True,
                        fwd_cfg=fwd_cfg,
                    )

                    # 3. 保存 PDB
                    pipeline.save_pdb(
                        pos14=output["final_atom_positions"],
                        b_factors=output["confidence"] * 100,
                        sequence=input_data[0]["p_msa"][0],
                        mask=input_data[0]["p_msa_mask"][0],
                        save_path=save_path,
                        model=0,
                    )

                    # 4. 读取 PDB
                    pdb_content = ""
                    if os.path.exists(save_path):
                        with open(save_path) as f:
                            pdb_content = f.read()

                    # 5. 提取置信度
                    confidence_val = float(output.get("confidence_overall", 0))

                    # 清理显存
                    del output
                    torch.cuda.empty_cache()

                    return StructureResult(
                        sequence=sequence,
                        pdb_content=pdb_content,
                        confidence=confidence_val,
                        details={
                            "mean_plddt": confidence_val,
                            "sequence_length": len(sequence),
                            "model_version": self._model_idx,
                            "num_cycle": self._num_cycle,
                            "device": str(device),
                        },
                    )

                return StructureResult(
                    sequence=sequence,
                    pdb_content="",
                    confidence=None,
                    details={"error": "OmegaFold pipeline returned no results"},
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

        import torch

        results: list[StructureResult] = []
        for i, item in enumerate(request.sequences):
            print(f"[{self.tool_name}] Batch {i + 1}/{len(request.sequences)}: "
                  f"{item.peptide_id or 'unnamed'} (len={len(item.sequence)})")
            result = await self.predict_structure(item.sequence)
            result.peptide_id = item.peptide_id or "unknown"
            result.sequence = item.sequence
            results.append(result)
            torch.cuda.empty_cache()

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

    PORT = int(os.environ.get("PORT", "8204"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    app = create_app(OmegaFoldService, enable_async=True)
    print(f"[omegafold] Starting on {HOST}:{PORT}")
    print("[omegafold] Async job endpoints enabled: "
          "/predict/async, /status/{id}, /result/{id}, /jobs, DELETE /jobs/{id}")
    uvicorn.run(app, host=HOST, port=PORT)
