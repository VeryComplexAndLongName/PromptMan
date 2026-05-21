from sqlalchemy import false, func
from sqlalchemy.orm import Query, Session, joinedload

from models import Project, Prompt, PromptVersion, Tag

from .common import _utcnow, normalize_project_name, normalize_tags
from .project import get_or_create_project, get_or_create_tags


def has_duplicate_prompt_version_content(
    db: Session,
    *,
    role: str | None,
    task: str,
    context: str | None,
    constraints: str | None,
    output_format: str | None,
    examples: str | None,
) -> bool:
    query = db.query(PromptVersion)

    filters = {
        PromptVersion.role: role,
        PromptVersion.task: task,
        PromptVersion.context: context,
        PromptVersion.constraints: constraints,
        PromptVersion.output_format: output_format,
        PromptVersion.examples: examples,
    }

    for column, value in filters.items():
        query = query.filter(column.is_(None)) if value is None else query.filter(column == value)

    return bool(db.query(query.exists()).scalar())


def create_prompt(
    db: Session,
    name: str,
    project: str,
    task: str,
    actor_id: int | None = None,
    role: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    output_format: str | None = None,
    examples: str | None = None,
    tags: list[str] | None = None,
) -> Prompt:
    if has_duplicate_prompt_version_content(
        db,
        role=role,
        task=task,
        context=context,
        constraints=constraints,
        output_format=output_format,
        examples=examples,
    ):
        raise ValueError("Duplicate prompt version content is not allowed")

    normalized_tags = normalize_tags(tags)
    db_tags = get_or_create_tags(db, normalized_tags)
    project_record = get_or_create_project(db, project)
    now = _utcnow()

    prompt = Prompt(
        name=name,
        project_ref=project_record,
        created_at=now,
        updated_at=now,
        created_by_id=actor_id,
        updated_by_id=actor_id,
    )
    prompt.tags = db_tags
    db.add(prompt)
    db.flush()
    db.refresh(prompt)

    version = PromptVersion(
        prompt_id=prompt.id,
        version=1,
        created_at=now,
        created_by_id=actor_id,
        role=role,
        task=task,
        context=context,
        constraints=constraints,
        output_format=output_format,
        examples=examples,
    )
    db.add(version)
    db.commit()

    return prompt


def get_prompt(db: Session, name: str, project: str, allowed_projects: list[str] | None = None) -> Prompt | None:
    query = (
        db.query(Prompt)
        .join(Prompt.project_ref)
        .options(
            joinedload(Prompt.project_ref),
            joinedload(Prompt.created_by_ref),
            joinedload(Prompt.updated_by_ref),
            joinedload(Prompt.tags),
        )
        .filter(Prompt.name == name, Project.name == normalize_project_name(project))
    )
    if allowed_projects is not None:
        if not allowed_projects:
            return None
        query = query.filter(Project.name.in_(allowed_projects))
    return query.first()


def delete_prompt(db: Session, prompt: Prompt) -> None:
    db.delete(prompt)
    db.commit()


def _build_prompt_list_query(
    db: Session,
    project: str | None = None,
    tag: str | None = None,
    allowed_projects: list[str] | None = None,
) -> Query[Prompt]:
    query = db.query(Prompt)
    query = query.join(Prompt.project_ref).options(
        joinedload(Prompt.project_ref),
        joinedload(Prompt.created_by_ref),
        joinedload(Prompt.updated_by_ref),
        joinedload(Prompt.tags),
    )

    if allowed_projects is not None:
        if not allowed_projects:
            return query.filter(false())
        query = query.filter(Project.name.in_(allowed_projects))

    if project:
        query = query.filter(Project.name == normalize_project_name(project))

    if tag:
        query = query.join(Prompt.tags).filter(Tag.name == tag.strip().lower())

    return query


def count_prompts(db: Session, project: str | None = None, tag: str | None = None, allowed_projects: list[str] | None = None) -> int:
    query = _build_prompt_list_query(db, project=project, tag=tag, allowed_projects=allowed_projects)
    result = query.distinct().count()
    return int(result) if result is not None else 0


def list_prompts(
    db: Session,
    project: str | None = None,
    tag: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    allowed_projects: list[str] | None = None,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> list[Prompt]:
    query = _build_prompt_list_query(db, project=project, tag=tag, allowed_projects=allowed_projects)

    order_desc = sort_order.strip().lower() == "desc"
    normalized_sort_by = (sort_by or "updated_at").strip().lower()

    if normalized_sort_by == "name":
        primary = Prompt.name.desc() if order_desc else Prompt.name.asc()
        query = query.order_by(primary, Project.name.asc(), Prompt.updated_at.desc())
    elif normalized_sort_by == "project":
        primary = Project.name.desc() if order_desc else Project.name.asc()
        query = query.order_by(primary, Prompt.name.asc(), Prompt.updated_at.desc())
    elif normalized_sort_by == "created_at":
        primary = Prompt.created_at.desc() if order_desc else Prompt.created_at.asc()
        query = query.order_by(primary, Project.name.asc(), Prompt.name.asc())
    else:
        # Default sort: last modified first.
        primary = Prompt.updated_at.desc() if order_desc else Prompt.updated_at.asc()
        query = query.order_by(primary, Project.name.asc(), Prompt.name.asc())

    if offset is not None:
        query = query.offset(max(0, offset))
    if limit is not None:
        query = query.limit(max(1, limit))

    results = query.all()
    return list(results) if results else []


def get_latest_version(db: Session, prompt_id: int) -> PromptVersion | None:
    return (
        db.query(PromptVersion)
        .options(joinedload(PromptVersion.created_by_ref))
        .filter_by(prompt_id=prompt_id)
        .order_by(PromptVersion.version.desc())
        .first()
    )


def add_version(
    db: Session,
    prompt_id: int,
    task: str,
    actor_id: int | None = None,
    role: str | None = None,
    context: str | None = None,
    constraints: str | None = None,
    output_format: str | None = None,
    examples: str | None = None,
) -> PromptVersion:
    prompt = db.query(Prompt).filter(Prompt.id == prompt_id).first()
    if not prompt:
        raise ValueError(f"Prompt {prompt_id} not found")

    latest = get_latest_version(db, prompt_id)
    if not latest:
        raise ValueError(f"No latest version found for prompt {prompt_id}")

    # Check if content is identical to latest version; if so, return latest without creating new version
    if (
        latest.role == role
        and latest.task == task
        and latest.context == context
        and latest.constraints == constraints
        and latest.output_format == output_format
        and latest.examples == examples
    ):
        return latest

    if has_duplicate_prompt_version_content(
        db,
        role=role,
        task=task,
        context=context,
        constraints=constraints,
        output_format=output_format,
        examples=examples,
    ):
        raise ValueError("Duplicate prompt version content is not allowed")

    now = _utcnow()
    new_version = PromptVersion(
        prompt_id=prompt_id,
        version=latest.version + 1,
        created_at=now,
        created_by_id=actor_id,
        role=role,
        task=task,
        context=context,
        constraints=constraints,
        output_format=output_format,
        examples=examples,
    )
    prompt.updated_at = now
    prompt.updated_by_id = actor_id
    db.add(prompt)
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    return new_version


def set_prompt_tags(db: Session, prompt: Prompt, tags: list[str] | None, actor_id: int | None = None) -> Prompt:
    normalized_tags = normalize_tags(tags)
    db_tags = get_or_create_tags(db, normalized_tags)
    prompt.tags = db_tags
    prompt.updated_at = _utcnow()
    prompt.updated_by_id = actor_id
    db.commit()
    db.refresh(prompt)
    return prompt


def get_specific_version(db: Session, prompt_id: int, version: int) -> PromptVersion | None:
    return (
        db.query(PromptVersion)
        .options(joinedload(PromptVersion.created_by_ref))
        .filter_by(prompt_id=prompt_id, version=version)
        .first()
    )


def list_versions(db: Session, prompt_id: int) -> list[PromptVersion]:
    results = (
        db.query(PromptVersion)
        .options(joinedload(PromptVersion.created_by_ref))
        .filter_by(prompt_id=prompt_id)
        .order_by(PromptVersion.version.asc())
        .all()
    )
    return list(results) if results else []


def search_prompts_by_tags(
    db: Session,
    tags: list[str],
    mode: str = "or",
    project: str | None = None,
    allowed_projects: list[str] | None = None,
) -> list[Prompt]:
    """Return prompts matching tags with AND (all tags required) or OR (any tag) semantics."""
    normalized = normalize_tags(tags)
    if not normalized:
        return []

    query = db.query(Prompt)
    query = query.join(Prompt.project_ref).options(
        joinedload(Prompt.project_ref),
        joinedload(Prompt.created_by_ref),
        joinedload(Prompt.updated_by_ref),
        joinedload(Prompt.tags),
    )

    if allowed_projects is not None:
        if not allowed_projects:
            return []
        query = query.filter(Project.name.in_(allowed_projects))

    if project:
        query = query.filter(Project.name == normalize_project_name(project))

    if mode == "and":
        subq = (
            db.query(Prompt.id)
            .join(Prompt.tags)
            .filter(Tag.name.in_(normalized))
            .group_by(Prompt.id)
            .having(func.count(func.distinct(Tag.id)) == len(normalized))
        )
        query = query.filter(Prompt.id.in_(subq))
    else:
        # OR: at least one tag matches
        subq = db.query(Prompt.id).join(Prompt.tags).filter(Tag.name.in_(normalized))
        query = query.filter(Prompt.id.in_(subq))

    results = query.order_by(Project.name.asc(), Prompt.name.asc()).all()
    return list(results) if results else []
