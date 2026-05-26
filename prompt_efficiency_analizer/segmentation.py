from __future__ import annotations

from collections.abc import Mapping

SEGMENT_ORDER: tuple[str, ...] = ("role", "task", "constraints", "output_format", "examples", "context")
SEGMENT_TITLES: dict[str, str] = {
    "role": "Role",
    "task": "Task",
    "constraints": "Constraints",
    "output_format": "Output format",
    "examples": "Examples",
    "context": "Context",
}


def segment_prompt(prompt: Mapping[str, object]) -> dict[str, str]:
    """Normalize PromptMan-like payload into canonical prompt segments."""
    segments: dict[str, str] = {}
    for key in SEGMENT_ORDER:
        value = prompt.get(key)
        segments[key] = str(value or "").strip()
    return segments


def compose_prompt_text(segments: Mapping[str, str]) -> str:
    """Compose segmented prompt into a stable markdown-like textual representation."""
    parts: list[str] = []
    for key in SEGMENT_ORDER:
        value = str(segments.get(key, "") or "").strip()
        if not value:
            continue
        title = SEGMENT_TITLES.get(key, key)
        parts.append(f"{title}: {value}")
    return "\n\n".join(parts)


def segment_presence(segments: Mapping[str, str]) -> dict[str, bool]:
    """Return boolean map showing which canonical segments are present."""
    return {key: bool(str(segments.get(key, "") or "").strip()) for key in SEGMENT_ORDER}
