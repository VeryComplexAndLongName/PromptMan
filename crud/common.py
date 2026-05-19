from datetime import UTC, datetime


def _utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return sorted({tag.strip().lower() for tag in tags if tag and tag.strip()})


def normalize_project_name(project: str) -> str:
    return project.strip()
