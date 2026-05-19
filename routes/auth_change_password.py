import auth as auth_service
from database import run_db_call
from models import User
from schemas import ChangePasswordRequest


def change_own_password_route(data: ChangePasswordRequest, db, current_user: User) -> None:  # type: ignore[no-untyped-def]
    run_db_call(
        db,
        auth_service.change_own_password,
        current_user,
        current_password=data.current_password,
        new_password=data.new_password,
    )
