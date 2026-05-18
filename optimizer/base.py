from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from optimizer.result import OptimizationResult


class PromptOptimizerBackend(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def optimize(self, fields: dict[str, str | None], config: dict[str, Any]) -> OptimizationResult:
        raise NotImplementedError

    @abstractmethod
    def list_models(
        self,
        provider: str,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 5,
        api_token: str | None = None,
        config_override: dict[str, Any] | None = None,
    ) -> list[str]:
        raise NotImplementedError
