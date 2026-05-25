from __future__ import annotations

from collections.abc import Mapping

from prompt_efficiency_analizer.similarity import compute_similarity

_STATIC_SEGMENTS: tuple[str, ...] = ("role", "task", "constraints", "output_format", "examples")


def estimate_cache_hit_score(previous_segments: Mapping[str, str], current_segments: Mapping[str, str]) -> float:
    """Estimate cache hit chance in range [0, 1] with heavier weight on stable prompt parts."""
    static_scores: list[float] = []
    for key in _STATIC_SEGMENTS:
        static_scores.append(
            compute_similarity(
                str(previous_segments.get(key, "") or ""),
                str(current_segments.get(key, "") or ""),
            )["hybrid"]
        )
    static_score = sum(static_scores) / len(static_scores) if static_scores else 0.0

    context_score = compute_similarity(
        str(previous_segments.get("context", "") or ""),
        str(current_segments.get("context", "") or ""),
    )["hybrid"]

    weighted = (0.78 * static_score) + (0.22 * context_score)
    if context_score < 0.40:
        weighted *= 0.85
    return max(0.0, min(weighted, 1.0))


def compute_prompt_stability_index(pairwise_hybrid: list[float], cache_hit_scores: list[float], context_drift_mean: float) -> float:
    """Compute Prompt Stability Index (PSI) in range [0, 100]."""
    mean_similarity = sum(pairwise_hybrid) / len(pairwise_hybrid) if pairwise_hybrid else 1.0
    mean_cache = sum(cache_hit_scores) / len(cache_hit_scores) if cache_hit_scores else 1.0
    drift_component = 1.0 - max(0.0, min(context_drift_mean, 1.0))
    psi = (0.45 * mean_similarity) + (0.35 * mean_cache) + (0.20 * drift_component)
    return round(max(0.0, min(psi, 1.0)) * 100.0, 2)
