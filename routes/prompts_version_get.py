from fastapi import HTTPException

import auth as auth_service
import crud
from cache.shared_cache import (
    PROMPT_CACHE_TTL_SECONDS,
    build_prompt_collection_cache_key,
    cache_get_or_set,
)
from database import run_db_call
from models import User
from routes.shared import allowed_projects, to_prompt_version_out
from schemas import PromptVersionOut


def get_prompt_version_route(project: str, name: str, version: int, db, current_user: User) -> PromptVersionOut:  # type: ignore[no-untyped-def]
    auth_service.ensure_project_access(current_user, project)
    cache_key = build_prompt_collection_cache_key(route="prompts.version", project=project, name=name, version=version)

    def _load_version() -> dict[str, object]:
        prompt = run_db_call(db, crud.get_prompt, name, project, allowed_projects=allowed_projects(current_user))
        if not prompt:
            raise HTTPException(404, "Prompt not found")

        prompt_version = run_db_call(db, crud.get_specific_version, prompt.id, version)
        if not prompt_version:
            raise HTTPException(404, "Version not found")

        return to_prompt_version_out(db, prompt_version).model_dump(mode="json")

    cached_version = cache_get_or_set(cache_key, PROMPT_CACHE_TTL_SECONDS, _load_version)
    return PromptVersionOut(**cached_version)
