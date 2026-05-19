from fastapi import HTTPException, Response

import crud
from database import run_db_call


def delete_project_route(project_id: int, db) -> Response:  # type: ignore[no-untyped-def]
    project = run_db_call(db, crud.get_project_by_id, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    run_db_call(db, crud.delete_project, project)
    return Response(status_code=204)
