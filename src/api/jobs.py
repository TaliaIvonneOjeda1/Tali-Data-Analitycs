"""Jobs en memoria + disco bajo outputs/jobs/{id}/."""

from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from src.config import JOBS_DIR

_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}
_pool = ThreadPoolExecutor(max_workers=2)


def _job_dir(job_id: str) -> Path:
    d = JOBS_DIR / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_job(kind: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "kind": kind,
            "status": "queued",
            "progress": [],
            "result": None,
            "error": None,
        }
    _job_dir(job_id)
    return job_id


def get_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def append_progress(job_id: str, event: dict[str, Any]) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["progress"].append(event)
        if job["status"] == "queued":
            job["status"] = "running"


def set_result(job_id: str, result: dict[str, Any]) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["result"] = result
        job["status"] = "done"
    path = _job_dir(job_id) / "result.json"
    path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def set_error(job_id: str, error: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["error"] = error
        job["status"] = "error"


def submit(job_id: str, fn: Callable[[], None]) -> None:
    def _wrap() -> None:
        try:
            append_progress(job_id, {"phase": "start"})
            fn()
        except Exception as exc:  # noqa: BLE001
            set_error(job_id, str(exc))

    _pool.submit(_wrap)


def artifact_path(job_id: str, name: str) -> Path | None:
    from src.security.paths import sanitize_filename

    safe = sanitize_filename(name)
    # buscar en job dir y outputs raíz
    for base in (_job_dir(job_id), JOBS_DIR.parent):
        candidate = (base / safe).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None
