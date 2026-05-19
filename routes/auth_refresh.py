import auth as auth_service
from database import run_db_call
from schemas import AuthResponse, RefreshTokenRequest


def refresh_auth_route(data: RefreshTokenRequest, db) -> AuthResponse:  # type: ignore[no-untyped-def]
    return AuthResponse(**run_db_call(db, auth_service.refresh_session, data.refresh_token))
