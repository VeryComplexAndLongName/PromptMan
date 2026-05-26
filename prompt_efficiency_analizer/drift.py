from __future__ import annotations

from collections.abc import Iterable


def _word_set(value: str) -> set[str]:
    return {word for word in (value or "").lower().split() if word}


def context_change_ratio(previous_context: str, current_context: str) -> float:
    """Compute context drift ratio in range [0, 1] based on word-set symmetric difference."""
    left = _word_set(previous_context)
    right = _word_set(current_context)
    if not left and not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left ^ right) / len(union)


def analyze_context_drift(context_series: Iterable[str]) -> dict[str, object]:
    """Analyze context drift between consecutive context values."""
    values = list(context_series)
    if len(values) < 2:
        return {"pairs": [], "mean": 0.0, "max": 0.0}

    pairs: list[float] = []
    for index in range(1, len(values)):
        pairs.append(context_change_ratio(values[index - 1], values[index]))

    mean_value = sum(pairs) / len(pairs) if pairs else 0.0
    max_value = max(pairs) if pairs else 0.0
    return {
        "pairs": [round(value, 4) for value in pairs],
        "mean": round(mean_value, 4),
        "max": round(max_value, 4),
    }
