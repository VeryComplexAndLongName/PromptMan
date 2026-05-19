from fastapi import HTTPException

import crud
from database import run_db_call
from routes.shared import to_project_out
from schemas import ProjectCreate, ProjectOut


def create_project_route(data: ProjectCreate, db) -> ProjectOut:  # type: ignore[no-untyped-def]
    try:
        project = run_db_call(db, crud.create_project, data.name)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return to_project_out(project)
