from fastapi import HTTPException, Response

import crud
from database import run_db_call
from models import User


def delete_user_route(user_id: int, db, current_admin: User) -> Response:  # type: ignore[no-untyped-def]
    user = run_db_call(db, crud.get_user_by_id, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if current_admin.id == user.id:
        raise HTTPException(400, "Admin cannot delete self")
    run_db_call(db, crud.delete_user, user)
    return Response(status_code=204)
