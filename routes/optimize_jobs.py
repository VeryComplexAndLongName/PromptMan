from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException
from loguru import logger

from routes.optimize_prompt import build_prompt_optimize_response
from routes.shared import get_personal_config
from schemas import PromptData, PromptOptimizeJobOut


def _build_job_response(snapshot: dict) -> PromptOptimizeJobOut:
    result = snapshot.get("result")
    return PromptOptimizeJobOut(
        job_id=str(snapshot.get("job_id") or ""),
        status=str(snapshot.get("status") or "failed"),
        created_at=snapshot.get("created_at"),
        started_at=snapshot.get("started_at"),
        completed_at=snapshot.get("completed_at"),
        cancelled_at=snapshot.get("cancelled_at"),
        error=snapshot.get("error"),
        result=build_prompt_optimize_response(result) if result is not None else None,
        can_cancel=bool(snapshot.get("can_cancel")),
    )


def create_optimize_job_route(data: PromptData, db, current_user, job_creator: Callable[..., dict]) -> PromptOptimizeJobOut:  # type: ignore[no-untyped-def]
    logger.info("optimize.job.request.start user_id={}", current_user.id)
    snapshot = job_creator(current_user.id, data.model_dump(), get_personal_config(db, current_user))
    return _build_job_response(snapshot)


def get_optimize_job_route(job_id: str, current_user, job_getter: Callable[..., dict]) -> PromptOptimizeJobOut:  # type: ignore[no-untyped-def]
    try:
        snapshot = job_getter(job_id, current_user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Optimization job not found.") from exc
    return _build_job_response(snapshot)


def cancel_optimize_job_route(job_id: str, current_user, job_canceller: Callable[..., dict]) -> PromptOptimizeJobOut:  # type: ignore[no-untyped-def]
    logger.info("optimize.job.request.cancel job_id={} user_id={}", job_id, current_user.id)
    try:
        snapshot = job_canceller(job_id, current_user.id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Optimization job not found.") from exc
    return _build_job_response(snapshot)
