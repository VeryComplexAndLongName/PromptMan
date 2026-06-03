from __future__ import annotations

import json
import time
from typing import Any

from loguru import logger

from .base import RuntimeCacheBackend


class NoCacheBackend(RuntimeCacheBackend):
    def get_json(self, key: str) -> dict[str, Any] | None:
        return None

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        return None

    def delete(self, key: str) -> None:
        return None

    def clear_prefix(self, prefix: str) -> None:
        return None


class InMemoryCacheBackend(RuntimeCacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, tuple[dict[str, Any], float | None]] = {}

    def get_json(self, key: str) -> dict[str, Any] | None:
        row = self._store.get(key)
        if row is None:
            return None
        payload, expires_at = row
        if expires_at is not None and expires_at <= time.time():
            self._store.pop(key, None)
            return None
        return payload

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        expires_at: float | None = None
        if ttl_seconds is not None:
            expires_at = time.time() + max(1, ttl_seconds)
        self._store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear_prefix(self, prefix: str) -> None:
        for key in list(self._store.keys()):
            if key.startswith(prefix):
                self._store.pop(key, None)


class RespCacheBackend(RuntimeCacheBackend):
    def __init__(self, url: str, namespace: str = "promptman", socket_timeout_seconds: float = 1.0) -> None:
        self.namespace = namespace.strip() or "promptman"
        self._client = self._create_client(url, socket_timeout_seconds)

    def _create_client(self, url: str, socket_timeout_seconds: float):  # type: ignore[no-untyped-def]
        try:
            from redis import Redis
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("redis package is required for redis/garnet cache backends") from exc
        timeout = max(0.05, float(socket_timeout_seconds))
        client = Redis.from_url(
            url,
            socket_timeout=timeout,
            socket_connect_timeout=min(timeout, 1.0),
            decode_responses=True,
            retry_on_timeout=False,
            health_check_interval=30,
        )
        client.ping()
        return client

    def _ns(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get_json(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self._client.get(self._ns(key))
        except Exception as exc:
            logger.warning("runtime_cache.get.failed key={} error={}", key, exc)
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("runtime_cache.invalid_json key={}", key)
            return None
        return payload if isinstance(payload, dict) else None

    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        encoded = json.dumps(value, ensure_ascii=False)
        namespaced = self._ns(key)
        try:
            if ttl_seconds is None:
                self._client.set(namespaced, encoded)
            else:
                self._client.setex(namespaced, max(1, ttl_seconds), encoded)
        except Exception as exc:
            logger.warning("runtime_cache.set.failed key={} error={}", key, exc)

    def delete(self, key: str) -> None:
        try:
            self._client.delete(self._ns(key))
        except Exception as exc:
            logger.warning("runtime_cache.delete.failed key={} error={}", key, exc)

    def clear_prefix(self, prefix: str) -> None:
        pattern = self._ns(f"{prefix}*")
        cursor = 0
        try:
            while True:
                cursor, keys = self._client.scan(cursor=cursor, match=pattern, count=200)
                if keys:
                    self._client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning("runtime_cache.clear_prefix.failed prefix={} error={}", prefix, exc)
