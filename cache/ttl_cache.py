from __future__ import annotations

import os
import time
from copy import deepcopy
from dataclasses import dataclass
from threading import Event, RLock
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def _default_max_entries() -> int:
    raw_value = os.getenv("PROMPTMAN_CACHE_MAX_ENTRIES", "512").strip()
    return max(1, int(raw_value)) if raw_value.isdigit() else 512


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float
    last_access_seq: int


@dataclass
class _InflightState:
    event: Event
    value: Any | None = None
    error: BaseException | None = None


class SharedTTLCache:
    def __init__(self, *, max_entries: int | None = None) -> None:
        self._entries: dict[str, _CacheEntry] = {}
        self._inflight: dict[str, _InflightState] = {}
        self._lock = RLock()
        self._sequence = 0
        self._max_entries = max_entries if max_entries is not None else _default_max_entries()

    def _next_sequence_unlocked(self) -> int:
        self._sequence += 1
        return self._sequence

    def _prune_expired_unlocked(self, now: float, *, sample_limit: int = 16) -> None:
        for key in list(self._entries.keys())[:sample_limit]:
            entry = self._entries.get(key)
            if entry is not None and entry.expires_at <= now:
                self._entries.pop(key, None)

    def _evict_lru_unlocked(self) -> None:
        while len(self._entries) > self._max_entries:
            lru_key = min(self._entries.items(), key=lambda item: item[1].last_access_seq)[0]
            self._entries.pop(lru_key, None)

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None

            entry.last_access_seq = self._next_sequence_unlocked()
            return deepcopy(entry.value)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        ttl = max(1, int(ttl_seconds))
        now = time.monotonic()
        expires_at = now + ttl

        with self._lock:
            self._prune_expired_unlocked(now)
            self._entries[key] = _CacheEntry(
                value=deepcopy(value),
                expires_at=expires_at,
                last_access_seq=self._next_sequence_unlocked(),
            )
            self._evict_lru_unlocked()

    def delete(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)

    def clear(self, prefix: str | None = None) -> None:
        with self._lock:
            if prefix is None:
                self._entries.clear()
                self._inflight.clear()
                return

            for key in list(self._entries.keys()):
                if key.startswith(prefix):
                    self._entries.pop(key, None)
            for key in list(self._inflight.keys()):
                if key.startswith(prefix):
                    self._inflight.pop(key, None)

    def get_or_set(self, key: str, ttl_seconds: int, factory: Callable[[], Any]) -> Any:
        ttl = max(1, int(ttl_seconds))

        with self._lock:
            entry = self._entries.get(key)
            now = time.monotonic()
            if entry is not None:
                if entry.expires_at > now:
                    entry.last_access_seq = self._next_sequence_unlocked()
                    return deepcopy(entry.value)
                self._entries.pop(key, None)

            inflight = self._inflight.get(key)
            if inflight is None:
                inflight = _InflightState(event=Event())
                self._inflight[key] = inflight
                owner = True
            else:
                owner = False

        if not owner:
            inflight.event.wait()
            if inflight.error is not None:
                raise inflight.error
            if inflight.value is not None:
                return deepcopy(inflight.value)
            return self.get(key)

        try:
            value = factory()
        except BaseException as exc:
            with self._lock:
                inflight.error = exc
                self._inflight.pop(key, None)
                inflight.event.set()
            raise

        with self._lock:
            now = time.monotonic()
            self._entries[key] = _CacheEntry(
                value=deepcopy(value),
                expires_at=now + ttl,
                last_access_seq=self._next_sequence_unlocked(),
            )
            self._prune_expired_unlocked(now)
            self._evict_lru_unlocked()
            inflight.value = deepcopy(value)
            self._inflight.pop(key, None)
            inflight.event.set()
        return deepcopy(value)
