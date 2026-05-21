from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import app_settings

from loguru import logger
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cache.shared_cache import PROMPT_CACHE_PREFIX, PROMPT_CACHE_TTL_SECONDS, get_hot_prompt_cache_entries, set_shared_cache_entry
from models import CacheRequest

_MAX_LRU_VALUE = 2**63 - 1
_DEFAULT_PERSIST_LIMIT = 100


def _cache_persistence_enabled() -> bool:
    return app_settings.get_bool("PROMPTMAN_CACHE_PERSISTENCE_ENABLED", default=True)


def _default_limit() -> int:
    return app_settings.get_int("PROMPTMAN_CACHE_PERSISTENCE_LIMIT", _DEFAULT_PERSIST_LIMIT)


def _serialize_payload(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _deserialize_payload(payload: str) -> Any:
    return json.loads(payload)


def _increment_lru(value: int | None) -> int:
    current = int(value or 0)
    if current >= _MAX_LRU_VALUE:
        return 0
    return current + 1


def _close_session(session: Session) -> None:
    session.close()


def persist_hot_prompt_cache_entries(db: Session, limit: int | None = None) -> int:
    if not _cache_persistence_enabled():
        return 0

    hot_entries = get_hot_prompt_cache_entries(limit or _default_limit())
    if not hot_entries:
        return 0

    persisted = 0
    try:
        for cache_key, value in hot_entries:
            serialized_payload = _serialize_payload(value)
            existing = db.scalar(select(CacheRequest).where(CacheRequest.cache_key == cache_key))
            if existing is None:
                try:
                    with db.begin_nested():
                        db.add(CacheRequest(cache_key=cache_key, payload=serialized_payload, lru=1))
                        db.flush()
                except IntegrityError:
                    # Concurrent persist already inserted this key; fall back to UPDATE.
                    existing = db.scalar(select(CacheRequest).where(CacheRequest.cache_key == cache_key))
                    if existing:
                        existing.payload = serialized_payload
                        existing.lru = _increment_lru(existing.lru)
            else:
                existing.payload = serialized_payload
                existing.lru = _increment_lru(existing.lru)
            persisted += 1

        db.commit()
        logger.info("cache.persistence.persisted count={} limit={}", persisted, limit or _default_limit())
        return persisted
    except Exception:
        db.rollback()
        logger.exception("cache.persistence.persist_failed")
        raise


def load_hot_prompt_cache_entries(db: Session, limit: int | None = None) -> list[tuple[str, Any]]:
    if not _cache_persistence_enabled():
        return []

    effective_limit = limit or _default_limit()
    rows = db.scalars(
        select(CacheRequest)
        .where(CacheRequest.cache_key.like(f"{PROMPT_CACHE_PREFIX}%"))
        .order_by(CacheRequest.lru.desc(), CacheRequest.id.asc())
        .limit(effective_limit)
    )
    entries: list[tuple[str, Any]] = []
    for row in rows:
        try:
            entries.append((row.cache_key, _deserialize_payload(row.payload)))
        except Exception:
            logger.warning("cache.persistence.skip_invalid_payload key={}", row.cache_key)
    return entries


def prewarm_hot_prompt_cache(db: Session, limit: int | None = None) -> int:
    if not _cache_persistence_enabled():
        return 0

    entries = load_hot_prompt_cache_entries(db, limit)
    for cache_key, payload in entries:
        set_shared_cache_entry(cache_key, payload, PROMPT_CACHE_TTL_SECONDS)

    logger.info("cache.persistence.prewarmed count={} limit={}", len(entries), limit or _default_limit())
    return len(entries)


def create_cache_persist_action(session_factory: Callable[[], Session], limit: int | None = None) -> Callable[[], None]:
    def action() -> None:
        db = session_factory()
        try:
            persist_hot_prompt_cache_entries(db, limit)
        finally:
            _close_session(db)

    return action


def create_cache_prewarm_action(session_factory: Callable[[], Session], limit: int | None = None) -> Callable[[], None]:
    def action() -> None:
        db = session_factory()
        try:
            prewarm_hot_prompt_cache(db, limit)
        finally:
            _close_session(db)

    return action
