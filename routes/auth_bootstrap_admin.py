from fastapi import HTTPException

import auth as auth_service
import crud
from database import run_db_call
from schemas import AuthResponse, UserBootstrap


def bootstrap_admin_route(data: UserBootstrap, db) -> AuthResponse:  # type: ignore[no-untyped-def]
    if run_db_call(db, crud.list_users):
        raise HTTPException(409, "Users already exist")
    user = run_db_call(
        db,
        auth_service.create_user_record,
        username=data.username,
        password=data.password,
        role="admin",
        is_active=True,
        projects=[],
    )
    return AuthResponse(**auth_service.build_auth_response(user))
