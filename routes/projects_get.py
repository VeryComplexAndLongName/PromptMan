from fastapi import HTTPException

import crud
from database import run_db_call
from routes.shared import to_project_out
from schemas import ProjectOut


def get_project_route(project_id: int, db) -> ProjectOut:  # type: ignore[no-untyped-def]
    project = run_db_call(db, crud.get_project_by_id, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return to_project_out(project)
