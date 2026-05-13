"""
service.py
==========
AlphaFold3 3D 结构预测微服务。

原仓库: https://github.com/google-deepmind/alphafold3
论文: Abramson et al. (2024) "Accurate structure prediction of biomolecular
      interactions with AlphaFold 3". *Nature*, 630, 493–500.

此服务是对官方 AlphaFold3 Docker 镜像的薄封装，通过 Docker CLI 调用 AF3 进行
结构预测。AF3 仅支持 Ubuntu + NVIDIA GPU (RTX)，在不满足条件的环境中服务会
正常启动但 /health 返回 model_loaded: false。

使用方式：
    cd tools/AlphaFold3
    source .venv/bin/activate
    python service.py

环境变量：
    AF3_IMAGE         AlphaFold3 Docker 镜像名 (默认: alphafold3)
    AF3_MODEL_DIR     模型参数目录 (必需)
    AF3_DATABASE_DIR  遗传数据库目录 (必需)
    AF3_KEEP_WORKSPACE  设为 1 保留临时工作目录便于调试
    JOBS_FILE         异步 Job 持久化路径 (可选; 不设置则仅在内存中)

API 端点：
    GET  /                   → 服务信息
    GET  /health             → 健康检查
    GET  /info               → 工具信息
    POST /predict            → 单序列结构预测（同步阻塞）
    POST /predict/batch      → 批量结构预测 (逐条处理)
    POST /predict/async      → 异步提交预测 → 202 {job_id, status_url}
    GET  /status/{job_id}    → 查询任务状态
    GET  /result/{job_id}    → 获取任务结果
    GET  /jobs               → 列出所有任务
    DELETE /jobs/{job_id}    → 清理任务
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.structure_service import (
    BatchPredictRequest,
    StructureBatchPredictResponse,
    StructurePredictResponse,
    StructureResult,
    StructureService,
    create_app,
    PredictRequest,
)
from tools.utils import detect_system
from tools.template.logger import get_logger


def _check_os() -> tuple[bool, str]:
    """AF3 仅支持 Linux (Docker 宿主机为 Linux 内核)。"""
    system = platform.system()
    if system != "Linux":
        return False, f"AlphaFold3 requires Linux (Docker host), current OS: {system}"
    return True, "Linux ✓"


def _check_nvidia_gpu() -> tuple[bool, str]:
    """检查 NVIDIA GPU 是否可用 (通过 Docker 信息查询，无拉取需求)。"""
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{json .Runtimes}}"],
            capture_output=True, text=True, timeout=15,
        )
        if "nvidia" in result.stdout.lower():
            return True, "NVIDIA runtime available (verified via docker info)"
        return False, "NVIDIA runtime not found in Docker"
    except FileNotFoundError:
        return False, "docker CLI not found"
    except subprocess.TimeoutExpired:
        return False, "docker info timed out"
    except Exception as exc:
        return False, f"GPU check error: {exc}"


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


def _check_nvidia_container_toolkit() -> tuple[bool, str]:
    """检查 nvidia-container-toolkit 是否配置 (Docker GPU 支持)。"""
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", "--gpus", "all", "alpine:latest", "echo", "ok"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            return True, "nvidia-container-toolkit configured"
        return False, f"--gpus not working: {result.stderr.strip()[:200]}"
    except FileNotFoundError:
        return False, "docker CLI not found"
    except subprocess.TimeoutExpired:
        return False, "docker run --gpus timed out (first pull may be slow)"
    except Exception as exc:
        return False, f"nvidia-container-toolkit check error: {exc}"


def _check_af3_image(image: str) -> tuple[bool, str]:
    """检查 AF3 Docker 镜像是否存在。"""
    try:
        result = subprocess.run(
            ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}", image],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, f"Image {image} found"
        return False, f"Image '{image}' not found — pull with: docker pull {image}"
    except Exception as exc:
        return False, f"Image check error: {exc}"


def _check_required_dirs(model_dir: str, database_dir: str) -> tuple[bool, str]:
    """检查模型和数据库目录是否存在。"""
    msgs = []
    if model_dir and Path(model_dir).is_dir():
        msgs.append(f"Model dir: {model_dir} ✓")
    elif model_dir:
        msgs.append(f"Model dir NOT FOUND: {model_dir}")
    else:
        msgs.append("AF3_MODEL_DIR not set")

    if database_dir and Path(database_dir).is_dir():
        msgs.append(f"Database dir: {database_dir} ✓")
    elif database_dir:
        msgs.append(f"Database dir NOT FOUND: {database_dir}")
    else:
        msgs.append("AF3_DATABASE_DIR not set")

    all_ok = "NOT FOUND" not in " ".join(msgs) and "not set" not in " ".join(msgs)
    return all_ok, " | ".join(msgs)


class AlphaFold3Service(StructureService):
    """AlphaFold3 3D 结构预测服务 (Docker 封装)。

    通过 Docker CLI 调用官方 alphafold3 镜像。需要:
      - Ubuntu 宿主机 (Linux 内核)
      - NVIDIA GPU + 驱动
      - Docker + nvidia-container-toolkit
      - AlphaFold3 Docker 镜像 (docker pull alphafold3)
      - 模型参数目录 (AF3_MODEL_DIR)
      - 遗传数据库目录 (AF3_DATABASE_DIR)
    """

    tool_name = "alphafold3"
    version = "3.0.0"
    description = (
        "AlphaFold3 3D 结构预测 — Google DeepMind 第三代蛋白质结构预测模型, "
        "Docker 封装。仅支持 Ubuntu + NVIDIA GPU。"
    )
    recommended_batch_size = 1  # AF3 每个预测需数分钟，不可批量

    def __init__(self):
        super().__init__()
        self._ready_message: str = "Not checked yet"
        self._af3_image: str = os.environ.get("AF3_IMAGE", "alphafold3")
        self._model_dir: str = os.environ.get("AF3_MODEL_DIR", "")
        self._database_dir: str = os.environ.get("AF3_DATABASE_DIR", "")
        self._model_host_dir: str = os.environ.get("AF3_MODEL_HOST_DIR", self._model_dir)
        self._database_host_dir: str = os.environ.get("AF3_DATABASE_HOST_DIR", self._database_dir)
        self._keep_workspace: bool = os.environ.get("AF3_KEEP_WORKSPACE", "") == "1"
        self._workspace_base: Path = Path(os.environ.get("AF3_WORKSPACE", "/tmp/af3_workspace"))

    # ── 环境验证 ──────────────────────────────────────────────

    async def load_model(self) -> None:
        """验证 AF3 运行环境 (不加载 Python 模型, AF3 在 Docker 内运行)。

        环境不满足时抛出 RuntimeError，模板 lifespan 会捕获并将 _loaded 保持为
        False，从而 /health 正确返回 model_loaded: false。
        """
        self.logger.info("Checking AlphaFold3 environment …")

        checks: list[tuple[str, bool, str]] = []

        # 1. 操作系统
        ok, msg = _check_os()
        checks.append(("OS", ok, msg))

        # 2. NVIDIA GPU
        if ok:
            ok_gpu, msg_gpu = _check_nvidia_gpu()
            checks.append(("GPU", ok_gpu, msg_gpu))
        else:
            checks.append(("GPU", False, "Skipped (OS check failed)"))

        # 3. Docker
        ok_docker, msg_docker = _check_docker()
        checks.append(("Docker", ok_docker, msg_docker))

        # 4. nvidia-container-toolkit
        if ok_docker:
            ok_nct, msg_nct = _check_nvidia_container_toolkit()
            checks.append(("nvidia-ctk", ok_nct, msg_nct))
        else:
            checks.append(("nvidia-ctk", False, "Skipped (Docker not available)"))

        # 5. AF3 镜像
        if ok_docker:
            ok_img, msg_img = _check_af3_image(self._af3_image)
            checks.append(("AF3 image", ok_img, msg_img))
        else:
            checks.append(("AF3 image", False, "Skipped (Docker not available)"))

        # 6. 模型和数据库目录
        ok_dirs, msg_dirs = _check_required_dirs(self._model_dir, self._database_dir)
        checks.append(("Data dirs", ok_dirs, msg_dirs))

        # 打印检查结果
        failures: list[str] = []
        for name, ok, msg in checks:
            status = "✓" if ok else "✗"
            self.logger.info("  [%s] %s: %s", status, name, msg)
            if not ok:
                failures.append(f"{name}: {msg}")

        if not failures:
            self._ready_message = "AlphaFold3 ready — Docker + GPU + image verified"
            self._system_info = detect_system()
            self._model_status = {
                "status": "ready",
                "runtime": "Docker (alphafold3 image)",
                "checks": {name: msg for name, _ok, msg in checks},
            }
            self.logger.info("%s", self._ready_message)
            return

        self._ready_message = (
            f"AlphaFold3 NOT available on this machine. "
            f"Failed checks: {'; '.join(failures)}"
        )
        self.logger.warning("%s", self._ready_message)
        raise RuntimeError(self._ready_message)

    # ── 结构预测 ──────────────────────────────────────────────

    async def predict_structure(self, sequence: str) -> StructureResult:
        """对一条氨基酸序列运行 AlphaFold3 结构预测。

        1. 创建临时工作目录
        2. 生成 AF3 输入 JSON
        3. 调用 docker run alphafold3 ...
        4. 解析输出 mmCIF + 置信度
        5. 清理工作目录
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

        job_id = uuid.uuid4().hex[:12]
        job_name = f"igem_silk_{job_id}"
        workspace = self._workspace_base / job_name
        workspace.mkdir(parents=True, exist_ok=True)

        input_dir = workspace / "input"
        output_dir = workspace / "output"
        input_dir.mkdir(exist_ok=True)
        output_dir.mkdir(exist_ok=True)

        try:
            # 1. 写入 AF3 输入 JSON
            input_json = {
                "name": job_name,
                "modelSeeds": [1],
                "sequences": [
                    {
                        "protein": {
                            "id": "A",
                            "sequence": sequence,
                        }
                    }
                ],
                "dialect": "alphafold3",
                "version": 3,
            }
            input_path = input_dir / f"{job_name}.json"
            input_path.write_text(json.dumps(input_json, indent=2))

            # 2. 运行 AF3 Docker
            cmd = [
                "docker", "run", "--rm",
                "--gpus", "all",
                "--volume", f"{input_dir}:/root/af_input",
                "--volume", f"{output_dir}:/root/af_output",
                "--volume", f"{self._model_host_dir}:/root/models",
                "--volume", f"{self._database_host_dir}:/root/public_databases",
                self._af3_image,
                "python", "run_alphafold.py",
                "--json_path", f"/root/af_input/{job_name}.json",
                "--model_dir", "/root/models",
                "--output_dir", "/root/af_output",
            ]

            self.logger.info("Running AF3 for %s (sequence length=%d) …",
                              job_name, len(sequence))

            proc = await _run_subprocess(cmd, timeout=14400, logger=self.logger)

            if proc.returncode != 0:
                error_msg = proc.stderr[-2000:] if proc.stderr else f"exit code {proc.returncode}"
                return StructureResult(
                    sequence=sequence,
                    pdb_content="",
                    confidence=None,
                    details={
                        "error": f"AlphaFold3 failed: {error_msg}",
                        "job_name": job_name,
                        "returncode": proc.returncode,
                    },
                )

            # 3. 解析输出
            # AF3 输出位于 output_dir/<job_name>/
            af3_output_dir = output_dir / job_name
            if not af3_output_dir.exists():
                return StructureResult(
                    sequence=sequence,
                    pdb_content="",
                    confidence=None,
                    details={
                        "error": f"AF3 output directory not found: {af3_output_dir}",
                        "job_name": job_name,
                    },
                )

            # 读取排名最高的 mmCIF 文件
            top_cif_path = af3_output_dir / f"{job_name}_model.cif"
            cif_content = ""
            if top_cif_path.exists():
                cif_content = top_cif_path.read_text()

            # 读取置信度
            summary_path = af3_output_dir / f"{job_name}_summary_confidences.json"
            confidence = None
            conf_details: dict[str, Any] = {}
            if summary_path.exists():
                conf_data = json.loads(summary_path.read_text())
                confidence = conf_data.get("ranking_score")
                conf_details = {
                    "ptm": conf_data.get("ptm"),
                    "iptm": conf_data.get("iptm"),
                    "fraction_disordered": conf_data.get("fraction_disordered"),
                    "has_clash": conf_data.get("has_clash"),
                    "ranking_score": conf_data.get("ranking_score"),
                    "chain_ptm": conf_data.get("chain_ptm"),
                    "chain_iptm": conf_data.get("chain_iptm"),
                }

            # 收集所有模型文件列表
            model_files = sorted(
                [p.name for p in af3_output_dir.glob("*.cif")]
            )

            return StructureResult(
                sequence=sequence,
                pdb_content=cif_content,
                confidence=confidence,
                details={
                    "format": "mmcif",
                    "job_name": job_name,
                    "model_files": model_files,
                    "confidence_metrics": conf_details,
                    "output_dir": str(af3_output_dir) if self._keep_workspace else None,
                },
            )

        except subprocess.TimeoutExpired:
            return StructureResult(
                sequence=sequence,
                pdb_content="",
                confidence=None,
                details={
                    "error": "AlphaFold3 prediction timed out (14400s limit)",
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

    # ── 批量预测 (逐条处理) ───────────────────────────────────

    async def predict_batch(
        self, request: BatchPredictRequest
    ) -> StructureBatchPredictResponse:
        """批量结构预测 — 逐条处理，每次只跑一个 AF3 任务。

        AlphaFold3 极慢 (每个序列数分钟到数十分钟)，并发无意义。
        """
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
            results.append(result)

        return StructureBatchPredictResponse(
            success=True,
            results=results,
            total=len(results),
            error=None,
        )

    # ── 单序列预测 (覆盖以加入 ready 检查) ────────────────────

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


# ── 异步 subprocess ──────────────────────────────────────────────

async def _run_subprocess(cmd: list[str], timeout: int = 14400, logger=None):
    """异步运行子进程，实时流式输出 stdout/stderr 到 logger。

    使用 asyncio.create_subprocess_exec 逐行读取输出并转发到 logger，
    同时累积完整输出用于错误报告。兼容 .returncode / .stdout / .stderr 访问。
    """
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
                _stream(process.stdout, "AF3-out", stdout_lines),
                _stream(process.stderr, "AF3", stderr_lines),
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        raise subprocess.TimeoutExpired(cmd, timeout)

    await process.wait()

    return subprocess.CompletedProcess(
        cmd, process.returncode or 0,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
    )


# ═══════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("PORT", "8201"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    logger = get_logger("alphafold3")
    app = create_app(AlphaFold3Service, enable_async=True)
    logger.info("Starting on %s:%s", HOST, PORT)
    logger.info("Async job endpoints enabled: /predict/async, /status/{id}, /result/{id}, /jobs, DELETE /jobs/{id}")
    uvicorn.run(app, host=HOST, port=PORT)
