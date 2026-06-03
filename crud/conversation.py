from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session, joinedload

from models import ConversationImport, ConversationMessage, ConversationThread, Project

from .common import normalize_project_name
from .project import get_or_create_project


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_thread(
    db: Session,
    *,
    project: str,
    title: str,
    source: str,
    actor_id: int | None,
) -> ConversationThread:
    project_record = get_or_create_project(db, project)
    now = _utcnow()
    thread = ConversationThread(
        project_ref=project_record,
        title=title.strip(),
        source=source.strip() or "manual",
        created_at=now,
        updated_at=now,
        created_by_id=actor_id,
    )
    db.add(thread)
    db.commit()
    db.refresh(thread)
    return thread


def list_threads(
    db: Session,
    *,
    project: str | None = None,
    allowed_projects: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ConversationThread]:
    query = db.query(ConversationThread).join(ConversationThread.project_ref).options(
        joinedload(ConversationThread.project_ref),
        joinedload(ConversationThread.created_by_ref),
    )
    if allowed_projects is not None:
        if not allowed_projects:
            return []
        query = query.filter(Project.name.in_(allowed_projects))
    if project:
        query = query.filter(Project.name == normalize_project_name(project))
    results = (
        query.order_by(ConversationThread.updated_at.desc(), ConversationThread.id.desc())
        .offset(max(0, offset))
        .limit(max(1, limit))
        .all()
    )
    return list(results)


def get_thread_by_id(db: Session, thread_id: int, *, allowed_projects: list[str] | None = None) -> ConversationThread | None:
    query = (
        db.query(ConversationThread)
        .join(ConversationThread.project_ref)
        .options(
            joinedload(ConversationThread.project_ref),
            joinedload(ConversationThread.created_by_ref),
        )
        .filter(ConversationThread.id == thread_id)
    )
    if allowed_projects is not None:
        if not allowed_projects:
            return None
        query = query.filter(Project.name.in_(allowed_projects))
    return query.first()


def delete_thread(db: Session, thread: ConversationThread) -> None:
    db.delete(thread)
    db.commit()


def list_messages(db: Session, thread_id: int) -> list[ConversationMessage]:
    rows = (
        db.query(ConversationMessage)
        .options(joinedload(ConversationMessage.created_by_ref))
        .filter(ConversationMessage.thread_id == thread_id)
        .order_by(ConversationMessage.seq_no.asc())
        .all()
    )
    return list(rows)


def append_messages(
    db: Session,
    *,
    thread: ConversationThread,
    messages: list[dict[str, Any]],
    actor_id: int | None,
) -> list[ConversationMessage]:
    existing_max = (
        db.query(ConversationMessage.seq_no)
        .filter(ConversationMessage.thread_id == thread.id)
        .order_by(ConversationMessage.seq_no.desc())
        .first()
    )
    next_seq = int(existing_max[0]) + 1 if existing_max else 1
    now = _utcnow()
    inserted: list[ConversationMessage] = []

    for item in messages:
        role = str(item.get("role", "user")).strip().lower()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        timestamp = item.get("timestamp")
        metadata = item.get("metadata")
        created_at = now
        if isinstance(timestamp, str) and timestamp.strip():
            try:
                created_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
            except ValueError:
                created_at = now
        row = ConversationMessage(
            thread_id=thread.id,
            seq_no=next_seq,
            role=role,
            content=content,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata is not None else None,
            created_at=created_at,
            created_by_id=actor_id,
        )
        db.add(row)
        inserted.append(row)
        next_seq += 1

    thread.updated_at = now
    db.add(thread)
    db.commit()

    for row in inserted:
        db.refresh(row)
    return inserted


def create_import_record(db: Session, *, thread_id: int, import_format: str, raw_payload: str) -> ConversationImport:
    record = ConversationImport(
        thread_id=thread_id,
        import_format=import_format,
        status="pending",
        raw_payload=raw_payload,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def set_import_completed(db: Session, record: ConversationImport, *, error_message: str | None = None) -> ConversationImport:
    record.status = "failed" if error_message else "completed"
    record.error_message = error_message
    record.completed_at = _utcnow()
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_import_record(db: Session, import_id: int) -> ConversationImport | None:
    return db.query(ConversationImport).filter(ConversationImport.id == import_id).first()
