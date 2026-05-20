from routes.app_version import get_app_version_route
from routes.auth_bootstrap_admin import bootstrap_admin_route
from routes.auth_change_password import change_own_password_route
from routes.auth_login import login_route
from routes.auth_me import get_me_route
from routes.auth_refresh import refresh_auth_route
from routes.auth_status import get_auth_status_route
from routes.llm_providers import list_llm_providers_route
from routes.optimize_config_get import get_optimize_config_route
from routes.optimize_config_update import update_optimize_config_route
from routes.optimize_jobs import cancel_optimize_job_route, create_optimize_job_route, get_optimize_job_route
from routes.optimize_prompt import optimize_prompt_route
from routes.optimize_provider_models import get_provider_models_route, list_llm_provider_models_route
from routes.projects_create import create_project_route
from routes.projects_delete import delete_project_route
from routes.projects_get import get_project_route
from routes.projects_list import list_projects_route
from routes.projects_update import update_project_route
from routes.prompts_create import create_prompt_route
from routes.prompts_delete import delete_prompt_route
from routes.prompts_get import get_prompt_route
from routes.prompts_list import list_prompts_route
from routes.prompts_search import search_prompts_route
from routes.prompts_update import update_prompt_route
from routes.prompts_update_tags import update_prompt_tags_route
from routes.prompts_version_get import get_prompt_version_route
from routes.prompts_versions_list import list_versions_route
from routes.roles_list import list_roles_route
from routes.serve_ui import serve_ui_route
from routes.users_create import create_user_route
from routes.users_delete import delete_user_route
from routes.users_get import get_user_route
from routes.users_list import list_users_route
from routes.users_update import update_user_route
from routes.users_update_projects import update_user_projects_route

__all__ = [
    "bootstrap_admin_route",
    "cancel_optimize_job_route",
    "create_optimize_job_route",
    "change_own_password_route",
    "create_project_route",
    "create_prompt_route",
    "create_user_route",
    "delete_project_route",
    "delete_prompt_route",
    "delete_user_route",
    "get_app_version_route",
    "get_auth_status_route",
    "get_me_route",
    "get_optimize_config_route",
    "get_optimize_job_route",
    "get_project_route",
    "get_prompt_route",
    "get_prompt_version_route",
    "get_provider_models_route",
    "get_user_route",
    "list_llm_provider_models_route",
    "list_llm_providers_route",
    "list_projects_route",
    "list_prompts_route",
    "list_roles_route",
    "list_users_route",
    "list_versions_route",
    "login_route",
    "optimize_prompt_route",
    "refresh_auth_route",
    "search_prompts_route",
    "serve_ui_route",
    "update_optimize_config_route",
    "update_project_route",
    "update_prompt_route",
    "update_prompt_tags_route",
    "update_user_projects_route",
    "update_user_route",
]
