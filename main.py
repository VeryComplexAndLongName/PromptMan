from collections.abc import Iterator
from typing import Literal

from fastapi import Depends, FastAPI, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from sqlalchemy.orm import Session

import auth as auth_service
import crud
import app_settings
from app_core.api_version import API_V1
from app_core.lifecycle import chain_actions, create_app_lifespan, create_startup_action, resolve_app_version
from app_core.logging_config import configure_logging
from cache.persistence import create_cache_persist_action, create_cache_prewarm_action
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
from optimizer.jobs import cancel_optimization_job, create_optimization_job, get_optimization_job
from optimizer.service import list_available_models, optimize_prompt_with_active_backend
from optimizer.service import get_llm_provider_catalog
from routes import (
    bootstrap_admin_route,
    cancel_optimize_job_route,
    change_own_password_route,
    create_optimize_job_route,
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
    get_optimize_job_route,
    get_project_route,
    get_prompt_route,
    get_prompt_version_route,
    get_provider_models_route,
    get_user_route,
    list_llm_provider_models_route,
    list_llm_providers_route,
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
    LlmProviderOut,
    OptimizeConfigOut,
    OptimizeConfigUpdate,
    ProjectAccessUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    PromptCreate,
    PromptData,
    PromptOptimizeJobOut,
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


def _bootstrap(db) -> None:  # type: ignore[no-untyped-def]
    """Combined startup bootstrap: admin seeding + loading global settings."""
    auth_service.maybe_bootstrap_admin(db)
    app_settings.load_from_db(db)


startup_action = chain_actions(
    create_startup_action(
        SQLALCHEMY_DATABASE_URL,
        lambda: init_database(),
        lambda: StartupSessionLocal(),
        _bootstrap,
        close_db_session,
    ),
    create_cache_prewarm_action(lambda: StartupSessionLocal()),
)
shutdown_action = create_cache_persist_action(lambda: StartupSessionLocal())

lifespan = create_app_lifespan(startup_action, shutdown_action)


app = FastAPI(title="PromptMan", version=APP_VERSION, lifespan=lifespan)
app.mount("/ui", StaticFiles(directory="ui"), name="ui")


configure_logging()
logger.info("logging.configured sinks=console+file")

# Order matters: request logging stays outermost so every request is traced,
# while exception middleware centralizes uncaught exceptions and returns a
# consistent 500 response.
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


@app.get(f"{API_V1}/prompts/search", response_model=list[PromptOut])
def search_prompts(
    tags: list[str] = Query(..., description="Tags to filter by (repeat for multiple)"),
    mode: Literal["and", "or"] = Query("or", description="'and' requires all tags; 'or' requires any tag"),
    project: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptOut]:
    return search_prompts_route(tags, mode, project, db, current_user)


@app.get(f"{API_V1}/prompts", response_model=list[PromptOut])
def list_prompts(
    response: Response,
    project: str | None = None,
    tag: str | None = None,
    limit: str | None = None,
    offset: str | None = None,
    sort_by: Literal["updated_at", "created_at", "name", "project"] = Query("updated_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[PromptOut]:
    return list_prompts_route(response, project, tag, limit, offset, sort_by, sort_order, db, current_user)


@app.post(f"{API_V1}/prompts", response_model=PromptOut)
def create_prompt(data: PromptCreate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOut:  # type: ignore[no-untyped-def]
    return create_prompt_route(data, db, current_user)


@app.get(f"{API_V1}/prompts/{{project}}/{{name}}", response_model=PromptOut)
def get_prompt(project: str, name: str, db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> PromptOut:  # type: ignore[no-untyped-def]
    return get_prompt_route(project, name, db, current_user)


@app.delete(f"{API_V1}/prompts/{{project}}/{{name}}", status_code=204)
def delete_prompt(project: str, name: str, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> Response:  # type: ignore[no-untyped-def]
    return delete_prompt_route(project, name, db, current_user)


@app.put(f"{API_V1}/prompts/{{project}}/{{name}}", response_model=PromptVersionOut)
def update_prompt(project: str, name: str, data: PromptUpdate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptVersionOut:  # type: ignore[no-untyped-def]
    return update_prompt_route(project, name, data, db, current_user)


@app.put(f"{API_V1}/prompts/{{project}}/{{name}}/tags", response_model=PromptOut)
def update_prompt_tags(project: str, name: str, data: PromptTagsUpdate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOut:  # type: ignore[no-untyped-def]
    return update_prompt_tags_route(project, name, data, db, current_user)


@app.get(f"{API_V1}/prompts/{{project}}/{{name}}/versions", response_model=list[PromptVersionOut])
def list_versions(project: str, name: str, db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> list[PromptVersionOut]:  # type: ignore[no-untyped-def]
    return list_versions_route(project, name, db, current_user)


@app.get(f"{API_V1}/prompts/{{project}}/{{name}}/versions/{{version}}", response_model=PromptVersionOut)
def get_prompt_version(project: str, name: str, version: int, db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> PromptVersionOut:  # type: ignore[no-untyped-def]
    return get_prompt_version_route(project, name, version, db, current_user)


@app.post(f"{API_V1}/optimize", response_model=PromptOptimizeResponse)
def optimize_prompt(data: PromptData, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOptimizeResponse:  # type: ignore[no-untyped-def]
    return optimize_prompt_route(data, db, current_user, optimize_prompt_with_active_backend)


@app.post(f"{API_V1}/optimize/jobs", response_model=PromptOptimizeJobOut)
def create_optimize_job(data: PromptData, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> PromptOptimizeJobOut:  # type: ignore[no-untyped-def]
    return create_optimize_job_route(data, db, current_user, create_optimization_job)


@app.get(f"{API_V1}/optimize/jobs/{{job_id}}", response_model=PromptOptimizeJobOut)
def get_optimize_job(job_id: str, current_user: User = Depends(auth_service.get_current_user)) -> PromptOptimizeJobOut:
    return get_optimize_job_route(job_id, current_user, get_optimization_job)


@app.delete(f"{API_V1}/optimize/jobs/{{job_id}}", response_model=PromptOptimizeJobOut)
def cancel_optimize_job(job_id: str, current_user: User = Depends(auth_service.get_current_user)) -> PromptOptimizeJobOut:
    return cancel_optimize_job_route(job_id, current_user, cancel_optimization_job)


@app.get(f"{API_V1}/optimize/config", response_model=OptimizeConfigOut)
def get_optimize_config(db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> OptimizeConfigOut:  # type: ignore[no-untyped-def]
    return get_optimize_config_route(db, current_user)


@app.get(f"{API_V1}/llm/config", response_model=OptimizeConfigOut)
def get_llm_config(db=Depends(get_db), current_user: User = Depends(auth_service.get_current_user)) -> OptimizeConfigOut:  # type: ignore[no-untyped-def]
    return get_optimize_config_route(db, current_user)


@app.put(f"{API_V1}/optimize/config", response_model=OptimizeConfigOut)
def update_optimize_config(data: OptimizeConfigUpdate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> OptimizeConfigOut:  # type: ignore[no-untyped-def]
    return update_optimize_config_route(data, db, current_user)


@app.put(f"{API_V1}/llm/config", response_model=OptimizeConfigOut)
def update_llm_config(data: OptimizeConfigUpdate, db=Depends(get_db), current_user: User = Depends(auth_service.require_write_access)) -> OptimizeConfigOut:  # type: ignore[no-untyped-def]
    return update_optimize_config_route(data, db, current_user)


@app.get(f"{API_V1}/llm/providers", response_model=list[LlmProviderOut])
def list_llm_providers(current_user: User = Depends(auth_service.get_current_user)) -> list[LlmProviderOut]:
    return list_llm_providers_route(get_llm_provider_catalog)


@app.get(f"{API_V1}/llm/providers/{{provider}}/models", response_model=list[str])
def list_llm_provider_models(
    provider: str,
    base_url: str | None = Query(None, description="Optional provider base URL override"),
    api_token: str | None = Query(None, description="Optional API token for authentication"),
    timeout_seconds: int = Query(5, ge=1, le=30, description="Timeout in seconds for provider model discovery"),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[str]:
    return list_llm_provider_models_route(provider, base_url, api_token, timeout_seconds, db, current_user, list_available_models)


@app.get(f"{API_V1}/optimize/providers/{{provider}}/models", response_model=list[str])
def get_provider_models(
    provider: str,
    base_url: str | None = Query(None, description="Optional provider base URL override"),
    api_token: str | None = Query(None, description="Optional API token for authentication"),
    timeout_seconds: int = Query(5, ge=1, le=30, description="Timeout in seconds for provider model discovery"),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[str]:
    return get_provider_models_route(provider, base_url, api_token, timeout_seconds, db, current_user, list_available_models)

from routes.admin_config import router as admin_config_router

app.include_router(admin_config_router)
