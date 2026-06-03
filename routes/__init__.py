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

__all__ = [
    "bootstrap_admin_route",
    "change_own_password_route",
    "conversations_router",
    "create_project_route",
    "create_user_route",
    "delete_project_route",
    "delete_user_route",
    "get_app_version_route",
    "get_auth_status_route",
    "get_me_route",
    "get_project_route",
    "get_user_route",
    "list_projects_route",
    "list_roles_route",
    "list_users_route",
    "login_route",
    "prompt_versions_router",
    "refresh_auth_route",
    "serve_ui_route",
    "update_project_route",
    "update_user_projects_route",
    "update_user_route",
]
