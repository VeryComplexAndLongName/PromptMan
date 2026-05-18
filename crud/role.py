from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Role

DEFAULT_ROLE_NAMES = ("admin", "developer", "viewer")


def list_roles(db: Session) -> list[Role]:
    return list(db.query(Role).order_by(Role.name.asc()).all())


def get_role_by_name(db: Session, name: str) -> Role | None:
    normalized_name = (name or "").strip().lower()
    if not normalized_name:
        return None
    return db.query(Role).filter(func.lower(Role.name) == normalized_name).first()


def ensure_default_roles(db: Session) -> list[Role]:
    existing = db.query(Role).filter(Role.name.in_(DEFAULT_ROLE_NAMES)).all()
    existing_names = {role.name for role in existing}
    for role_name in DEFAULT_ROLE_NAMES:
        if role_name not in existing_names:
            db.add(Role(name=role_name))
    db.commit()
    return list_roles(db)
