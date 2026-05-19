from fastapi import HTTPException

import auth as auth_service
import crud
from database import run_db_call
from models import User
from routes.shared import allowed_projects, invalidate_prompt_cache, to_prompt_out
from schemas import PromptOut, PromptTagsUpdate


def update_prompt_tags_route(project: str, name: str, data: PromptTagsUpdate, db, current_user: User) -> PromptOut:  # type: ignore[no-untyped-def]
    auth_service.ensure_project_access(current_user, project)
    prompt = run_db_call(db, crud.get_prompt, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        raise HTTPException(404, "Prompt not found")

    run_db_call(db, crud.set_prompt_tags, prompt, data.tags, actor_id=current_user.id)
    invalidate_prompt_cache(project, name)
    prompt = run_db_call(db, crud.get_prompt, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        raise HTTPException(404, "Prompt not found after update")
    return to_prompt_out(db, prompt)
