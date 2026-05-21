from datetime import UTC, datetime
from sqlalchemy.orm import Session
from models.models import GlobalConfig


def _utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    return sorted({tag.strip().lower() for tag in tags if tag and tag.strip()})


def normalize_project_name(project: str) -> str:
    return project.strip()


def get_global_config(db: Session, key: str) -> str | None:
    record = db.query(GlobalConfig).filter(GlobalConfig.key == key).first()
    return record.value if record else None


def set_global_config(db: Session, key: str, value: str) -> None:
    record = db.query(GlobalConfig).filter(GlobalConfig.key == key).first()
    if record:
        record.value = value
    else:
        record = GlobalConfig(key=key, value=value)
        db.add(record)
    db.commit()
