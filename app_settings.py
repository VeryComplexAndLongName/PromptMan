"""
Global in-memory application settings.

These settings are mutable at runtime and are backed by the `global_config`
database table.  Low-level modules (cache, optimizer) read from this module
so they never need a database session at import/init time.

Lifecycle
---------
1. At import time this module initialises every setting from its hard-coded
   default (same values the old env-vars had).
2. At application startup `load_from_db(db)` is called once, overwriting the
   defaults with whatever is stored in the database.
3. The admin endpoint calls `apply(key, value)` to update both the in-memory
   state and the database row.

Settings that intentionally stay in environment variables (never here):
  DATABASE_URL, PROMPTMAN_KEY, PROMPTMAN_KEY_PREVIOUS,
  BOOTSTRAP_ADMIN_USERNAME, BOOTSTRAP_ADMIN_PASSWORD,
  LOG_LEVEL, SHOW_CONSOLE_SOURCE
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from loguru import logger

# ---------------------------------------------------------------------------
# Defaults – must be plain Python values, no DB / no os.getenv calls here
# ---------------------------------------------------------------------------

_DEFAULTS: dict[str, str] = {
    # cache
    "PROMPTMAN_CACHE_ENABLED": "true",
    "PROMPTMAN_CACHE_MAX_ENTRIES": "512",
    "PROMPTMAN_CACHE_PERSISTENCE_ENABLED": "true",
    "PROMPTMAN_CACHE_PERSISTENCE_LIMIT": "100",
    # plugins
    "PROMPTMAN_PLUGINS_SIGNED_ONLY": "false",
    # optimizer
    "OPTIMIZER_PROVIDER": "openai",
    "OPTIMIZER_MODEL": "gpt-4o-mini",
    "OPTIMIZER_BASE_URL": "",
    "OPTIMIZER_TIMEOUT_SECONDS": "120",
    "OPTIMIZER_API_TOKEN": "",
    "OPTIMIZER_BACKEND": "leo",
    "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
}

_ALL_KEYS: frozenset[str] = frozenset(_DEFAULTS)

_lock = Lock()
_store: dict[str, str] = dict(_DEFAULTS)


# ---------------------------------------------------------------------------
# Public read API (no imports from db/cache/optimizer needed)
# ---------------------------------------------------------------------------

def get(key: str, default: str = "") -> str:
    with _lock:
        return _store.get(key, default)


def get_bool(key: str, default: bool = False) -> bool:
    raw = get(key, "true" if default else "false").lower().strip()
    return raw not in {"false", "0", "no", "off"}


def get_int(key: str, default: int = 0) -> int:
    raw = get(key, str(default)).strip()
    return int(raw) if raw.lstrip("-").isdigit() else default


# ---------------------------------------------------------------------------
# Mutation – used at startup and by the admin endpoint
# ---------------------------------------------------------------------------

def apply(key: str, value: str) -> None:
    """Update a single setting in memory (does NOT write to DB)."""
    if key not in _ALL_KEYS:
        raise ValueError(f"Unknown setting key: {key!r}")
    with _lock:
        _store[key] = value


def all_settings() -> dict[str, str]:
    """Return a snapshot of all current settings (for the admin endpoint)."""
    with _lock:
        return dict(_store)


def load_from_db(db: Any) -> None:
    """
    Called once at startup.  Reads every known key from `global_config` and
    overwrites the in-memory defaults.  Unknown DB keys are ignored.
    Missing DB rows keep the default value and are inserted so the table stays
    complete.
    """
    from crud.common import get_global_config, set_global_config  # local import – DB layer

    loaded = 0
    for key, default_value in _DEFAULTS.items():
        db_value = get_global_config(db, key)
        if db_value is None:
            # Seed the row so operators can see and edit it
            set_global_config(db, key, default_value)
        else:
            apply(key, db_value)
            loaded += 1

    logger.info("app_settings.loaded count={} total_keys={}", loaded, len(_DEFAULTS))
