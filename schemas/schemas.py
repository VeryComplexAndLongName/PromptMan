from typing import Annotated

from pydantic import BaseModel, StringConstraints

RequiredPromptText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
class UserLogin(BaseModel):
    username: RequiredPromptText
    password: RequiredPromptText


class UserBootstrap(BaseModel):
    username: RequiredPromptText
    password: RequiredPromptText


class RefreshTokenRequest(BaseModel):
    refresh_token: RequiredPromptText


class ProjectAccessUpdate(BaseModel):
    projects: list[RequiredPromptText] = []


class ProjectCreate(BaseModel):
    name: RequiredPromptText


class ProjectUpdate(BaseModel):
    name: RequiredPromptText


class ProjectOut(BaseModel):
    id: int
    name: str


class RoleOut(BaseModel):
    id: int
    name: str


class UserCreate(BaseModel):
    username: RequiredPromptText
    password: RequiredPromptText
    role: str = "developer"
    is_active: bool = True
    projects: list[RequiredPromptText] = []


class UserUpdate(BaseModel):
    username: RequiredPromptText | None = None
    password: RequiredPromptText | None = None
    role: str | None = None
    is_active: bool | None = None
    projects: list[RequiredPromptText] | None = None


class ChangePasswordRequest(BaseModel):
    current_password: RequiredPromptText
    new_password: RequiredPromptText


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    projects: list[str] = []


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int
    access_token_expires_at: int
    refresh_token_expires_at: int
    user: UserOut


class AuthStatus(BaseModel):
    bootstrap_required: bool
    has_users: bool
