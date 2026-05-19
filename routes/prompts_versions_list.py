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


def list_versions_route(project: str, name: str, db, current_user: User) -> list[PromptVersionOut]:  # type: ignore[no-untyped-def]
    auth_service.ensure_project_access(current_user, project)
    cache_key = build_prompt_collection_cache_key(route="prompts.versions", project=project, name=name)

    def _load_versions() -> list[dict[str, object]]:
        prompt = run_db_call(db, crud.get_prompt, name, project, allowed_projects=allowed_projects(current_user))
        if not prompt:
            raise HTTPException(404, "Prompt not found")

        versions = run_db_call(db, crud.list_versions, prompt.id)
        return [to_prompt_version_out(db, version).model_dump(mode="json") for version in versions]

    cached_versions = cache_get_or_set(cache_key, PROMPT_CACHE_TTL_SECONDS, _load_versions)
    return [PromptVersionOut(**version) for version in cached_versions]
