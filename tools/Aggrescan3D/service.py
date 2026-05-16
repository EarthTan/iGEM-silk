"""
service.py
==========
Aggrescan3D PDB 聚集倾向分析微服务。

原仓库: https://bitbucket.org/lcbio/aggrescan3d
原工具: Aggrescan3D standalone, Python 2.7, console entrypoint `aggrescan`
论文: Kuriata et al. (2019), Aggrescan3D standalone package.

Aggrescan3D 本体依赖 Python 2.7。本服务通过 conda 环境调用 aggrescan 命令，
解析原始输出 `A3D.csv`。

使用方式：推荐通过 Docker Compose 运行（--profile cpu）。
  非 Docker 运行需要手动配置 conda Python 2.7 环境并安装 aggrescan3d。
  参考: https://bitbucket.org/lcbio/aggrescan3d

API 端点：
    GET  /              → 服务信息
    GET  /health        → 健康检查
    GET  /info          → 工具信息
    POST /predict       → 单次 PDB 评分
    POST /predict/batch → 批量 PDB 评分

环境变量：
    AGGRESCAN_CONDA_ENV  Aggrescan3D conda 环境路径（非 Docker 时必须设置）
                          (默认: /home/lenovo/miniconda3/envs/aggrescan3d)
    A3D_KEEP_WORKSPACE   设为 1 保留临时工作目录便于调试
    A3D_WORKSPACE        workspace 根目录 (默认: /tmp/a3d_workspace)
    A3D_TIMEOUT          单次预测超时秒数 (默认: 900)
    A3D_DISTANCE         聚集距离阈值 (默认: 10)
"""

from __future__ import annotations

import asyncio
import csv
import os
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.logger import get_logger
from tools.template.pdb_service import (
    PdbBatchScoreRequest,
    PdbBatchScoreResponse,
    PdbScoreRequest,
    PdbScoreResponse,
    PdbScoreResult,
    PdbScoringService,
    create_app,
)


DEFAULT_DISTANCE_CUTOFF = 10
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_CONDA_ENV = "/home/lenovo/miniconda3/envs/aggrescan3d"


@dataclass(frozen=True)
class A3DResidue:
    protein: str
    chain: str
    residue_id: str
    residue_name: str
    score: float


def _check_aggrescan(conda_env: str) -> tuple[bool, str]:
    """检查 aggrescan 命令是否可用。"""
    aggrescan_path = Path(conda_env) / "bin" / "aggrescan"
    if not aggrescan_path.is_file():
        return False, f"aggrescan not found at {aggrescan_path}"
    try:
        result = subprocess.run(
            [str(aggrescan_path), "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True, f"aggrescan found at {aggrescan_path}"
        return False, f"aggrescan failed: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return False, "aggrescan --help timed out"
    except Exception as exc:
        return False, f"aggrescan check error: {exc}"


def _parse_a3d_csv(path: Path) -> list[A3DResidue]:
    """解析 Aggrescan3D 原始 A3D.csv。"""
    residues: list[A3DResidue] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"protein", "chain", "residue", "residue_name", "score"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"A3D.csv missing columns: {sorted(missing)}")

        for row in reader:
            try:
                score = float(row["score"])
            except (TypeError, ValueError):
                continue
            residues.append(
                A3DResidue(
                    protein=row["protein"],
                    chain=row["chain"],
                    residue_id=row["residue"],
                    residue_name=row["residue_name"],
                    score=score,
                )
            )
    if not residues:
        raise ValueError("A3D.csv contained no residue scores")
    return residues


def _summarize_scores(residues: list[A3DResidue]) -> dict[str, Any]:
    """生成整体、链级和逐残基统计。"""
    scores = [r.score for r in residues]
    positive = [s for s in scores if s > 0.0]
    positive_fraction = len(positive) / len(scores)
    positive_mean = sum(positive) / len(positive) if positive else 0.0
    max_score = max(scores)
    min_score = min(scores)
    avg_score = sum(scores) / len(scores)
    total_score = sum(scores)

    chain_stats: dict[str, dict[str, Any]] = {}
    for chain in sorted({r.chain for r in residues}):
        chain_scores = [r.score for r in residues if r.chain == chain]
        chain_positive = [s for s in chain_scores if s > 0.0]
        chain_stats[chain] = {
            "num_residues": len(chain_scores),
            "min_score": round(min(chain_scores), 4),
            "max_score": round(max(chain_scores), 4),
            "avg_score": round(sum(chain_scores) / len(chain_scores), 4),
            "total_score": round(sum(chain_scores), 4),
            "positive_fraction": round(len(chain_positive) / len(chain_scores), 4),
        }

    # Aggrescan3D 原始 score 不是 0-1。这里给统一 API 一个风险归一化：
    # 聚集热点由正分残基比例、正分平均值和最大正热点共同决定。
    positive_mean_scaled = min(max(positive_mean / 4.0, 0.0), 1.0)
    max_scaled = min(max(max_score / 4.0, 0.0), 1.0)
    risk_score = (
        0.50 * positive_fraction
        + 0.30 * positive_mean_scaled
        + 0.20 * max_scaled
    )
    risk_score = min(max(risk_score, 0.0), 1.0)

    if risk_score >= 0.50:
        label = "high_aggregation_risk"
    elif risk_score >= 0.25:
        label = "moderate_aggregation_risk"
    else:
        label = "low_aggregation_risk"

    top_hotspots = sorted(residues, key=lambda r: r.score, reverse=True)[:20]

    return {
        "risk_score": round(risk_score, 4),
        "label": label,
        "statistics": {
            "num_residues": len(residues),
            "min_score": round(min_score, 4),
            "max_score": round(max_score, 4),
            "avg_score": round(avg_score, 4),
            "total_score": round(total_score, 4),
            "positive_fraction": round(positive_fraction, 4),
            "positive_mean": round(positive_mean, 4),
        },
        "chain_statistics": chain_stats,
        "top_hotspots": [
            {
                "chain": r.chain,
                "residue_id": r.residue_id,
                "residue_name": r.residue_name,
                "score": round(r.score, 4),
            }
            for r in top_hotspots
        ],
        "residues": [
            {
                "protein": r.protein,
                "chain": r.chain,
                "residue_id": r.residue_id,
                "residue_name": r.residue_name,
                "a3d_score": round(r.score, 4),
                "is_aggregation_prone": r.score > 0.0,
            }
            for r in residues
        ],
    }


async def _run_subprocess(cmd: list[str], timeout: int, logger=None):
    """异步运行子进程，实时流式输出 stdout/stderr 到 logger。"""
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    async def _stream(stream, label: str, collector: list[str]) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            collector.append(decoded)
            if logger and decoded.strip():
                logger.info("[%s] %s", label, decoded)

    try:
        await asyncio.wait_for(
            asyncio.gather(
                _stream(process.stdout, "A3D-out", stdout_lines),
                _stream(process.stderr, "A3D", stderr_lines),
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        raise subprocess.TimeoutExpired(cmd, timeout)

    await process.wait()

    return subprocess.CompletedProcess(
        cmd, process.returncode or 0,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
    )


class Aggrescan3DService(PdbScoringService):
    """Aggrescan3D PDB 聚集倾向分析服务。"""

    tool_name = "aggrescan3d"
    version = "1.0.2-wrapper"
    description = (
        "Aggrescan3D 结构聚集倾向分析 — conda Python 2.7 环境，"
        "输入 PDB，输出逐残基 A3D score 和整体聚集风险。"
    )
    recommended_batch_size = 10

    def __init__(self):
        super().__init__()
        self._ready_message = "Not checked yet"
        self._conda_env = os.environ.get(
            "AGGRESCAN_CONDA_ENV", DEFAULT_CONDA_ENV
        )
        self._keep_workspace = os.environ.get("A3D_KEEP_WORKSPACE", "") == "1"
        self._workspace_base = Path(os.environ.get("A3D_WORKSPACE", "/tmp/a3d_workspace"))
        self._timeout = int(os.environ.get("A3D_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
        self._distance = int(os.environ.get("A3D_DISTANCE", str(DEFAULT_DISTANCE_CUTOFF)))

    async def load_model(self) -> None:
        """验证 Aggrescan3D conda 环境。"""
        self.logger.info("Checking Aggrescan3D environment …")

        ok_agg, msg_agg = _check_aggrescan(self._conda_env)

        status = "✓" if ok_agg else "✗"
        self.logger.info("  [%s] aggrescan: %s", status, msg_agg)

        if not ok_agg:
            in_docker = os.path.exists("/.dockerenv")
            self._ready_message = (
                "Aggrescan3D NOT available. " + msg_agg + "\n"
                "此服务依赖 conda Python 2.7 环境中的 aggrescan 命令。\n"
                + (
                    "推荐方式：\n"
                    "  docker compose --profile cpu up -d aggrescan3d\n"
                    "非 Docker 方式：\n"
                    "  1. 安装 miniconda2 并创建 Python 2.7 环境\n"
                    "  2. conda install -c lcbio aggrescan3d\n"
                    "  3. export AGGRESCAN_CONDA_ENV=/path/to/conda/envs/aggrescan3d\n"
                    "  4. 重新启动本服务"
                    if not in_docker else
                    "Docker 内部 aggrescan 未安装，请检查 Dockerfile 构建是否成功。"
                )
            )
            self.logger.warning("%s", self._ready_message)
            raise RuntimeError(self._ready_message)

        self._ready_message = f"Aggrescan3D ready — {self._aggrescan_path}"
        self.logger.info("%s", self._ready_message)

    @property
    def _aggrescan_path(self) -> str:
        return str(Path(self._conda_env) / "bin" / "aggrescan")

    async def score_pdb(
        self,
        pdb_content: str,
        sequence: str | None = None,
        chain_id: str | None = None,
    ) -> PdbScoreResult:
        """对 PDB 结构运行 Aggrescan3D。"""
        if not self._loaded:
            return PdbScoreResult(
                score=0.0,
                label="unavailable",
                details={"error": self._ready_message},
            )

        if "ATOM" not in pdb_content and "HETATM" not in pdb_content:
            raise ValueError("pdb_content does not look like a PDB file")

        job_id = uuid.uuid4().hex[:12]
        job_name = f"a3d_{job_id}"
        workspace = self._workspace_base / job_name
        output_dir = workspace / "run"
        workspace.mkdir(parents=True, exist_ok=True)

        input_path = workspace / "input.pdb"
        input_path.write_text(pdb_content, encoding="utf-8")

        cmd = [
            self._aggrescan_path,
            "-i",
            str(input_path),
            "-w",
            str(output_dir),
            "-v",
            "2",
            "-D",
            str(self._distance),
        ]
        self.logger.info("Running Aggrescan3D job %s …", job_name)

        try:
            proc = await _run_subprocess(cmd, timeout=self._timeout, logger=self.logger)
            if proc.returncode != 0:
                stderr = proc.stderr[-3000:] if proc.stderr else ""
                stdout = proc.stdout[-1000:] if proc.stdout else ""
                raise RuntimeError(
                    f"Aggrescan3D failed with exit code {proc.returncode}. "
                    f"stdout={stdout!r} stderr={stderr!r}"
                )

            csv_path = output_dir / "A3D.csv"
            if not csv_path.exists():
                raise FileNotFoundError(f"Aggrescan3D did not produce {csv_path}")

            residues = _parse_a3d_csv(csv_path)
            if chain_id:
                selected = [r for r in residues if r.chain == chain_id]
                if not selected:
                    available = sorted({r.chain for r in residues})
                    raise ValueError(
                        f"Requested chain_id={chain_id!r} not found. "
                        f"Available chains: {available}"
                    )
                residues = selected
            summary = _summarize_scores(residues)

            output_pdb_path = output_dir / "output.pdb"
            if output_pdb_path.exists():
                try:
                    summary["output_pdb_content"] = output_pdb_path.read_text(
                        encoding="utf-8"
                    )
                except UnicodeDecodeError:
                    summary["output_pdb_path"] = str(output_pdb_path)

            summary["aggrescan3d"] = {
                "conda_env": self._conda_env,
                "aggrescan_path": self._aggrescan_path,
                "distance_cutoff": self._distance,
                "chain": chain_id or "all",
                "chain_filter_mode": "postprocess",
                "raw_csv_header": "protein,chain,residue,residue_name,score",
                "workspace": str(workspace) if self._keep_workspace else None,
            }

            return PdbScoreResult(
                score=summary["risk_score"],
                label=summary["label"],
                details=summary,
            )

        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Aggrescan3D timed out after {self._timeout}s"
            ) from exc
        finally:
            if not self._keep_workspace:
                shutil.rmtree(workspace, ignore_errors=True)

    async def predict_batch(
        self, request: PdbBatchScoreRequest
    ) -> PdbBatchScoreResponse:
        """批量 PDB 评分，限制并发避免同时启动过多 Docker 容器。"""
        if not self._loaded:
            return PdbBatchScoreResponse(
                success=False,
                results=[],
                total=0,
                error=self._ready_message,
            )

        semaphore = asyncio.Semaphore(2)

        async def bounded_predict(item: PdbScoreRequest) -> PdbScoreResult | None:
            async with semaphore:
                try:
                    result = await self.score_pdb(
                        pdb_content=item.pdb_content,
                        sequence=item.sequence,
                        chain_id=item.chain_id,
                    )
                    result.peptide_id = item.peptide_id or "unknown"
                    return result
                except Exception as exc:
                    self.logger.error("Batch item failed: %s", exc)
                    return None

        results = await asyncio.gather(
            *(bounded_predict(item) for item in request.requests)
        )
        valid_results = [r for r in results if r is not None]
        return PdbBatchScoreResponse(
            success=True,
            results=valid_results,
            total=len(valid_results),
            error=None
            if len(valid_results) == len(request.requests)
            else f"{len(valid_results)}/{len(request.requests)} succeeded",
        )

    async def predict_single(self, request: PdbScoreRequest) -> PdbScoreResponse:
        if not self._loaded:
            return PdbScoreResponse(
                success=False,
                peptide_id=request.peptide_id,
                result=None,
                error=self._ready_message,
            )
        return await super().predict_single(request)


if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("PORT", "8102"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    logger = get_logger("aggrescan3d")
    app = create_app(Aggrescan3DService)
    logger.info("Starting on %s:%s", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT)
