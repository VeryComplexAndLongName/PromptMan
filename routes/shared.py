import datetime
from typing import Any, cast

from sqlalchemy.orm import Session

import auth as auth_service
import crud
from cache.shared_cache import (
    PROMPT_CACHE_PREFIX,
    build_prompt_response_cache_key,
    clear_shared_cache,
    delete_shared_cache_entry,
)
from database import run_db_call
from models import Prompt, User
from schemas import ProjectOut, PromptOut, PromptVersionOut, UserOut


def to_user_out(user: User) -> UserOut:
    return UserOut(**auth_service.user_to_dict(user))


def to_project_out(project: Any) -> ProjectOut:
    return ProjectOut(id=project.id, name=project.name)


def get_personal_config(db: Session, current_user: User) -> dict[str, Any]:
    config = run_db_call(db, auth_service.get_or_create_personal_config, current_user)
    return auth_service.serialize_optimizer_config(config)


def allowed_projects(current_user: User) -> list[str] | None:
    return auth_service.allowed_projects_for_user(current_user)


def normalize_utc_datetime(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.UTC)
    return value.astimezone(datetime.UTC)


def require_utc_datetime(value: datetime.datetime | None) -> datetime.datetime:
    normalized = normalize_utc_datetime(value)
    if normalized is None:
        raise ValueError("Expected datetime value")
    return normalized


def to_prompt_out(db: Session, prompt: Prompt) -> PromptOut:
    latest = run_db_call(db, crud.get_latest_version, prompt.id)
    if not latest:
        raise ValueError(f"No version found for prompt {prompt.id}")
    return PromptOut(
        name=prompt.name,
        project=prompt.project,
        created_at=require_utc_datetime(cast("datetime.datetime | None", prompt.created_at)),
        updated_at=require_utc_datetime(cast("datetime.datetime | None", prompt.updated_at)),
        created_by_username=run_db_call(db, crud.resolve_audit_username, prompt.created_by_ref),
        updated_by_username=run_db_call(db, crud.resolve_audit_username, prompt.updated_by_ref),
        tags=[tag.name for tag in prompt.tags],
        latest_version=latest.version,
        role=latest.role,
        task=latest.task,
        context=latest.context,
        constraints=latest.constraints,
        output_format=latest.output_format,
        examples=latest.examples,
    )


def invalidate_prompt_cache(project: str, name: str) -> None:
    delete_shared_cache_entry(build_prompt_response_cache_key(project, name))
    clear_shared_cache(PROMPT_CACHE_PREFIX)


def to_prompt_version_out(db: Session, version: Any) -> PromptVersionOut:
    return PromptVersionOut(
        version=version.version,
        created_at=require_utc_datetime(cast("datetime.datetime | None", version.created_at)),
        created_by_username=run_db_call(db, crud.resolve_audit_username, version.created_by_ref),
        role=version.role,
        task=version.task,
        context=version.context,
        constraints=version.constraints,
        output_format=version.output_format,
        examples=version.examples,
    )
