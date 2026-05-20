from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context
from queue import Empty
from threading import Lock
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from loguru import logger

from optimizer.result import OptimizationResult
from optimizer.service import optimize_prompt_with_active_backend

if TYPE_CHECKING:
    from collections.abc import Mapping


_JOB_RETENTION = timedelta(hours=1)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _run_optimization_job(
    fields: dict[str, str | None],
    config_override: dict[str, Any],
    result_queue: Any,
) -> None:
    started_at = _utcnow()
    try:
        result = optimize_prompt_with_active_backend(fields, config_override)
        completed_at = _utcnow()
        result_queue.put(
            {
                "status": "completed",
                "result": result,
                "started_at": started_at,
                "completed_at": completed_at,
            }
        )
    except Exception as exc:  # pragma: no cover - child-process safeguard
        logger.exception("optimize.job.worker.error")
        completed_at = _utcnow()
        result_queue.put(
            {
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "started_at": started_at,
                "completed_at": completed_at,
            }
        )


@dataclass
class OptimizationJobRecord:
    job_id: str
    user_id: int
    process: Any
    result_queue: Any
    status: str
    created_at: datetime
    started_at: datetime
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    error: str | None = None
    result: OptimizationResult | None = None


class OptimizationJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, OptimizationJobRecord] = {}
        self._lock = Lock()

    def create_job(self, user_id: int, fields: Mapping[str, str | None], config_override: Mapping[str, Any]) -> dict[str, Any]:
        context = get_context("spawn")
        result_queue = context.Queue(maxsize=1)
        job_id = str(uuid4())
        process = context.Process(
            target=_run_optimization_job,
            args=(dict(fields), dict(config_override), result_queue),
            daemon=True,
            name=f"promptman-opt-{job_id[:8]}",
        )
        now = _utcnow()
        record = OptimizationJobRecord(
            job_id=job_id,
            user_id=user_id,
            process=process,
            result_queue=result_queue,
            status="running",
            created_at=now,
            started_at=now,
        )
        with self._lock:
            self._prune_finished_jobs_unlocked()
            self._jobs[job_id] = record
            process.start()
            logger.info("optimize.job.created job_id={} user_id={}", job_id, user_id)
            return self._snapshot_unlocked(record)

    def get_job(self, job_id: str, user_id: int) -> dict[str, Any]:
        with self._lock:
            record = self._get_owned_job_unlocked(job_id, user_id)
            self._sync_job_unlocked(record)
            return self._snapshot_unlocked(record)

    def cancel_job(self, job_id: str, user_id: int) -> dict[str, Any]:
        with self._lock:
            record = self._get_owned_job_unlocked(job_id, user_id)
            self._sync_job_unlocked(record)
            if record.status not in {"completed", "failed", "cancelled"}:
                if record.process.is_alive():
                    record.process.terminate()
                    record.process.join(timeout=1)
                now = _utcnow()
                record.status = "cancelled"
                record.cancelled_at = now
                record.completed_at = now
                record.error = "Optimization cancelled by user."
                logger.info("optimize.job.cancelled job_id={} user_id={}", job_id, user_id)
            return self._snapshot_unlocked(record)

    def _get_owned_job_unlocked(self, job_id: str, user_id: int) -> OptimizationJobRecord:
        record = self._jobs.get(job_id)
        if record is None or record.user_id != user_id:
            raise KeyError(job_id)
        return record

    def _prune_finished_jobs_unlocked(self) -> None:
        cutoff = _utcnow() - _JOB_RETENTION
        stale = [
            job_id
            for job_id, record in self._jobs.items()
            if record.completed_at is not None and record.completed_at < cutoff
        ]
        for job_id in stale:
            self._jobs.pop(job_id, None)

    def _sync_job_unlocked(self, record: OptimizationJobRecord) -> None:
        if record.status in {"completed", "failed", "cancelled"}:
            return

        try:
            payload = record.result_queue.get_nowait()
        except Empty:
            if not record.process.is_alive() and record.process.exitcode not in (None, 0):
                record.status = "failed"
                record.completed_at = _utcnow()
                record.error = f"Optimization worker exited unexpectedly (exitcode={record.process.exitcode})."
            return

        status = str(payload.get("status") or "failed")
        payload_started_at = payload.get("started_at")
        if isinstance(payload_started_at, datetime):
            record.started_at = payload_started_at
        payload_completed_at = payload.get("completed_at")
        if isinstance(payload_completed_at, datetime):
            record.completed_at = payload_completed_at
        else:
            record.completed_at = _utcnow()
        if status == "completed":
            record.status = "completed"
            result = payload.get("result")
            if isinstance(result, OptimizationResult):
                record.result = result
            else:
                record.status = "failed"
                record.error = "Optimization worker returned an invalid result payload."
        else:
            record.status = "failed"
            record.error = str(payload.get("error") or "Optimization worker failed.")

        if record.process.is_alive():
            record.process.join(timeout=0.1)

    def _snapshot_unlocked(self, record: OptimizationJobRecord) -> dict[str, Any]:
        return {
            "job_id": record.job_id,
            "status": record.status,
            "created_at": record.created_at,
            "started_at": record.started_at,
            "completed_at": record.completed_at,
            "cancelled_at": record.cancelled_at,
            "error": record.error,
            "result": record.result,
            "can_cancel": record.status == "running",
        }


_OPTIMIZATION_JOB_MANAGER = OptimizationJobManager()


def create_optimization_job(user_id: int, fields: Mapping[str, str | None], config_override: Mapping[str, Any]) -> dict[str, Any]:
    return _OPTIMIZATION_JOB_MANAGER.create_job(user_id, fields, config_override)


def get_optimization_job(job_id: str, user_id: int) -> dict[str, Any]:
    return _OPTIMIZATION_JOB_MANAGER.get_job(job_id, user_id)


def cancel_optimization_job(job_id: str, user_id: int) -> dict[str, Any]:
    return _OPTIMIZATION_JOB_MANAGER.cancel_job(job_id, user_id)
