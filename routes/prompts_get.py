from fastapi import HTTPException

import auth as auth_service
import crud
from cache.shared_cache import (
    PROMPT_CACHE_TTL_SECONDS,
    build_prompt_response_cache_key,
    cache_get_or_set,
)
from database import run_db_call
from models import User
from routes.shared import allowed_projects, to_prompt_out
from schemas import PromptOut


def get_prompt_route(project: str, name: str, db, current_user: User) -> PromptOut:  # type: ignore[no-untyped-def]
    auth_service.ensure_project_access(current_user, project)
    cache_key = build_prompt_response_cache_key(project, name)

    def _load_prompt() -> dict[str, object]:
        prompt = run_db_call(db, crud.get_prompt, name, project, allowed_projects=allowed_projects(current_user))
        if not prompt:
            raise HTTPException(404, "Prompt not found")
        return to_prompt_out(db, prompt).model_dump(mode="json")

    cached_prompt = cache_get_or_set(cache_key, PROMPT_CACHE_TTL_SECONDS, _load_prompt)
    return PromptOut(**cached_prompt)
