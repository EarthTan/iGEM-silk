"""
service.py
==========
PEP-FOLD4 肽从头结构预测微服务。

原服务: https://bioserv.rpbs.univ-paris-diderot.fr/services/PEP-FOLD4/
论文: Rey et al. (2023) "PEP-FOLD4: a pH-dependent force field for peptide
      structure prediction". *Nucleic Acids Research*, 51(W1), W432–W437.

PEP-FOLD4 使用结构字母表 (structural alphabet)、sOPEP 粗粒度力场和蒙特卡洛
采样进行肽从头结构预测。支持 pH 和离子强度依赖的静电相互作用 (Debye-Hückel)。

此服务封装官方 PEP-FOLD4 Docker 镜像（RPBS OwnCloud 分发），通过 Docker CLI
调用。镜像需遵守 Université Paris Cité 非商业许可。

使用方式：
    cd tools/PEP-FOLD4
    source .venv/bin/activate
    python service.py

环境变量：
    PF4_IMAGE          PEP-FOLD4 Docker 镜像名 (默认: pepfold4)
    PF4_KEEP_WORKSPACE  设为 1 保留临时工作目录便于调试
    PF4_WORKSPACE      workspace 根目录 (默认: /tmp/pf4_workspace; Docker Compose 下需 volume mount)

API 端点：
    GET  /              → 服务信息
    GET  /health        → 健康检查
    GET  /info          → 工具信息
    POST /predict       → 单序列结构预测
    POST /predict/batch → 批量结构预测 (逐条处理)
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

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


# ═══════════════════════════════════════════════════════════════════════════════
# 环境检测
# ═══════════════════════════════════════════════════════════════════════════════


def _check_docker() -> tuple[bool, str]:
    """检查 Docker 守护进程是否可用。"""
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, f"Docker {result.stdout.strip()}"
        return False, f"Docker daemon not accessible: {result.stderr.strip()}"
    except FileNotFoundError:
        return False, "docker CLI not found"
    except subprocess.TimeoutExpired:
        return False, "docker info timed out"
    except Exception as exc:
        return False, f"Docker check error: {exc}"


def _check_pf4_image(image: str) -> tuple[bool, str]:
    """检查 PEP-FOLD4 Docker 镜像是否存在。"""
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", image],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, f"Image {image} found"
        return False, f"Image '{image}' not found — load from RPBS OwnCloud first"
    except Exception as exc:
        return False, f"Image check error: {exc}"


# ═══════════════════════════════════════════════════════════════════════════════
# 服务类
# ═══════════════════════════════════════════════════════════════════════════════


class PEPFOLD4Service(StructureService):
    """PEP-FOLD4 肽从头结构预测服务 (Docker 封装)。

    通过 Docker CLI 调用官方 PEP-FOLD4 镜像。PEP-FOLD4 专为短肽 (5–40 aa)
    设计，使用 sOPEP 力场 + 蒙特卡洛采样，支持 pH/离子强度参数。

    环境要求:
      - Docker 守护进程
      - PEP-FOLD4 Docker 镜像 (需从 RPBS OwnCloud 获取，非商业许可)
      - CPU 即可运行 (无需 GPU)
    """

    tool_name = "pepfold4"
    version = "4.0.0"
    description = (
        "PEP-FOLD4 肽从头结构预测 — sOPEP 力场 + 蒙特卡洛采样, "
        "支持 pH/离子强度依赖。Docker 封装。"
    )
    recommended_batch_size = 5

    # PEP-FOLD4 支持的序列长度范围
    MIN_LENGTH = 5
    MAX_LENGTH = 40

    # 默认参数
    DEFAULT_PH = 7.0
    DEFAULT_IONIC_STRENGTH = 150.0  # mM
    DEFAULT_NUM_MODELS = 100

    def __init__(self):
        super().__init__()
        self._ready_message: str = "Not checked yet"
        self._pf4_image: str = os.environ.get("PF4_IMAGE", "pepfold4")
        self._keep_workspace: bool = os.environ.get("PF4_KEEP_WORKSPACE", "") == "1"
        self._workspace_base: Path = Path(os.environ.get("PF4_WORKSPACE", "/tmp/pf4_workspace"))

    # ── 环境验证 ──────────────────────────────────────────────

    async def load_model(self) -> None:
        """验证 PEP-FOLD4 Docker 环境。"""
        print(f"[{self.tool_name}] Checking PEP-FOLD4 environment …")

        checks: list[tuple[str, bool, str]] = []

        ok_docker, msg_docker = _check_docker()
        checks.append(("Docker", ok_docker, msg_docker))

        if ok_docker:
            ok_img, msg_img = _check_pf4_image(self._pf4_image)
            checks.append(("PF4 image", ok_img, msg_img))
        else:
            checks.append(("PF4 image", False, "Skipped (Docker not available)"))

        failures: list[str] = []
        for name, ok, msg in checks:
            status = "✓" if ok else "✗"
            print(f"  [{status}] {name}: {msg}")
            if not ok:
                failures.append(f"{name}: {msg}")

        if not failures:
            self._ready_message = "PEP-FOLD4 ready — Docker + image verified"
            print(f"[{self.tool_name}] {self._ready_message}")
            return

        self._ready_message = (
            f"PEP-FOLD4 NOT available on this machine. "
            f"Failed checks: {'; '.join(failures)}"
        )
        print(f"[{self.tool_name}] {self._ready_message}")
        raise RuntimeError(self._ready_message)

    # ── 序列校验 ──────────────────────────────────────────────

    @staticmethod
    def _validate_sequence(sequence: str) -> str | None:
        """校验序列是否在 PEP-FOLD4 支持范围内。返回错误信息或 None。"""
        seq = sequence.strip().upper()
        if len(seq) < PEPFOLD4Service.MIN_LENGTH:
            return f"Sequence too short ({len(seq)} aa, min {PEPFOLD4Service.MIN_LENGTH})"
        if len(seq) > PEPFOLD4Service.MAX_LENGTH:
            return f"Sequence too long ({len(seq)} aa, max {PEPFOLD4Service.MAX_LENGTH})"
        standard_aa = set("ACDEFGHIKLMNPQRSTVWY")
        invalid = [c for c in seq if c not in standard_aa]
        if invalid:
            return f"Non-standard amino acids: {sorted(set(invalid))}"
        return None

    # ── 结构预测 ──────────────────────────────────────────────

    async def predict_structure(self, sequence: str) -> StructureResult:
        """对一条肽序列运行 PEP-FOLD4 结构预测。

        1. 校验序列 (5–40 aa, 标准氨基酸)
        2. 创建临时工作目录
        3. 准备 PEP-FOLD4 输入
        4. 调用 docker run pepfold4 ...
        5. 解析输出 PDB + 能量分数
        6. 清理工作目录
        """
        if not self._loaded:
            return StructureResult(
                sequence=sequence,
                pdb_content="",
                confidence=None,
                details={
                    "error": "Environment not ready",
                    "diagnosis": self._ready_message,
                },
            )

        # 序列校验
        error = self._validate_sequence(sequence)
        if error:
            return StructureResult(
                sequence=sequence,
                pdb_content="",
                confidence=None,
                details={"error": error},
            )

        job_id = uuid.uuid4().hex[:12]
        job_name = f"pf4_{job_id}"
        workspace = self._workspace_base / job_name
        workspace.mkdir(parents=True, exist_ok=True)

        input_dir = workspace / "input"
        output_dir = workspace / "output"
        input_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)

        try:
            # 1. 写入 FASTA 输入文件
            fasta_path = input_dir / "sequence.fasta"
            fasta_path.write_text(f">pf4_job\n{sequence}\n")

            # 2. 运行 PEP-FOLD4 Docker
            #    注: Docker 具体命令取决于镜像的实际接口。
            #    以下基于 RPBS PEP-FOLD4 服务的典型调用方式。
            #    如果镜像提供的是 Web 服务 (Mobyle)，需改为启动容器 + HTTP 调用。
            cmd = [
                "docker", "run", "--rm",
                "--volume", f"{input_dir}:/input",
                "--volume", f"{output_dir}:/output",
                self._pf4_image,
                # PEP-FOLD4 命令行参数 (根据实际镜像调整)
                "--fasta", "/input/sequence.fasta",
                "--output_dir", "/output",
                "--ph", str(self.DEFAULT_PH),
                "--ionic_strength", str(self.DEFAULT_IONIC_STRENGTH),
                "--num_models", str(self.DEFAULT_NUM_MODELS),
            ]

            print(f"[{self.tool_name}] Running PEP-FOLD4 for {job_name} "
                  f"(sequence length={len(sequence)}) …")

            proc = await _run_subprocess(cmd, timeout=1800)

            if proc.returncode != 0:
                error_msg = proc.stderr[-2000:] if proc.stderr else f"exit code {proc.returncode}"
                return StructureResult(
                    sequence=sequence,
                    pdb_content="",
                    confidence=None,
                    details={
                        "error": f"PEP-FOLD4 failed: {error_msg}",
                        "job_name": job_name,
                        "returncode": proc.returncode,
                    },
                )

            # 3. 解析输出
            #    PEP-FOLD4 输出 top 5 模型: model1.pdb – model5.pdb
            pdb_files = sorted(output_dir.glob("model*.pdb"))
            if not pdb_files:
                # 尝试通配
                pdb_files = sorted(output_dir.glob("*.pdb"))

            if not pdb_files:
                return StructureResult(
                    sequence=sequence,
                    pdb_content="",
                    confidence=None,
                    details={
                        "error": "No PDB output files found",
                        "job_name": job_name,
                        "output_dir": str(output_dir),
                    },
                )

            # 取 model1 (能量最低 / 聚类中心) 作为主结构
            top_pdb = pdb_files[0].read_text()
            confidence = None

            # 读取能量信息 (如果存在)
            energy_details: dict[str, Any] = {}
            energy_path = output_dir / "energies.json"
            if not energy_path.exists():
                energy_path = output_dir / "ClusterReport.txt"
            if energy_path.exists():
                try:
                    energy_text = energy_path.read_text()
                    energy_details["energy_report"] = energy_text[:2000]
                    # 尝试从报告中提取能量值作为伪置信度
                except Exception:
                    pass

            details: dict[str, Any] = {
                "format": "pdb",
                "job_name": job_name,
                "num_models": len(pdb_files),
                "model_files": [p.name for p in pdb_files],
                "output_dir": str(output_dir) if self._keep_workspace else None,
            }
            if energy_details:
                details["energy"] = energy_details

            return StructureResult(
                sequence=sequence,
                pdb_content=top_pdb,
                confidence=confidence,
                details=details,
            )

        except subprocess.TimeoutExpired:
            return StructureResult(
                sequence=sequence,
                pdb_content="",
                confidence=None,
                details={
                    "error": "PEP-FOLD4 prediction timed out (1800s limit)",
                    "job_name": job_name,
                },
            )
        except Exception as exc:
            return StructureResult(
                sequence=sequence,
                pdb_content="",
                confidence=None,
                details={
                    "error": f"Prediction error: {exc}",
                    "job_name": job_name,
                },
            )
        finally:
            if not self._keep_workspace:
                shutil.rmtree(workspace, ignore_errors=True)

    # ── 批量预测 ──────────────────────────────────────────────

    async def predict_batch(
        self, request: BatchPredictRequest
    ) -> StructureBatchPredictResponse:
        """批量结构预测 — 逐条处理，每次只跑一个 PEP-FOLD4 任务。"""
        if not self._loaded:
            return StructureBatchPredictResponse(
                success=False,
                results=[],
                total=0,
                error=self._ready_message,
            )

        results: list[StructureResult] = []
        for i, item in enumerate(request.sequences):
            print(f"[{self.tool_name}] Batch {i + 1}/{len(request.sequences)}: "
                  f"{item.peptide_id or 'unnamed'} (len={len(item.sequence)})")
            result = await self.predict_structure(item.sequence)
            result.peptide_id = item.peptide_id or "unknown"
            results.append(result)

        return StructureBatchPredictResponse(
            success=True,
            results=results,
            total=len(results),
            error=None,
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


# ═══════════════════════════════════════════════════════════════════════════════
# 异步 subprocess
# ═══════════════════════════════════════════════════════════════════════════════


async def _run_subprocess(cmd: list[str], timeout: int = 1800):
    """在线程池中运行 subprocess，不阻塞事件循环。"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=timeout),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("PORT", "8202"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    app = create_app(PEPFOLD4Service)
    print(f"[pepfold4] Starting on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT)
