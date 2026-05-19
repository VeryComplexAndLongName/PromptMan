import crud
from database import run_db_call
from schemas import AuthStatus


def get_auth_status_route(db) -> AuthStatus:  # type: ignore[no-untyped-def]
    has_users = bool(run_db_call(db, crud.list_users))
    return AuthStatus(bootstrap_required=not has_users, has_users=has_users)
