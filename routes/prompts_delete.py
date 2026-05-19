from fastapi import HTTPException, Response
from loguru import logger

import auth as auth_service
import crud
from database import run_db_call
from models import User
from routes.shared import allowed_projects, invalidate_prompt_cache


def delete_prompt_route(project: str, name: str, db, current_user: User) -> Response:  # type: ignore[no-untyped-def]
    logger.info("prompt.delete project={} name={}", project, name)
    auth_service.ensure_project_access(current_user, project)
    prompt = run_db_call(db, crud.get_prompt, name, project, allowed_projects=allowed_projects(current_user))
    if not prompt:
        logger.warning("prompt.delete.not_found project={} name={}", project, name)
        raise HTTPException(404, "Prompt not found")

    run_db_call(db, crud.delete_prompt, prompt)
    invalidate_prompt_cache(project, name)
    return Response(status_code=204)
