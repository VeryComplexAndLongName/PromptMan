from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class RuntimeCacheBackend(ABC):
    @abstractmethod
    def get_json(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def set_json(self, key: str, value: dict[str, Any], ttl_seconds: int | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear_prefix(self, prefix: str) -> None:
        raise NotImplementedError
