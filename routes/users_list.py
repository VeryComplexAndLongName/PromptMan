import crud
from database import run_db_call
from routes.shared import to_user_out
from schemas import UserOut


def list_users_route(db) -> list[UserOut]:  # type: ignore[no-untyped-def]
    return [to_user_out(user) for user in run_db_call(db, crud.list_users)]
