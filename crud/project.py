from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Project

from .common import normalize_project_name


def get_project_by_name(db: Session, name: str) -> Project | None:
    normalized_name = normalize_project_name(name)
    if not normalized_name:
        return None
    return db.query(Project).filter(func.lower(Project.name) == normalized_name.lower()).first()


def get_project_by_id(db: Session, project_id: int) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()


def list_projects(db: Session) -> list[Project]:
    return list(db.query(Project).order_by(Project.name.asc()).all())


def create_project(db: Session, name: str) -> Project:
    normalized_name = normalize_project_name(name)
    existing = get_project_by_name(db, normalized_name)
    if existing:
        raise ValueError("Project already exists")
    project = Project(name=normalized_name)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def update_project(db: Session, project: Project, *, name: str) -> Project:
    normalized_name = normalize_project_name(name)
    existing = get_project_by_name(db, normalized_name)
    if existing and existing.id != project.id:
        raise ValueError("Project already exists")
    project.name = normalized_name
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def delete_project(db: Session, project: Project) -> None:
    db.delete(project)
    db.commit()


def get_or_create_project(db: Session, name: str) -> Project:
    normalized_name = normalize_project_name(name)
    existing = get_project_by_name(db, normalized_name)
    if existing:
        return existing
    project = Project(name=normalized_name)
    db.add(project)
    db.flush()
    return project


def get_or_create_projects(db: Session, names: list[str]) -> list[Project]:
    normalized_names = sorted({normalize_project_name(name) for name in names if name and normalize_project_name(name)})
    if not normalized_names:
        return []

    existing = db.query(Project).filter(Project.name.in_(normalized_names)).all()
    existing_names = {project.name for project in existing}
    new_projects = [Project(name=name) for name in normalized_names if name not in existing_names]
    if new_projects:
        db.add_all(new_projects)
        db.flush()
    return [*existing, *new_projects]
