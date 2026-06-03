from pathlib import Path

from fastapi import Depends, FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

import app_settings
import auth as auth_service
from app_core.api_version import API_V1
from app_core.lifecycle import (
    chain_actions,
    create_app_lifespan,
    create_startup_action,
    resolve_app_version,
)
from app_core.logging_config import configure_logging
from database import (
    SQLALCHEMY_DATABASE_URL,
    SessionLocal,
    StartupSessionLocal,
    close_db_session,
    get_db,
    init_database,
)
from middleware import ExceptionLoggingMiddleware, RequestLoggingMiddleware
from models import User
from plugin_engine import PluginEngine
from plugin_engine import router as plugin_router
from routes.admin_config import router as admin_config_router
from routes.app_version import get_app_version_route
from routes.auth_bootstrap_admin import bootstrap_admin_route
from routes.auth_change_password import change_own_password_route
from routes.auth_login import login_route
from routes.auth_me import get_me_route
from routes.auth_refresh import refresh_auth_route
from routes.auth_status import get_auth_status_route
from routes.conversations import router as conversations_router
from routes.projects_create import create_project_route
from routes.projects_delete import delete_project_route
from routes.projects_get import get_project_route
from routes.projects_list import list_projects_route
from routes.projects_update import update_project_route
from routes.prompt_versions import router as prompt_versions_router
from routes.roles_list import list_roles_route
from routes.serve_ui import serve_ui_route
from routes.users_create import create_user_route
from routes.users_delete import delete_user_route
from routes.users_get import get_user_route
from routes.users_list import list_users_route
from routes.users_update import update_user_route
from routes.users_update_projects import update_user_projects_route
from schemas import (
    AuthResponse,
    AuthStatus,
    ChangePasswordRequest,
    ProjectAccessUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
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
    "get_db",
    "init_database",
]


def _bootstrap(db) -> None:  # type: ignore[no-untyped-def]
    auth_service.maybe_bootstrap_admin(db)
    app_settings.load_from_db(db)


startup_action = chain_actions(
    create_startup_action(
        SQLALCHEMY_DATABASE_URL,
        lambda: init_database(),
        lambda: StartupSessionLocal(),
        _bootstrap,
        close_db_session,
    )
)
shutdown_action = None

lifespan = create_app_lifespan(startup_action, shutdown_action)


app = FastAPI(title="PromptMan", version=APP_VERSION, lifespan=lifespan)
app.mount("/ui", StaticFiles(directory="ui"), name="ui")
app.state.plugin_engine = PluginEngine(app, plugins_dir=Path("plugins"), app_version=APP_VERSION)

configure_logging()
logger.info("logging.configured sinks=console+file")


class PluginHookMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):  # type: ignore[no-untyped-def]
        plugin_engine = getattr(request.app.state, "plugin_engine", None)
        if plugin_engine is None:
            return await call_next(request)
        if request.url.path.startswith(f"{API_V1}/plugins/") or request.url.path == f"{API_V1}/plugins":
            return await call_next(request)
        await plugin_engine.run_before_hooks(request)
        response = await call_next(request)
        await plugin_engine.run_after_hooks(request, response)
        return response


app.add_middleware(PluginHookMiddleware)
app.add_middleware(ExceptionLoggingMiddleware)
app.add_middleware(RequestLoggingMiddleware)


@app.get("/", include_in_schema=False)
def serve_ui() -> FileResponse:
    return serve_ui_route()


@app.get("/PromptMan_240x240.png", include_in_schema=False)
def serve_app_icon() -> FileResponse:
    return FileResponse("PromptMan_240x240.png")


@app.get("/P_240x240.png", include_in_schema=False)
def serve_app_icon_new() -> FileResponse:
    return FileResponse("P_240x240.png")


@app.post(f"{API_V1}/auth/bootstrap-admin", response_model=AuthResponse)
def bootstrap_admin(data: UserBootstrap, db=Depends(get_db)) -> AuthResponse:  # type: ignore[no-untyped-def]
    return bootstrap_admin_route(data, db)


@app.post(f"{API_V1}/auth/login", response_model=AuthResponse)
def login(data: UserLogin, db=Depends(get_db)) -> AuthResponse:  # type: ignore[no-untyped-def]
    return login_route(data, db)


@app.post(f"{API_V1}/auth/refresh", response_model=AuthResponse)
def refresh_auth(data: RefreshTokenRequest, db=Depends(get_db)) -> AuthResponse:  # type: ignore[no-untyped-def]
    return refresh_auth_route(data, db)


@app.get(f"{API_V1}/auth/status", response_model=AuthStatus)
def get_auth_status(db=Depends(get_db)) -> AuthStatus:  # type: ignore[no-untyped-def]
    return get_auth_status_route(db)


@app.get(f"{API_V1}/version")
def get_app_version() -> dict[str, str]:
    return get_app_version_route(APP_VERSION)


@app.get(f"{API_V1}/auth/me", response_model=UserOut)
def get_me(current_user: User = Depends(auth_service.get_current_user)) -> UserOut:
    return get_me_route(current_user)


@app.post(f"{API_V1}/auth/me/password", status_code=204)
def change_own_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> None:
    change_own_password_route(data, db, current_user)


@app.get(f"{API_V1}/roles", response_model=list[RoleOut])
def list_roles(db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[RoleOut]:  # type: ignore[no-untyped-def]
    return list_roles_route(db)


@app.get(f"{API_V1}/users", response_model=list[UserOut])
def list_users(db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[UserOut]:  # type: ignore[no-untyped-def]
    return list_users_route(db)


@app.post(f"{API_V1}/users", response_model=UserOut)
def create_user(data: UserCreate, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:  # type: ignore[no-untyped-def]
    return create_user_route(data, db)


@app.get(f"{API_V1}/users/{{user_id}}", response_model=UserOut)
def get_user(user_id: int, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:  # type: ignore[no-untyped-def]
    return get_user_route(user_id, db)


@app.put(f"{API_V1}/users/{{user_id}}", response_model=UserOut)
def update_user(user_id: int, data: UserUpdate, db=Depends(get_db), current_admin: User = Depends(auth_service.require_admin)) -> UserOut:  # type: ignore[no-untyped-def]
    return update_user_route(user_id, data, db, current_admin)


@app.put(f"{API_V1}/users/{{user_id}}/projects", response_model=UserOut)
def update_user_projects(user_id: int, data: ProjectAccessUpdate, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> UserOut:  # type: ignore[no-untyped-def]
    return update_user_projects_route(user_id, data, db)


@app.delete(f"{API_V1}/users/{{user_id}}", status_code=204)
def delete_user(user_id: int, db=Depends(get_db), current_admin: User = Depends(auth_service.require_admin)) -> Response:  # type: ignore[no-untyped-def]
    return delete_user_route(user_id, db, current_admin)


@app.get(f"{API_V1}/projects", response_model=list[ProjectOut])
def list_projects(db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> list[ProjectOut]:  # type: ignore[no-untyped-def]
    return list_projects_route(db)


@app.get(f"{API_V1}/projects/{{project_id}}", response_model=ProjectOut)
def get_project(project_id: int, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:  # type: ignore[no-untyped-def]
    return get_project_route(project_id, db)


@app.post(f"{API_V1}/projects", response_model=ProjectOut)
def create_project(data: ProjectCreate, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:  # type: ignore[no-untyped-def]
    return create_project_route(data, db)


@app.put(f"{API_V1}/projects/{{project_id}}", response_model=ProjectOut)
def update_project(project_id: int, data: ProjectUpdate, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> ProjectOut:  # type: ignore[no-untyped-def]
    return update_project_route(project_id, data, db)


@app.delete(f"{API_V1}/projects/{{project_id}}", status_code=204)
def delete_project(project_id: int, db=Depends(get_db), _: User = Depends(auth_service.require_admin)) -> Response:  # type: ignore[no-untyped-def]
    return delete_project_route(project_id, db)


app.include_router(admin_config_router)
app.include_router(conversations_router)
app.include_router(prompt_versions_router)
app.include_router(plugin_router)
