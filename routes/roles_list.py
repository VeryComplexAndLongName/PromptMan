import auth as auth_service
from database import run_db_call
from schemas import RoleOut


def list_roles_route(db) -> list[RoleOut]:  # type: ignore[no-untyped-def]
    return [RoleOut(**item) for item in run_db_call(db, auth_service.list_roles_out)]
