from fastapi import HTTPException

import auth as auth_service
import crud
from database import run_db_call
from models import User
from routes.shared import to_user_out
from schemas import UserOut, UserUpdate


def update_user_route(user_id: int, data: UserUpdate, db, current_admin: User) -> UserOut:  # type: ignore[no-untyped-def]
    user = run_db_call(db, crud.get_user_by_id, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if current_admin.id == user.id and data.role is not None and data.role != "admin":
        raise HTTPException(400, "Admin cannot remove own admin role")
    updated = run_db_call(
        db,
        auth_service.update_user_record,
        user,
        username=data.username,
        password=data.password,
        role=data.role,
        is_active=data.is_active,
        projects=data.projects,
    )
    return to_user_out(updated)
