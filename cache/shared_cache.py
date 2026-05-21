from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

import app_settings
from cache.ttl_cache import SharedTTLCache

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


_shared_cache = SharedTTLCache()


PROMPT_CACHE_TTL_SECONDS = 300
OPTIMIZATION_CACHE_TTL_SECONDS = 300

PROMPT_CACHE_PREFIX = "prompt:"
OPTIMIZATION_CACHE_PREFIX = "optimize:"


def clear_shared_cache(prefix: str | None = None) -> None:
    if _is_cache_enabled():
        _shared_cache.clear(prefix)


def delete_shared_cache_entry(key: str) -> None:
    if _is_cache_enabled():
        _shared_cache.delete(key)


def get_shared_cache_entry(key: str) -> Any | None:
    if _is_cache_enabled():
        return _shared_cache.get(key)
    return None


def set_shared_cache_entry(key: str, value: Any, ttl_seconds: int) -> None:
    if _is_cache_enabled():
        _shared_cache.set(key, value, ttl_seconds)


def cache_get_or_set(key: str, ttl_seconds: int, factory: Callable[[], Any]) -> Any:
    if not _is_cache_enabled():
        return factory()
    return _shared_cache.get_or_set(key, ttl_seconds, factory)


def get_hot_prompt_cache_entries(limit: int) -> list[tuple[str, Any]]:
    if not _is_cache_enabled():
        return []
    return _shared_cache.get_hot_entries(limit, prefix=PROMPT_CACHE_PREFIX)


def build_prompt_response_cache_key(project: str, name: str) -> str:
    payload = {
        "scope": "prompt-response",
        "project": _normalize_text(project).lower(),
        "name": _normalize_text(name),
    }
    return f"{PROMPT_CACHE_PREFIX}{_sha256_text(_canonical_json(payload))}"


def build_prompt_collection_cache_key(
    *,
    route: str,
    project: str | None = None,
    name: str | None = None,
    tag: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    tags: list[str] | None = None,
    mode: str | None = None,
    version: int | None = None,
    allowed_projects: list[str] | None = None,
) -> str:
    normalized_allowed_projects = sorted({_normalize_text(item).lower() for item in (allowed_projects or []) if _normalize_text(item)})
    payload = {
        "scope": "prompt-collection",
        "route": _normalize_text(route),
        "project": _normalize_text(project).lower() if project is not None else None,
        "name": _normalize_text(name) if name is not None else None,
        "tag": _normalize_text(tag).lower() if tag is not None else None,
        "limit": limit,
        "offset": offset,
        "tags": sorted({_normalize_text(item).lower() for item in (tags or []) if _normalize_text(item)}),
        "mode": _normalize_text(mode).lower() if mode is not None else None,
        "version": version,
        "allowed_projects": normalized_allowed_projects,
        "allowed_projects_all": allowed_projects is None,
    }
    return f"{PROMPT_CACHE_PREFIX}{_sha256_text(_canonical_json(payload))}"


def build_optimization_cache_key(fields: Mapping[str, str | None], config: Mapping[str, Any], backend_name: str) -> str:
    token = _normalize_text(config.get("effective_llm_api_token"))
    normalized_config = dict(config)
    normalized_config["effective_llm_api_token_fingerprint"] = _sha256_text(token) if token else ""
    normalized_config.pop("effective_llm_api_token", None)

    payload = {
        "scope": "prompt-optimization",
        "backend": _normalize_text(backend_name),
        "fields": {
            "role": _normalize_text(fields.get("role")),
            "task": _normalize_text(fields.get("task")),
            "context": _normalize_text(fields.get("context")),
            "constraints": _normalize_text(fields.get("constraints")),
            "output_format": _normalize_text(fields.get("output_format")),
            "examples": _normalize_text(fields.get("examples")),
        },
        "config": normalized_config,
    }
    return f"{OPTIMIZATION_CACHE_PREFIX}{_sha256_text(_canonical_json(payload))}"


def _is_cache_enabled() -> bool:
    return app_settings.get_bool("PROMPTMAN_CACHE_ENABLED", default=True)


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()
