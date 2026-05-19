import crud
from database import run_db_call
from routes.shared import to_project_out
from schemas import ProjectOut


def list_projects_route(db) -> list[ProjectOut]:  # type: ignore[no-untyped-def]
    return [to_project_out(project) for project in run_db_call(db, crud.list_projects)]
