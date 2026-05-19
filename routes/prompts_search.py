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


def search_prompts_route(
    tags: list[str],
    mode: str,
    project: str | None,
    db: Session,
    current_user: User,
) -> list[PromptOut]:
    if project is not None:
        auth_service.ensure_project_access(current_user, project)
    user_allowed_projects = allowed_projects(current_user)
    cache_key = build_prompt_collection_cache_key(
        route="prompts.search",
        project=project,
        tags=tags,
        mode=mode,
        allowed_projects=user_allowed_projects,
    )

    def _load_search() -> list[dict[str, object]]:
        prompts = run_db_call(db, crud.search_prompts_by_tags, tags=tags, mode=mode, project=project, allowed_projects=user_allowed_projects)
        return [to_prompt_out(db, prompt).model_dump(mode="json") for prompt in prompts]

    cached_prompts = cache_get_or_set(cache_key, PROMPT_CACHE_TTL_SECONDS, _load_search)
    return [PromptOut(**prompt) for prompt in cached_prompts]
