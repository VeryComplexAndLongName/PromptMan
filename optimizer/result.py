from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OptimizationResult:
    engine: str
    optimized_fields: dict[str, str | None]
    optimized_markdown: str
    notes: list[str]
    elapsed_seconds: float | None = None
