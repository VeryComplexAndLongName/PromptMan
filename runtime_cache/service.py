from __future__ import annotations

from threading import Lock
from typing import TYPE_CHECKING

from loguru import logger

import app_settings

from .backends import InMemoryCacheBackend, NoCacheBackend, RespCacheBackend

if TYPE_CHECKING:
    from .base import RuntimeCacheBackend

_runtime_backend: RuntimeCacheBackend | None = None
_backend_lock = Lock()


def _read_cache_backend_name() -> str:
    return app_settings.get("PROMPTMAN_RUNTIME_CACHE_BACKEND", "memory").strip().lower()


def _build_runtime_backend() -> RuntimeCacheBackend:
    if app_settings.get_bool("PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL", default=False):
        return NoCacheBackend()

    backend_name = _read_cache_backend_name()
    if backend_name == "none":
        return NoCacheBackend()
    if backend_name == "memory":
        return InMemoryCacheBackend()

    url = app_settings.get("PROMPTMAN_RUNTIME_CACHE_URL", "redis://127.0.0.1:6379/0").strip()
    namespace = app_settings.get("PROMPTMAN_RUNTIME_CACHE_NAMESPACE", "promptman")

    if backend_name in {"redis", "garnet"}:
        try:
            return RespCacheBackend(url=url, namespace=namespace)
        except Exception as exc:
            logger.warning("runtime_cache.backend_fallback backend={} error={} fallback=memory", backend_name, exc)
            return InMemoryCacheBackend()

    logger.warning("runtime_cache.unknown_backend name={} fallback=memory", backend_name)
    return InMemoryCacheBackend()


def get_runtime_cache() -> RuntimeCacheBackend:
    global _runtime_backend
    with _backend_lock:
        if _runtime_backend is None:
            _runtime_backend = _build_runtime_backend()
        return _runtime_backend


def reset_runtime_cache() -> RuntimeCacheBackend:
    global _runtime_backend
    with _backend_lock:
        _runtime_backend = _build_runtime_backend()
        return _runtime_backend
