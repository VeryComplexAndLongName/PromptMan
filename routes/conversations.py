from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query

import auth as auth_service
import crud
from app_core.api_version import API_V1
from database import get_db, run_db_call
from runtime_cache import get_runtime_cache
from schemas import (
    ConversationAnalysisLogOut,
    ConversationAnalyzeOut,
    ConversationImportJsonRequest,
    ConversationImportOut,
    ConversationImportTextRequest,
    ConversationMessageOut,
    ConversationMessagesAppendRequest,
    ConversationThreadCreate,
    ConversationThreadOut,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from models import User

router = APIRouter(prefix=f"{API_V1}/conversations", tags=["Conversations"])
THREAD_ANALYSIS_LOG_ROOT = Path("logs") / "thread-analysis"


def _allowed_projects(current_user: User) -> list[str] | None:
    return auth_service.allowed_projects_for_user(current_user)


def _to_thread_out(db: Session, row) -> ConversationThreadOut:  # type: ignore[no-untyped-def]
    username = run_db_call(db, crud.resolve_audit_username, row.created_by_ref)
    created = row.created_at if row.created_at.tzinfo is not None else row.created_at.replace(tzinfo=UTC)
    updated = row.updated_at if row.updated_at.tzinfo is not None else row.updated_at.replace(tzinfo=UTC)
    return ConversationThreadOut(
        id=row.id,
        project=row.project_ref.name,
        title=row.title,
        source=row.source,
        created_at=created,
        updated_at=updated,
        created_by_username=username,
    )


def _parse_message_metadata(raw: str | None) -> dict[str, Any] | None:
    if raw is None or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _to_message_out(db: Session, row) -> ConversationMessageOut:  # type: ignore[no-untyped-def]
    created = row.created_at if row.created_at.tzinfo is not None else row.created_at.replace(tzinfo=UTC)
    username = run_db_call(db, crud.resolve_audit_username, row.created_by_ref)
    return ConversationMessageOut(
        id=row.id,
        seq_no=row.seq_no,
        role=row.role,
        content=row.content,
        timestamp=created,
        created_by_username=username,
        metadata=_parse_message_metadata(row.metadata_json),
    )


def _parse_text_chain(text: str, delimiter: str) -> list[dict[str, Any]]:
    normalized_delimiter = delimiter.strip() or "=== TURN ==="
    chunks = [item.strip() for item in text.split(normalized_delimiter) if item.strip()]
    messages: list[dict[str, Any]] = []
    for chunk in chunks:
        if ":" not in chunk:
            raise ValueError(f"Invalid turn format: {chunk[:40]}")
        role_raw, content_raw = chunk.split(":", 1)
        role = role_raw.strip().lower()
        if role not in {"user", "assistant", "system", "tool"}:
            raise ValueError(f"Unsupported role '{role}'")
        content = content_raw.strip()
        if not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


def _invalidate_conversation_cache(thread_id: int | None = None) -> None:
    cache = get_runtime_cache()
    cache.clear_prefix("conversations:list:")
    if thread_id is not None:
        cache.delete(f"conversations:thread:{thread_id}")
        cache.delete(f"conversations:messages:{thread_id}")


def _build_thread_analysis_out(thread_id: int, rows: list[Any]) -> ConversationAnalyzeOut:
    counters = {"user": 0, "assistant": 0, "system": 0, "tool": 0}
    total_chars = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None

    for row in rows:
        role = row.role.strip().lower()
        if role in counters:
            counters[role] += 1
        total_chars += len(row.content or "")
        created_at = row.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if started_at is None or created_at < started_at:
            started_at = created_at
        if ended_at is None or created_at > ended_at:
            ended_at = created_at

    return ConversationAnalyzeOut(
        thread_id=thread_id,
        turns=len(rows),
        user_turns=counters["user"],
        assistant_turns=counters["assistant"],
        system_turns=counters["system"],
        tool_turns=counters["tool"],
        total_chars=total_chars,
        started_at=started_at,
        ended_at=ended_at,
    )


def _format_thread_analysis_log(db: Session, thread, rows: list[Any], analysis: ConversationAnalyzeOut, current_user: User) -> str:  # type: ignore[no-untyped-def]
    generated_at = datetime.now(UTC)
    role_counts = {
        "user": analysis.user_turns,
        "assistant": analysis.assistant_turns,
        "system": analysis.system_turns,
        "tool": analysis.tool_turns,
    }
    lines = [
        "PromptMan Thread Analysis Log",
        f"Generated at (UTC): {generated_at.isoformat()}",
        f"Requested by: {current_user.username}",
        f"Thread ID: {thread.id}",
        f"Project: {thread.project_ref.name}",
        f"Title: {thread.title}",
        f"Source: {thread.source}",
        f"Turns: {analysis.turns}",
        "Role counts:",
        f"- user: {role_counts['user']}",
        f"- assistant: {role_counts['assistant']}",
        f"- system: {role_counts['system']}",
        f"- tool: {role_counts['tool']}",
        f"Total chars: {analysis.total_chars}",
        f"Started at: {analysis.started_at.isoformat() if analysis.started_at else ''}",
        f"Ended at: {analysis.ended_at.isoformat() if analysis.ended_at else ''}",
        "",
        "Messages:",
    ]

    for row in rows:
        created_at = row.created_at if row.created_at.tzinfo is not None else row.created_at.replace(tzinfo=UTC)
        username = run_db_call(db, crud.resolve_audit_username, row.created_by_ref)
        lines.append(f"[{row.seq_no}] {created_at.isoformat()} | {row.role} | {username or 'unknown'}")
        lines.append(row.content or "")
        lines.append("")

    lines.extend([
        "Analysis JSON:",
        json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False, indent=2),
    ])
    return "\n".join(lines).rstrip() + "\n"


def _write_thread_analysis_log(thread_id: int, log_text: str) -> Path:
    log_dir = THREAD_ANALYSIS_LOG_ROOT / f"thread_{thread_id}"
    log_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    log_path = log_dir / f"analysis_{generated_at}.log"
    log_path.write_text(log_text, encoding="utf-8")
    latest_path = log_dir / "latest.log"
    latest_path.write_text(log_text, encoding="utf-8")
    return log_path


def _build_and_store_thread_analysis_log(
    db: Session,
    thread,
    rows: list[Any],
    analysis: ConversationAnalyzeOut,
    current_user: User,
) -> ConversationAnalysisLogOut:  # type: ignore[no-untyped-def]
    log_text = _format_thread_analysis_log(db, thread, rows, analysis, current_user)
    log_path = _write_thread_analysis_log(thread.id, log_text)
    return ConversationAnalysisLogOut(
        thread_id=thread.id,
        generated_at=datetime.now(UTC),
        log_path=str(log_path),
        analysis=analysis,
        log_text=log_text,
    )


@router.post("/threads", response_model=ConversationThreadOut)
def create_thread(
    payload: ConversationThreadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.require_write_access),
) -> ConversationThreadOut:
    auth_service.ensure_project_access(current_user, payload.project)
    thread = run_db_call(
        db,
        crud.create_thread,
        project=payload.project,
        title=payload.title,
        source=payload.source,
        actor_id=current_user.id,
    )
    _invalidate_conversation_cache(thread.id)
    return _to_thread_out(db, thread)


@router.get("/threads", response_model=list[ConversationThreadOut])
def list_threads(
    project: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[ConversationThreadOut]:
    allowed_projects = _allowed_projects(current_user)
    cache_key = f"conversations:list:{project}:{limit}:{offset}:{allowed_projects}"
    cache = get_runtime_cache()
    cached = cache.get_json(cache_key)
    if cached and isinstance(cached.get("threads"), list):
        return [ConversationThreadOut(**item) for item in cached["threads"]]

    rows = run_db_call(
        db,
        crud.list_threads,
        project=project,
        allowed_projects=allowed_projects,
        limit=limit,
        offset=offset,
    )
    payload = [_to_thread_out(db, row).model_dump(mode="json") for row in rows]
    cache.set_json(cache_key, {"threads": payload}, ttl_seconds=30)
    return [ConversationThreadOut(**item) for item in payload]


@router.get("/threads/{thread_id}", response_model=ConversationThreadOut)
def get_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> ConversationThreadOut:
    allowed_projects = _allowed_projects(current_user)
    cache_key = f"conversations:thread:{thread_id}"
    cache = get_runtime_cache()
    cached = cache.get_json(cache_key)
    if cached:
        return ConversationThreadOut(**cached)

    row = run_db_call(db, crud.get_thread_by_id, thread_id, allowed_projects=allowed_projects)
    if not row:
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    out = _to_thread_out(db, row)
    cache.set_json(cache_key, out.model_dump(mode="json"), ttl_seconds=30)
    return out


@router.delete("/threads/{thread_id}", status_code=204)
def delete_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.require_write_access),
) -> None:
    row = run_db_call(db, crud.get_thread_by_id, thread_id, allowed_projects=_allowed_projects(current_user))
    if not row:
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    auth_service.ensure_project_access(current_user, row.project_ref.name)
    run_db_call(db, crud.delete_thread, row)
    _invalidate_conversation_cache(thread_id)


@router.post("/threads/{thread_id}/messages", response_model=list[ConversationMessageOut])
def append_messages(
    thread_id: int,
    payload: ConversationMessagesAppendRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.require_write_access),
) -> list[ConversationMessageOut]:
    thread = run_db_call(db, crud.get_thread_by_id, thread_id, allowed_projects=_allowed_projects(current_user))
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation thread not found")
    auth_service.ensure_project_access(current_user, thread.project_ref.name)
    inserted = run_db_call(db, crud.append_messages, thread=thread, messages=[m.model_dump() for m in payload.messages], actor_id=current_user.id)
    _invalidate_conversation_cache(thread_id)
    return [_to_message_out(db, row) for row in inserted]


@router.get("/threads/{thread_id}/messages", response_model=list[ConversationMessageOut])
def list_messages(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> list[ConversationMessageOut]:
    thread = run_db_call(db, crud.get_thread_by_id, thread_id, allowed_projects=_allowed_projects(current_user))
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation thread not found")

    cache_key = f"conversations:messages:{thread_id}"
    cache = get_runtime_cache()
    cached = cache.get_json(cache_key)
    if cached and isinstance(cached.get("messages"), list):
        return [ConversationMessageOut(**item) for item in cached["messages"]]

    rows = run_db_call(db, crud.list_messages, thread_id)
    payload = [_to_message_out(db, row).model_dump(mode="json") for row in rows]
    cache.set_json(cache_key, {"messages": payload}, ttl_seconds=20)
    return [ConversationMessageOut(**item) for item in payload]


@router.post("/import/json", response_model=ConversationImportOut)
def import_json(
    payload: ConversationImportJsonRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.require_write_access),
) -> ConversationImportOut:
    auth_service.ensure_project_access(current_user, payload.project)
    thread = run_db_call(
        db,
        crud.create_thread,
        project=payload.project,
        title=payload.title,
        source="import-json",
        actor_id=current_user.id,
    )
    import_record = run_db_call(
        db,
        crud.create_import_record,
        thread_id=thread.id,
        import_format="json",
        raw_payload=json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
    )

    error_message: str | None = None
    try:
        run_db_call(db, crud.append_messages, thread=thread, messages=[m.model_dump() for m in payload.messages], actor_id=current_user.id)
    except Exception as exc:  # pragma: no cover
        error_message = str(exc)

    import_record = run_db_call(db, crud.set_import_completed, import_record, error_message=error_message)
    _invalidate_conversation_cache(thread.id)
    return ConversationImportOut(
        import_id=import_record.id,
        thread_id=thread.id,
        status=import_record.status,
        format=import_record.import_format,
        error_message=import_record.error_message,
    )


@router.post("/import/text", response_model=ConversationImportOut)
def import_text(
    payload: ConversationImportTextRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.require_write_access),
) -> ConversationImportOut:
    auth_service.ensure_project_access(current_user, payload.project)
    thread = run_db_call(
        db,
        crud.create_thread,
        project=payload.project,
        title=payload.title,
        source="import-text",
        actor_id=current_user.id,
    )
    import_record = run_db_call(
        db,
        crud.create_import_record,
        thread_id=thread.id,
        import_format="text",
        raw_payload=payload.text,
    )

    error_message: str | None = None
    try:
        parsed_messages = _parse_text_chain(payload.text, payload.delimiter)
        run_db_call(db, crud.append_messages, thread=thread, messages=parsed_messages, actor_id=current_user.id)
    except Exception as exc:
        error_message = str(exc)

    import_record = run_db_call(db, crud.set_import_completed, import_record, error_message=error_message)
    _invalidate_conversation_cache(thread.id)
    return ConversationImportOut(
        import_id=import_record.id,
        thread_id=thread.id,
        status=import_record.status,
        format=import_record.import_format,
        error_message=import_record.error_message,
    )


@router.get("/import/{import_id}", response_model=ConversationImportOut)
def get_import_status(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(auth_service.get_current_user),
) -> ConversationImportOut:
    row = run_db_call(db, crud.get_import_record, import_id)
    if not row:
        raise HTTPException(status_code=404, detail="Import record not found")
    return ConversationImportOut(
        import_id=row.id,
        thread_id=row.thread_id,
        status=row.status,
        format=row.import_format,
        error_message=row.error_message,
    )


@router.post("/analyze/{thread_id}", response_model=ConversationAnalyzeOut)
def analyze_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> ConversationAnalyzeOut:
    thread = run_db_call(db, crud.get_thread_by_id, thread_id, allowed_projects=_allowed_projects(current_user))
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation thread not found")

    rows = run_db_call(db, crud.list_messages, thread_id)
    analysis = _build_thread_analysis_out(thread_id, rows)
    _build_and_store_thread_analysis_log(db, thread, rows, analysis, current_user)
    return analysis


@router.get("/threads/{thread_id}/analysis-log", response_model=ConversationAnalysisLogOut)
def get_thread_analysis_log(
    thread_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
) -> ConversationAnalysisLogOut:
    thread = run_db_call(db, crud.get_thread_by_id, thread_id, allowed_projects=_allowed_projects(current_user))
    if not thread:
        raise HTTPException(status_code=404, detail="Conversation thread not found")

    rows = run_db_call(db, crud.list_messages, thread_id)
    analysis = _build_thread_analysis_out(thread_id, rows)
    return _build_and_store_thread_analysis_log(db, thread, rows, analysis, current_user)
