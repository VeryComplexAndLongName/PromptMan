from fastapi import Response
from sqlalchemy.orm import Session

import auth as auth_service
import crud
from cache.shared_cache import (
    PROMPT_CACHE_TTL_SECONDS,
    build_prompt_collection_cache_key,
    cache_get_or_set,
)
from database import run_db_call
from models import User
from routes.shared import allowed_projects, to_prompt_out
from schemas import PromptOut


def list_prompts_route(
    response: Response,
    project: str | None,
    tag: str | None,
    limit: str | None,
    offset: str | None,
    db: Session,
    current_user: User,
) -> list[PromptOut]:
    limit_int: int | None = None
    offset_int: int | None = None
    try:
        if limit:
            limit_int = int(limit)
            if limit_int < 1:
                limit_int = 1
    except (ValueError, TypeError):
        limit_int = None

    try:
        if offset:
            offset_int = int(offset)
            if offset_int < 0:
                offset_int = 0
    except (ValueError, TypeError):
        offset_int = None

    if project is not None:
        auth_service.ensure_project_access(current_user, project)
    user_allowed_projects = allowed_projects(current_user)
    cache_key = build_prompt_collection_cache_key(
        route="prompts.list",
        project=project,
        tag=tag,
        limit=limit_int,
        offset=offset_int,
        allowed_projects=user_allowed_projects,
    )

    def _load_list() -> dict[str, object]:
        total_count = run_db_call(db, crud.count_prompts, project=project, tag=tag, allowed_projects=user_allowed_projects)
        prompts = run_db_call(db, crud.list_prompts, project=project, tag=tag, limit=limit_int, offset=offset_int, allowed_projects=user_allowed_projects)
        return {
            "total_count": total_count,
            "prompts": [to_prompt_out(db, prompt).model_dump(mode="json") for prompt in prompts],
        }

    cached_list = cache_get_or_set(cache_key, PROMPT_CACHE_TTL_SECONDS, _load_list)
    response.headers["X-Total-Count"] = str(int(cached_list.get("total_count", 0)))
    return [PromptOut(**prompt) for prompt in cached_list.get("prompts", [])]
