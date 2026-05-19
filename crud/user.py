import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from models import Config, ProjectAccess, User

from .project import get_or_create_projects
from .role import get_role_by_name


def get_default_admin_user(db: Session) -> User | None:
    return get_user_by_username(db, "admin")


def resolve_audit_username(db: Session, user: User | None) -> str:
    if user and user.username:
        return user.username
    admin_user = get_default_admin_user(db)
    return admin_user.username if admin_user else "admin"


def list_users(db: Session) -> list[User]:
    return list(
        db.query(User)
        .options(joinedload(User.role_ref), joinedload(User.project_access).joinedload(ProjectAccess.project_ref))
        .order_by(User.username.asc())
        .all()
    )


def get_user_by_username(db: Session, username: str) -> User | None:
    return (
        db.query(User)
        .options(joinedload(User.role_ref), joinedload(User.project_access).joinedload(ProjectAccess.project_ref))
        .filter(func.lower(User.username) == username.strip().lower())
        .first()
    )


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return (
        db.query(User)
        .options(joinedload(User.role_ref), joinedload(User.project_access).joinedload(ProjectAccess.project_ref))
        .filter(User.id == user_id)
        .first()
    )


def get_or_create_user_config(db: Session, user_id: int) -> Config:
    config = db.query(Config).filter(Config.user_id == user_id).first()
    if config:
        return config
    config = Config(user_id=user_id)
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def set_user_projects(db: Session, user: User, projects: list[str] | None) -> User:
    db_projects = get_or_create_projects(db, projects or [])
    user.project_access.clear()
    for project in sorted(db_projects, key=lambda item: item.name.lower()):
        user.project_access.append(ProjectAccess(project_ref=project))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_user(
    db: Session,
    *,
    username: str,
    password_hash_encrypted: str,
    role: str,
    is_active: bool,
    projects: list[str] | None = None,
) -> User:
    role_record = get_role_by_name(db, role)
    if role_record is None:
        raise ValueError("Invalid role")
    user = User(username=username.strip(), password_hash_encrypted=password_hash_encrypted, role_ref=role_record, is_active=is_active)
    db.add(user)
    db.flush()
    db.add(Config(user_id=user.id))
    db.commit()
    db.refresh(user)
    return set_user_projects(db, user, projects)


def update_user(
    db: Session,
    user: User,
    *,
    username: str | None = None,
    password_hash_encrypted: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    projects: list[str] | None = None,
    password_changed_at: datetime.datetime | None = None,
) -> User:
    if username is not None:
        user.username = username.strip()
    if password_hash_encrypted is not None:
        user.password_hash_encrypted = password_hash_encrypted
    if role is not None:
        role_record = get_role_by_name(db, role)
        if role_record is None:
            raise ValueError("Invalid role")
        user.role_ref = role_record
    if is_active is not None:
        user.is_active = is_active
    if password_changed_at is not None:
        user.password_changed_at = password_changed_at
    db.add(user)
    db.commit()
    db.refresh(user)
    if projects is not None:
        return set_user_projects(db, user, projects)
    return user


def delete_user(db: Session, user: User) -> None:
    db.delete(user)
    db.commit()
