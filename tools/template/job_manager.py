"""
Job Manager — 异步后台任务管理器。

供 structure_service 模板的 ``create_app(..., enable_async=True)`` 使用。
当前使用进程内 dict，可选 JSON 文件持久化。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


JOB_TTL_SECONDS = 86400  # 任务完成后默认保留 24 小时


@dataclass
class Job:
    """单个预测任务的完整状态。"""

    job_id: str
    sequence: str
    status: str = "pending"       # pending | running | success | failed
    progress: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    pdb_content: str = ""
    confidence: float | None = None
    details: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class JobManager:
    """进程内任务管理器。

    线程安全说明：当前假设所有操作在同一个事件循环中串行执行
    （FastAPI 路由 + 后台 task 都在同一 loop）。
    """

    def __init__(self, persist_path: str | None = None):
        self._jobs: dict[str, Job] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path and self._persist_path.exists():
            self._load()
            self._cleanup_expired()

    def create(self, job_id: str, sequence: str) -> Job:
        self._cleanup_expired()
        job = Job(job_id=job_id, sequence=sequence)
        self._jobs[job_id] = job
        self._save()
        return job

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: str | None = None,
        pdb_content: str | None = None,
        confidence: float | None = None,
        details: dict | None = None,
        error: str | None = None,
    ) -> Job | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if status is not None:
            job.status = status
            if status in ("success", "failed"):
                job.finished_at = time.time()
        if progress is not None:
            job.progress = progress
        if pdb_content is not None:
            job.pdb_content = pdb_content
        if confidence is not None:
            job.confidence = confidence
        if details is not None:
            job.details = details
        if error is not None:
            job.error = error
        self._save()
        return job

    def get(self, job_id: str) -> Job | None:
        self._cleanup_expired()
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[dict]:
        return [
            {
                "job_id": j.job_id,
                "status": j.status,
                "progress": j.progress,
                "created_at": j.created_at,
                "finished_at": j.finished_at,
            }
            for j in self._jobs.values()
        ]

    def delete(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save()
            return True
        return False

    # ── 持久化 ──────────────────────────────────────────────

    def _save(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {j.job_id: asdict(j) for j in self._jobs.values()}
        self._persist_path.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        try:
            data = json.loads(self._persist_path.read_text())
            for job_id, d in data.items():
                d["created_at"] = d.get("created_at", 0.0)
                d["finished_at"] = d.get("finished_at")
                self._jobs[job_id] = Job(**d)
        except Exception:
            pass

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [
            jid
            for jid, j in self._jobs.items()
            if j.finished_at and (now - j.finished_at) > JOB_TTL_SECONDS
        ]
        for jid in expired:
            del self._jobs[jid]
        if expired:
            self._save()
