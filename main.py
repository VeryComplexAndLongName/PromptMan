from collections.abc import Iterator
from typing import Literal

from fastapi import Depends, FastAPI, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy.orm import Session

import auth as auth_service
import crud
from app_core.lifecycle import create_lifespan, resolve_app_version, run_startup_bootstrap
from app_core.logging_config import configure_logging
from database import (
    SQLALCHEMY_DATABASE_URL,
    SessionLocal,
    StartupSessionLocal,
    close_db_session,
    init_database,
)
from middleware import ExceptionLoggingMiddleware, RequestLoggingMiddleware
from models import User
from optimizer.service import list_available_models, optimize_prompt_with_active_backend
from routes import (
    bootstrap_admin_route,
    change_own_password_route,
    create_project_route,
    create_prompt_route,
    create_user_route,
    delete_project_route,
    delete_prompt_route,
    delete_user_route,
    get_app_version_route,
    get_auth_status_route,
    get_me_route,
    get_optimize_config_route,
    get_project_route,
    get_prompt_route,
    get_prompt_version_route,
    get_provider_models_route,
    get_user_route,
    list_projects_route,
    list_prompts_route,
    list_roles_route,
    list_users_route,
    list_versions_route,
    login_route,
    optimize_prompt_route,
    refresh_auth_route,
    search_prompts_route,
    serve_ui_route,
    update_optimize_config_route,
    update_project_route,
    update_prompt_route,
    update_prompt_tags_route,
    update_user_projects_route,
    update_user_route,
)
from schemas import (
    AuthResponse,
    AuthStatus,
    ChangePasswordRequest,
    OptimizeConfigOut,
    OptimizeConfigUpdate,
    ProjectAccessUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    PromptCreate,
    PromptData,
    PromptOptimizeResponse,
    PromptOut,
    PromptTagsUpdate,
    PromptUpdate,
    PromptVersionOut,
    RefreshTokenRequest,
    RoleOut,
    UserBootstrap,
    UserCreate,
    UserLogin,
    UserOut,
    UserUpdate,
)

APP_VERSION = resolve_app_version()

__all__ = [
    "SessionLocal",
    "StartupSessionLocal",
    "app",
    "crud",
    "get_db",
    "init_database",
    "list_available_models",
    "optimize_prompt_with_active_backend",
]


def _run_startup_bootstrap() -> None:
    run_startup_bootstrap(
        SQLALCHEMY_DATABASE_URL,
        init_database,
        StartupSessionLocal,
        auth_service.maybe_bootstrap_admin,
        close_db_session,
    )


lifespan = create_lifespan(_run_startup_bootstrap)


app = FastAPI(title="Prompt Man", version=APP_VERSION, lifespan=lifespan)
app.mount("/ui", StaticFiles(directory="ui"), name="ui")


configure_logging()
logger.info("logging.configured sinks=console+file")

# Order matters: request logging stays outermost so every request is traced,
# while exception middleware centralizes uncaught exceptions and returns a
# consistent 500 response.
app.add_middleware(ExceptionLoggingMiddleware)
app.add_middleware(RequestLoggingMiddleware)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        close_db_session(db)


@app.get("/", include_in_schema=False)
def serve_ui() -> FileResponse:
    return serve_ui_route()


@app.post("/auth/bootstrap-admin", response_model=AuthResponse)
def bootstrap_admin(data: UserBootstrap, db=Depends(get_db)) -> AuthResponse:  # type: ignore[no-untyped-def]
    return bootstrap_admin_route(data, db)


@app.post("/auth/login", response_model=AuthResponse)
def login(data: UserLogin, db=Depends(get_db)) -> AuthResponse:  # type: ignore[no-untyped-def]
    return login_route(data, db)


@app.post("/auth/refresh", response_model=AuthResponse)
def refresh_auth(data: RefreshTokenRequest, db=Depends(get_db)) -> AuthResponse:  # type: ignore[no-untyped-def]
    return refresh_auth_route(data, db)


@app.get("/auth/status", response_model=AuthStatus)
def get_auth_status(db=Depends(get_db)) -> AuthStatus:  # type: ignore[no-untyped-def]
    return get_auth_status_route(db)


@app.get("/version")
def get_app_version() -> dict[str, str]:
    return get_app_version_route(APP_VERSION)


@app.get("/auth/me", response_model=UserOut)
def get_me(current_user: User = Depends(auth_service.get_current_user)) -> UserOut:
    return get_me_route(current_user)


@app.post("/auth/me/password", status_code=204)
def change_own_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> None:
    change_own_password_route(data, db, current_user)


@app.get("/roles", response_model=list[RoleOut])
def list_roles(db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[RoleOut]:  # type: ignore[no-untyped-def]
    return list_roles_route(db)


@app.get("/users", response_model=list[UserOut])
def list_users(db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[UserOut]:  # type: ignore[no-untyped-def]
    return list_users_route(db)


@app.post("/users", response_model=UserOut)
def create_user(data: UserCreate, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:  # type: ignore[no-untyped-def]
    return create_user_route(data, db)


@app.get("/users/{user_id}", response_model=UserOut)
def get_user(user_id: int, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:  # type: ignore[no-untyped-def]
    return get_user_route(user_id, db)


@app.put("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db=Depends(get_db), current_admin: User = Depends(auth_service.require_admin)) -> UserOut:  # type: ignore[no-untyped-def]
    return update_user_route(user_id, data, db, current_admin)


@app.put("/users/{user_id}/projects", response_model=UserOut)
def update_user_projects(user_id: int, data: ProjectAccessUpdate, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:  # type: ignore[no-untyped-def]
    return update_user_projects_route(user_id, data, db)


@app.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, db=Depends(get_db), current_admin: User = Depends(auth_service.require_admin)) -> Response:  # type: ignore[no-untyped-def]
    return delete_user_route(user_id, db, current_admin)


@app.get("/projects", response_model=list[ProjectOut])
def list_projects(db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[ProjectOut]:  # type: ignore[no-untyped-def]
    return list_projects_route(db)


@app.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:  # type: ignore[no-untyped-def]
    return get_project_route(project_id, db)


@app.post("/projects", response_model=ProjectOut)
def create_project(data: ProjectCreate, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:  # type: ignore[no-untyped-def]
    return create_project_route(data, db)


@app.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, data: ProjectUpdate, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:  # type: ignore[no-untyped-def]
    return update_project_route(project_id, data, db)


@app.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> Response:  # type: ignore[no-untyped-def]
    return delete_project_route(project_id, db)


@app.get("/prompts/search", response_model=list[PromptOut])
def search_prompts(
    tags: list[str] = Query(..., description="Tags to filter by (repeat for multiple)"),
    mode: Literal["and", "or"] = Query("or", description="'and' requires all tags; 'or' requires any tag"),
    project: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptOut]:
    return search_prompts_route(tags, mode, project, db, current_user)


@app.get("/prompts", response_model=list[PromptOut])
def list_prompts(
    response: Response,
    project: str | None = None,
    tag: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptOut]:
    return list_prompts_route(response, project, tag, limit, offset, db, current_user)


@app.post("/prompts", response_model=PromptOut)
def create_prompt(data: PromptCreate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOut:  # type: ignore[no-untyped-def]
    return create_prompt_route(data, db, current_user)


@app.get("/prompts/{project}/{name}", response_model=PromptOut)
def get_prompt(project: str, name: str, db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> PromptOut:  # type: ignore[no-untyped-def]
    return get_prompt_route(project, name, db, current_user)


@app.delete("/prompts/{project}/{name}", status_code=204)
def delete_prompt(project: str, name: str, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> Response:  # type: ignore[no-untyped-def]
    return delete_prompt_route(project, name, db, current_user)


@app.put("/prompts/{project}/{name}", response_model=PromptVersionOut)
def update_prompt(project: str, name: str, data: PromptUpdate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptVersionOut:  # type: ignore[no-untyped-def]
    return update_prompt_route(project, name, data, db, current_user)


@app.put("/prompts/{project}/{name}/tags", response_model=PromptOut)
def update_prompt_tags(project: str, name: str, data: PromptTagsUpdate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOut:  # type: ignore[no-untyped-def]
    return update_prompt_tags_route(project, name, data, db, current_user)


@app.get("/prompts/{project}/{name}/versions", response_model=list[PromptVersionOut])
def list_versions(project: str, name: str, db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> list[PromptVersionOut]:  # type: ignore[no-untyped-def]
    return list_versions_route(project, name, db, current_user)


@app.get("/prompts/{project}/{name}/versions/{version}", response_model=PromptVersionOut)
def get_prompt_version(project: str, name: str, version: int, db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> PromptVersionOut:  # type: ignore[no-untyped-def]
    return get_prompt_version_route(project, name, version, db, current_user)


@app.post("/optimize", response_model=PromptOptimizeResponse)
def optimize_prompt(data: PromptData, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOptimizeResponse:  # type: ignore[no-untyped-def]
    return optimize_prompt_route(data, db, current_user, optimize_prompt_with_active_backend)


@app.get("/optimize/config", response_model=OptimizeConfigOut)
def get_optimize_config(db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> OptimizeConfigOut:  # type: ignore[no-untyped-def]
    return get_optimize_config_route(db, current_user)


@app.put("/optimize/config", response_model=OptimizeConfigOut)
def update_optimize_config(data: OptimizeConfigUpdate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> OptimizeConfigOut:  # type: ignore[no-untyped-def]
    return update_optimize_config_route(data, db, current_user)


@app.get("/optimize/providers/{provider}/models", response_model=list[str])
def get_provider_models(
    provider: str,
    base_url: str | None = Query(None, description="Optional provider base URL override"),
    api_token: str | None = Query(None, description="Optional API token for authentication"),
    timeout_seconds: int = Query(5, ge=1, le=30, description="Timeout in seconds for provider model discovery"),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[str]:
    return get_provider_models_route(provider, base_url, api_token, timeout_seconds, db, current_user, list_available_models)
