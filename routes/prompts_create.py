from fastapi import HTTPException
from loguru import logger

import auth as auth_service
import crud
from database import run_db_call
from models import User
from routes.shared import allowed_projects, invalidate_prompt_cache, to_prompt_out
from schemas import PromptCreate, PromptOut


def create_prompt_route(data: PromptCreate, db, current_user: User) -> PromptOut:  # type: ignore[no-untyped-def]
    logger.info("prompt.create name={} project={}", data.name, data.project)
    auth_service.ensure_project_access(current_user, data.project)
    prompt = run_db_call(db, crud.get_prompt, data.name, data.project, allowed_projects=allowed_projects(current_user))
    if prompt:
        logger.warning("prompt.create.duplicate name={} project={}", data.name, data.project)
        raise HTTPException(400, "Prompt already exists")

    try:
        prompt = run_db_call(
            db,
            crud.create_prompt,
            data.name,
            data.project,
            task=data.task,
            actor_id=current_user.id,
            role=data.role,
            context=data.context,
            constraints=data.constraints,
            output_format=data.output_format,
            examples=data.examples,
            tags=data.tags,
        )
    except ValueError as exc:
        logger.warning("prompt.create.duplicate_content name={} project={}", data.name, data.project)
        raise HTTPException(409, str(exc)) from exc
    invalidate_prompt_cache(data.project, data.name)
    prompt = run_db_call(db, crud.get_prompt, data.name, data.project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        raise HTTPException(404, "Prompt not found after create")
    return to_prompt_out(db, prompt)
