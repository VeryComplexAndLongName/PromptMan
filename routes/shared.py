from __future__ import annotations

from typing import TYPE_CHECKING, Any

import auth as auth_service
from schemas import ProjectOut, UserOut

if TYPE_CHECKING:
    from models import User


def to_user_out(user: User) -> UserOut:
    return UserOut(**auth_service.user_to_dict(user))


def to_project_out(project: Any) -> ProjectOut:
    return ProjectOut(id=project.id, name=project.name)
