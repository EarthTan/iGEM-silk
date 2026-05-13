"""
Waveflow — Tamarind.bio API 包装微服务
=======================================

将 tamarind.bio 的 REST API 包装为结构预测微服务。
工具类型在 URL 路径中指定，一个服务实例可代理多种远程模型。

用法::

    POST /predict/esmfold      # 使用 ESMFold 预测
    POST /predict/omegafold    # 使用 OmegaFold 预测
    POST /predict/alphafold    # 使用 AlphaFold2 预测
    POST /predict/batch/esmfold
    GET  /health

工作流程::

    POST /predict/{tool} → tamarind /submit-job → 轮询 /jobs → /result → 下载 PDB → 返回

API 端点:

    GET  /                         → 服务信息
    GET  /health                   → 健康检查
    POST /predict/{tool}           → 单序列结构预测（tool = esmfold / omegafold / alphafold ...）
    POST /predict                  → 同上，使用默认工具（WAVEFLOW_DEFAULT_TOOL, 默认 esmfold）
    POST /predict/batch/{tool}     → 批量结构预测
    POST /predict/batch            → 同上，使用默认工具
    POST /predict/async/{tool}     → 异步提交（立即返回 job_id）
    GET  /status/{job_id}          → 查询异步任务状态
    GET  /result/{job_id}          → 获取异步任务结果
    GET  /jobs                     → 列出所有异步任务
    DELETE /jobs/{job_id}          → 清理任务

环境变量:

    TAMARIND_API_KEY          (必需) API 密钥
    TAMARIND_BASE_URL         (默认: https://app.tamarind.bio/api)
    TAMARIND_POLL_INTERVAL    (默认: 15) 轮询间隔秒数
    TAMARIND_TIMEOUT          (默认: 3600) 最大等待秒数
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import time
import uuid
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).parent.parent.parent
import sys
sys.path.insert(0, str(PROJECT_ROOT))

from tools.template.structure_service import (
    StructureResult,
    PredictRequest,
    BatchPredictRequest,
    JobManager,
)
from tools.template.logger import get_logger
from tools.utils import detect_system


# ═══════════════════════════════════════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════


class HealthResponse(BaseModel):
    status: str
    tool_name: str = "waveflow"
    version: str = "1.0.0"
    model_loaded: bool
    model: dict | None = None
    system: dict | None = None


class StructurePredictResponse(BaseModel):
    success: bool
    peptide_id: str | None = None
    sequence: str | None = None
    result: StructureResult | None = None
    error: str | None = None


class StructureBatchPredictResponse(BaseModel):
    success: bool
    results: list[StructureResult]
    total: int
    error: str | None = None


class InfoResponse(BaseModel):
    tool_name: str = "waveflow"
    version: str = "1.0.0"
    description: str = "Waveflow — Tamarind.bio 云端结构预测代理"
    capabilities: list[str] = [
        "predict/{tool}", "predict/batch/{tool}", "predict/async/{tool}",
        "predict", "predict/batch",
    ]
    input_format: dict[str, str] = {"sequence": "string (amino acid sequence)"}
    output_format: dict[str, str] = {
        "pdb_content": "string (PDB format)",
        "confidence": "float 0-1 (from remote, may be null)",
    }
    recommended_batch_size: int = 10


class AsyncPredictResponse(BaseModel):
    job_id: str
    status_url: str
    status: str = "pending"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: str = ""
    created_at: float
    finished_at: float | None = None


class JobResultResponse(BaseModel):
    job_id: str
    sequence: str
    status: str
    pdb_content: str = ""
    confidence: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    error: str = ""


class JobListResponse(BaseModel):
    jobs: list[dict]


# ═══════════════════════════════════════════════════════════════════════════════
# Waveflow Service
# ═══════════════════════════════════════════════════════════════════════════════


# 每个请求的 tool 上下文（用于异步 Job 场景）
_current_tool: contextvars.ContextVar[str] = contextvars.ContextVar("current_tool")


class WaveflowService:
    """Tamarind.bio API 包装服务。

    不加载本地模型，将预测委托给远程 API。
    工具类型在 URL 路径中指定（如 /predict/esmfold），支持任意 tamarind 平台上的工具。
    """

    tool_name = "waveflow"
    version = "1.0.0"
    description = (
        "Waveflow — Tamarind.bio 云端结构预测代理. "
        "将预测委托给远程 API，无需本地 GPU/模型。"
    )
    recommended_batch_size = 10

    def __init__(self):
        self.logger = get_logger(self.tool_name)
        self._loaded = False
        self._lock = asyncio.Lock()
        self._model_status: dict | None = None
        self._system_info: dict | None = None

        # ── 配置 ────────────────────────────────────────────────
        self.api_key = os.environ.get("TAMARIND_API_KEY", "")
        self.base_url = os.environ.get(
            "TAMARIND_BASE_URL", "https://app.tamarind.bio/api/"
        ).rstrip("/") + "/"
        self.poll_interval = int(os.environ.get("TAMARIND_POLL_INTERVAL", "15"))
        self.timeout = int(os.environ.get("TAMARIND_TIMEOUT", "3600"))

        self._http_client: httpx.AsyncClient | None = None

    # ── 属性 ────────────────────────────────────────────────────

    @property
    def http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                headers={"x-api-key": self.api_key},
            )
        return self._http_client

    @property
    def tamarind_headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key}

    # ── 模型加载 ────────────────────────────────────────────────

    async def load_model(self) -> None:
        """验证 tamarind.bio API 可用性，不加载本地模型。"""
        self.logger.info(
            "Waveflow starting: api_url=%s", self.base_url,
        )

        if not self.api_key:
            msg = (
                "TAMARIND_API_KEY not set. "
                "Get your API key from https://app.tamarind.bio/api-docs/api-key "
                "or set the environment variable."
            )
            self.logger.error("%s", msg)
            raise RuntimeError(msg)

        # 验证 API key
        try:
            resp = await self.http_client.get(
                self.base_url + "tools",
                headers=self.tamarind_headers,
            )
            resp.raise_for_status()
            self.logger.info("Tamarind API auth OK: %s", resp.status_code)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                msg = "Tamarind API key rejected (401 Unauthorized)"
            elif e.response.status_code == 403:
                msg = "Tamarind API key rejected (403 Forbidden)"
            else:
                msg = f"Tamarind API auth failed: {e}"
            self.logger.error("%s", msg)
            raise RuntimeError(msg) from e
        except httpx.RequestError as e:
            msg = f"Tamarind API unreachable: {e}"
            self.logger.error("%s", msg)
            raise RuntimeError(msg) from e

        self._loaded = True
        self._model_status = {"api_base": self.base_url}
        self._system_info = detect_system() | {
            "description": "Remote API via tamarind.bio",
            "local_gpu": False,
            "network_required": True,
        }
        self.logger.info("Waveflow ready: %s", self.base_url)

    # ── Tamarind API 调用 ──────────────────────────────────────

    async def _submit_job(self, tool: str, sequence: str, job_name: str) -> str:
        payload = {
            "jobName": job_name,
            "type": tool,
            "settings": {"sequence": sequence},
        }
        self.logger.info("Submit job: %s tool=%s seq_len=%d", job_name, tool, len(sequence))
        resp = await self.http_client.post(
            self.base_url + "submit-job",
            headers=self.tamarind_headers,
            json=payload,
        )
        resp.raise_for_status()
        # tamarind 返回字符串如 "test_job submitted to queue."
        text = resp.text.strip().strip('"')
        self.logger.info("Submit response: %s", text[:100])
        return text

    async def _submit_batch(
        self, tool: str, sequences: list[tuple[str, str]],
    ) -> dict[str, Any]:
        batch_name = f"waveflow_{uuid.uuid4().hex[:8]}"
        jobs = [
            {"jobName": name, "settings": {"sequence": seq}}
            for name, seq in sequences
        ]
        payload = {
            "tool": tool,
            "batchName": batch_name,
            "jobs": jobs,
        }
        self.logger.info("Submit batch: %s tool=%s (%d jobs)", batch_name, tool, len(jobs))
        resp = await self.http_client.post(
            self.base_url + "submit-batch",
            headers=self.tamarind_headers,
            json=payload,
        )
        resp.raise_for_status()
        # tamarind submit-batch 可能返回字符串，统一用 text 避免 JSON 解析异常
        return resp.text

    async def _poll_job(self, job_name: str) -> dict[str, Any]:
        """轮询 tamarind GET /jobs 直到任务完成。

        tamarind 响应格式:
            {"0": {"JobName": "...", "JobStatus": "Complete|Running|In Queue", ...},
             "statuses": {"Complete": 0, "In Queue": 1, "Running": 0, ...}}
        """
        start_time = time.time()
        last_status = "submitted"

        while True:
            elapsed = time.time() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(f"Job {job_name} timed out after {self.timeout}s")

            resp = await self.http_client.get(
                self.base_url + "jobs",
                headers=self.tamarind_headers,
                params={"jobName": job_name},
            )
            resp.raise_for_status()
            data = resp.json()

            # 在编号条目中查找目标 job（如 "0": {"JobName": "...", "JobStatus": "..."}）
            job_status = None
            if isinstance(data, dict):
                for key, entry in data.items():
                    if isinstance(entry, dict) and entry.get("JobName") == job_name:
                        job_status = entry.get("JobStatus", "")
                        break

            if job_status is None:
                await asyncio.sleep(self.poll_interval)
                continue

            if job_status != last_status:
                self.logger.info("Job %s: %s -> %s (%.0fs)", job_name, last_status, job_status, elapsed)
                last_status = job_status

            if job_status == "Complete":
                return data
            if job_status in ("Failed", "Error", "Stopped"):
                raise RuntimeError(f"Job {job_name} failed with status: {job_status}")

            await asyncio.sleep(self.poll_interval)

    async def _download_result(self, job_name: str) -> dict[str, Any]:
        """从 tamarind /result 获取下载 URL，下载 ZIP 包并提取 PDB。

        tamarind /result 返回一个带引号的 URL 字符串:
            "https://downloads.tamarind.bio/.../result-{job_name}.zip"

        ZIP 内包含: model.pdb, output.log, metrics.csv, metrics.parquet, ...
        """
        self.logger.info("Fetching result URL for job: %s", job_name)
        resp = await self.http_client.post(
            self.base_url + "result",
            headers=self.tamarind_headers,
            json={"jobName": job_name},
        )
        resp.raise_for_status()

        # /result 返回形如 '"https://..."' 的 JSON 字符串
        raw_text = resp.text.strip()
        download_url = raw_text.strip('"')

        if not download_url.startswith("http"):
            self.logger.warning("No presigned URL in /result response: %s", raw_text[:200])
            return {"raw": raw_text}

        self.logger.info("Downloading result ZIP from: %s", download_url[:80])
        dl_resp = await self.http_client.get(download_url)
        dl_resp.raise_for_status()
        zip_bytes = dl_resp.content

        return {"url": download_url, "zip_bytes": zip_bytes}

    def _extract_pdb(self, result: dict[str, Any]) -> str | None:
        """从下载结果中提取 PDB 内容。

        处理两种格式:
        1. ZIP 包 → 解压后读取 model.pdb
        2. 原始文本 → 按 PDB 格式解析
        """
        zip_bytes = result.get("zip_bytes")
        if zip_bytes:
            import io
            import zipfile
            try:
                z = zipfile.ZipFile(io.BytesIO(zip_bytes))
                # 查找 model.pdb 或 .pdb 文件
                for name in z.namelist():
                    if name.endswith(".pdb"):
                        pdb_text = z.read(name).decode("utf-8")
                        self.logger.info("Extracted PDB from ZIP: %s (%d bytes)", name, len(pdb_text))
                        return pdb_text
                self.logger.warning("No .pdb file found in ZIP: %s", z.namelist())
            except zipfile.BadZipFile:
                self.logger.warning("Result is not a valid ZIP file")

        # 原始文本回退
        content = result.get("content", "")
        raw = result.get("raw", "")
        text = content or raw

        if not text:
            return None

        if "ATOM" in text and ("END" in text or "MODEL" in text):
            lines = text.splitlines()
            pdb_lines = [
                l for l in lines
                if l.startswith(("ATOM  ", "HETATM", "TER", "END", "MODEL", "PARENT"))
            ]
            if pdb_lines:
                return "\n".join(pdb_lines)

        # 非 PDB 文本不应冒充成功结果
        return None

    # ── 核心预测方法 ──────────────────────────────────────────

    async def predict_structure(self, tool: str, sequence: str) -> StructureResult:
        if not self._loaded:
            return StructureResult(
                sequence=sequence, pdb_content="", confidence=None,
                details={"error": "Service not initialized. Check TAMARIND_API_KEY."},
            )

        job_name = f"waveflow_{tool}_{uuid.uuid4().hex[:12]}"
        start_time = time.time()

        try:
            await self._submit_job(tool, sequence, job_name)
            await self._poll_job(job_name)
            dl_result = await self._download_result(job_name)
            pdb_content = self._extract_pdb(dl_result)
            elapsed = time.time() - start_time

            if pdb_content:
                self.logger.info("Job %s done: pdb_len=%d (%.0fs)", job_name, len(pdb_content), elapsed)
                return StructureResult(
                    sequence=sequence, pdb_content=pdb_content, confidence=None,
                    details={
                        "tool_type": tool, "job_name": job_name,
                        "elapsed_seconds": round(elapsed, 1),
                        "sequence_length": len(sequence),
                    },
                )
            else:
                return StructureResult(
                    sequence=sequence, pdb_content="", confidence=None,
                    details={
                        "error": "No PDB structure in result",
                        "tool_type": tool, "job_name": job_name,
                        "raw_response_preview": str(dl_result.get("content", ""))[:500],
                    },
                )
        except Exception as exc:
            elapsed = time.time() - start_time
            self.logger.error("Job %s failed after %.0fs: %s", job_name, elapsed, exc)
            return StructureResult(
                sequence=sequence, pdb_content="", confidence=None,
                details={
                    "error": str(exc), "tool_type": tool,
                    "job_name": job_name, "elapsed_seconds": round(elapsed, 1),
                },
            )

    async def predict_batch(self, tool: str, sequences: list[PredictRequest]) -> list[StructureResult]:
        if not self._loaded:
            return [
                StructureResult(
                    sequence=s.sequence, pdb_content="", confidence=None,
                    details={"error": "Service not initialized"},
                )
                for s in sequences
            ]

        seq_list = [(f"waveflow_{tool}_{uuid.uuid4().hex[:12]}", s.sequence) for s in sequences]

        try:
            await self._submit_batch(tool, seq_list)

            async def poll_one(name: str) -> None:
                await self._poll_job(name)

            await asyncio.gather(*[poll_one(name) for name, _ in seq_list])

            async def download_one(name: str, seq: str) -> StructureResult:
                try:
                    dl = await self._download_result(name)
                    pdb = self._extract_pdb(dl)
                    return StructureResult(
                        sequence=seq, pdb_content=pdb or "", confidence=None,
                        details={
                            "tool_type": tool, "job_name": name,
                        } if pdb else {
                            "error": "No PDB in result",
                            "tool_type": tool, "job_name": name,
                        },
                    )
                except Exception as e:
                    return StructureResult(
                        sequence=seq, pdb_content="", confidence=None,
                        details={"error": str(e), "tool_type": tool, "job_name": name},
                    )

            results = await asyncio.gather(*[download_one(name, seq) for name, seq in seq_list])
            for i, item in enumerate(sequences):
                if i < len(results):
                    results[i].peptide_id = item.peptide_id or f"batch_{i}"
            return results

        except Exception as exc:
            return [
                StructureResult(
                    sequence=s.sequence, pdb_content="", confidence=None,
                    details={"error": str(exc)},
                )
                for s in sequences
            ]


# ═══════════════════════════════════════════════════════════════════════════════
# FastAPI 应用工厂
# ═══════════════════════════════════════════════════════════════════════════════


def create_app() -> FastAPI:
    svc = WaveflowService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc.logger.info("Starting service ...")
        api_key_set = bool(svc.api_key)
        svc.logger.info("Waveflow: api_key=%s", "SET" if api_key_set else "NOT SET")
        try:
            await svc.load_model()
            svc._loaded = True
            svc.logger.info("Tamarind API connected")
        except Exception as e:
            svc.logger.error("Failed to initialize: %s", e)
        yield
        svc.logger.info("Shutdown")

    app = FastAPI(
        title="waveflow",
        description="Waveflow — Tamarind.bio API 代理: 在 URL 路径中指定工具类型",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ── 辅助函数 ───────────────────────────────────────────

    async def _predict_single(tool: str, request: PredictRequest) -> StructurePredictResponse:
        pid = request.peptide_id or "unknown"
        svc.logger.info("Predict: tool=%s seq=%s len=%d", tool, pid, len(request.sequence))
        t0 = time.time()
        result = await svc.predict_structure(tool, request.sequence)
        result.peptide_id = request.peptide_id or "unknown"
        result.sequence = request.sequence
        elapsed = time.time() - t0
        if result.pdb_content:
            svc.logger.info("Predict done: %s tool=%s (%.2fs)", pid, tool, elapsed)
        else:
            svc.logger.warning("Predict failed: %s tool=%s (%.2fs)", pid, tool, elapsed)
        return StructurePredictResponse(
            success=bool(result.pdb_content),
            peptide_id=result.peptide_id,
            sequence=result.sequence,
            result=result,
            error=result.details.get("error") if not result.pdb_content else None,
        )

    async def _predict_batch(tool: str, request: BatchPredictRequest) -> StructureBatchPredictResponse:
        n = len(request.sequences)
        svc.logger.info("Batch predict: tool=%s n=%d", tool, n)
        t0 = time.time()
        results = await svc.predict_batch(tool, request.sequences)
        elapsed = time.time() - t0
        valid = [r for r in results if r.pdb_content]
        svc.logger.info("Batch predict done: tool=%s %d/%d (%.2fs)", tool, len(valid), n, elapsed)
        return StructureBatchPredictResponse(
            success=True,
            results=results,
            total=len(valid),
            error=None if len(valid) == n else f"{len(valid)}/{n} succeeded",
        )

    # ── 路由 ──────────────────────────────────────────────

    @app.get("/")
    async def root():
        return {"service": svc.tool_name, "version": svc.version, "docs": "/docs"}

    @app.get("/health", response_model=HealthResponse)
    async def health():
        return HealthResponse(
            status="healthy" if svc._loaded else "loading",
            model_loaded=svc._loaded,
            model=svc._model_status,
            system=svc._system_info,
        )

    @app.get("/info", response_model=InfoResponse)
    async def info():
        return InfoResponse()

    # ── 按工具类型预测 ────────────────────────────────

    _default_tool = os.environ.get("WAVEFLOW_DEFAULT_TOOL", "esmfold")

    @app.post("/predict/{tool}", response_model=StructurePredictResponse)
    async def predict_with_tool(tool: str, request: PredictRequest):
        """单序列结构预测，工具类型在 URL 路径中指定。

        curl -X POST http://localhost:8205/predict/esmfold \\
          -H 'Content-Type: application/json' \\
          -d '{"sequence": "MGRGGSGGYGGLGGQGGYGGLGSGGY"}'
        """
        return await _predict_single(tool, request)

    @app.post("/predict", response_model=StructurePredictResponse)
    async def predict_default(request: PredictRequest):
        """兼容路由：使用默认工具 (esmfold) 预测。"""
        return await _predict_single(_default_tool, request)

    @app.post("/predict/batch/{tool}", response_model=StructureBatchPredictResponse)
    async def predict_batch_with_tool(tool: str, request: BatchPredictRequest):
        """批量结构预测，工具类型在 URL 路径中指定。"""
        return await _predict_batch(tool, request)

    @app.post("/predict/batch", response_model=StructureBatchPredictResponse)
    async def predict_batch_default(request: BatchPredictRequest):
        """兼容路由：使用默认工具 (esmfold) 批量预测。"""
        return await _predict_batch(_default_tool, request)

    # ── 异步 Job 模式 ────────────────────────────────

    persist_path = os.environ.get("JOBS_FILE")
    job_manager_kwargs = {}
    if persist_path:
        job_manager_kwargs["persist_path"] = persist_path
    job_manager = JobManager(**job_manager_kwargs)

    @app.post("/predict/async/{tool}", status_code=202, response_model=AsyncPredictResponse)
    async def predict_async(tool: str, request: PredictRequest):
        """提交异步预测任务，工具类型在 URL 路径中指定。"""
        job_id = uuid.uuid4().hex[:12]
        job_manager.create(job_id, request.sequence)
        asyncio.create_task(_run_job(job_id, tool, request.sequence))
        svc.logger.info(
            "Async predict: %s tool=%s job=%s seq_len=%d",
            request.peptide_id or "unknown", tool, job_id, len(request.sequence),
        )
        return AsyncPredictResponse(
            job_id=job_id,
            status_url=f"/status/{job_id}",
            status="pending",
        )

    async def _run_job(job_id: str, tool: str, sequence: str) -> None:
        svc.logger.info("Job %s: started tool=%s seq_len=%d", job_id, tool, len(sequence))
        job = job_manager.get(job_id)
        try:
            job_manager.update(job_id, status="running", progress="Submitting to tamarind ...")
            result = await svc.predict_structure(tool, sequence)
            if result.pdb_content:
                job_manager.update(
                    job_id, status="success", progress="Completed",
                    pdb_content=result.pdb_content,
                    confidence=result.confidence,
                    details=result.details,
                )
            else:
                err = result.details.get("error", "Unknown error")
                job_manager.update(job_id, status="failed", progress=f"Failed: {err}", error=err)
        except Exception as exc:
            job_manager.update(job_id, status="failed", progress=f"Exception: {exc}", error=str(exc))
            svc.logger.error("Job %s: exception — %s", job_id, exc)

    @app.get("/status")
    async def list_running_jobs():
        running = [
            j for j in job_manager.list_jobs()
            if j["status"] in ("pending", "running")
        ]
        return {"jobs": running, "total": len(running)}

    @app.get("/status/{job_id}", response_model=JobStatusResponse)
    async def get_job_status(job_id: str):
        job = job_manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        return JobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            created_at=job.created_at,
            finished_at=job.finished_at,
        )

    @app.get("/result/{job_id}", response_model=JobResultResponse)
    async def get_job_result(job_id: str):
        job = job_manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        if job.status in ("pending", "running"):
            raise HTTPException(status_code=425, detail=f"Job {job_id!r} is still {job.status}")
        return JobResultResponse(
            job_id=job.job_id,
            sequence=job.sequence,
            status=job.status,
            pdb_content=job.pdb_content,
            confidence=job.confidence,
            details=job.details,
            error=job.error,
        )

    @app.get("/jobs", response_model=JobListResponse)
    async def list_jobs():
        return JobListResponse(jobs=job_manager.list_jobs())

    @app.delete("/jobs/{job_id}")
    async def delete_job(job_id: str):
        if not job_manager.delete(job_id):
            raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
        return {"deleted": job_id, "status": "ok"}

    return app


# ═══════════════════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    PORT = int(os.environ.get("PORT", "8205"))
    HOST = os.environ.get("HOST", "0.0.0.0")

    logger = get_logger("waveflow")
    api_key_set = bool(os.environ.get("TAMARIND_API_KEY"))
    logger.info("Waveflow starting: api_key=%s port=%s", "SET" if api_key_set else "NOT SET", PORT)

    app = create_app()
    logger.info("Routes: /predict/{tool}, /predict/batch/{tool}, /predict/async/{tool}")
    uvicorn.run(app, host=HOST, port=PORT)
