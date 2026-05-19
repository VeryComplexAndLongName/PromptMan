from fastapi import HTTPException

import crud
from database import run_db_call
from routes.shared import to_user_out
from schemas import ProjectAccessUpdate, UserOut


def update_user_projects_route(user_id: int, data: ProjectAccessUpdate, db) -> UserOut:  # type: ignore[no-untyped-def]
    user = run_db_call(db, crud.get_user_by_id, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    updated = run_db_call(db, crud.set_user_projects, user, data.projects)
    return to_user_out(updated)
