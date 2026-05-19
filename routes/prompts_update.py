from fastapi import HTTPException
from loguru import logger

import auth as auth_service
import crud
from database import run_db_call
from models import User
from routes.shared import allowed_projects, invalidate_prompt_cache, to_prompt_version_out
from schemas import PromptUpdate, PromptVersionOut


def update_prompt_route(project: str, name: str, data: PromptUpdate, db, current_user: User) -> PromptVersionOut:  # type: ignore[no-untyped-def]
    logger.info("prompt.update project={} name={}", project, name)
    auth_service.ensure_project_access(current_user, project)
    prompt = run_db_call(db, crud.get_prompt, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        logger.warning("prompt.update.not_found project={} name={}", project, name)
        raise HTTPException(404, "Prompt not found")

    if data.tags is not None:
        run_db_call(db, crud.set_prompt_tags, prompt, data.tags, actor_id=current_user.id)

    try:
        new_version = run_db_call(
            db,
            crud.add_version,
            prompt.id,
            task=data.task,
            actor_id=current_user.id,
            role=data.role,
            context=data.context,
            constraints=data.constraints,
            output_format=data.output_format,
            examples=data.examples,
        )
    except ValueError as exc:
        logger.warning("prompt.update.conflict project={} name={} error={}", project, name, str(exc))
        raise HTTPException(409, str(exc)) from exc
    invalidate_prompt_cache(project, name)
    refreshed_version = run_db_call(db, crud.get_specific_version, prompt.id, new_version.version)
    if not refreshed_version:
        raise HTTPException(404, "Version not found after update")
    return to_prompt_version_out(db, refreshed_version)
