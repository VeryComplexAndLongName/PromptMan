from fastapi import HTTPException

import auth as auth_service
from database import run_db_call
from schemas import AuthResponse, UserLogin


def login_route(data: UserLogin, db) -> AuthResponse:  # type: ignore[no-untyped-def]
    user = run_db_call(db, auth_service.authenticate_user, data.username, data.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    return AuthResponse(**auth_service.build_auth_response(user))
