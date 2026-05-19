import auth as auth_service
from database import run_db_call
from routes.shared import to_user_out
from schemas import UserCreate, UserOut


def create_user_route(data: UserCreate, db) -> UserOut:  # type: ignore[no-untyped-def]
    user = run_db_call(
        db,
        auth_service.create_user_record,
        username=data.username,
        password=data.password,
        role=data.role,
        is_active=data.is_active,
        projects=data.projects,
    )
    return to_user_out(user)
