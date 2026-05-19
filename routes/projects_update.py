from fastapi import HTTPException

import crud
from database import run_db_call
from routes.shared import to_project_out
from schemas import ProjectOut, ProjectUpdate


def update_project_route(project_id: int, data: ProjectUpdate, db) -> ProjectOut:  # type: ignore[no-untyped-def]
    project = run_db_call(db, crud.get_project_by_id, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        updated = run_db_call(db, crud.update_project, project, name=data.name)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return to_project_out(updated)
