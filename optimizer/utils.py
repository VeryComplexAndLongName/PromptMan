from __future__ import annotations

import json
import re
from queue import Empty, Queue
from threading import Thread
from typing import Any

from optimizer.errors import BackendOperationTimeoutError


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        raw = value
    elif isinstance(value, (dict, list)):
        raw = json.dumps(value, ensure_ascii=False)
    else:
        raw = str(value)
    trimmed = " ".join(raw.split())
    return trimmed or None


def _build_full_prompt(fields: dict[str, str | None]) -> str:
    parts: list[str] = []
    if fields.get("role"):
        parts.append(f"Role: {fields['role']}")
    parts.append(f"Task: {fields['task']}")
    if fields.get("constraints"):
        parts.append(f"Constraints: {fields['constraints']}")
    if fields.get("output_format"):
        parts.append(f"Output format: {fields['output_format']}")
    if fields.get("examples"):
        parts.append(f"Examples: {fields['examples']}")
    if fields.get("context"):
        parts.append(f"Context: {fields['context']}")
    return "\n\n".join(parts)


def _heuristic_improve(fields: dict[str, str | None]) -> dict[str, str | None]:
    optimized = {
        "role": _normalize_text(fields.get("role")),
        "task": _normalize_text(fields.get("task")) or "",
        "context": _normalize_text(fields.get("context")),
        "constraints": _normalize_text(fields.get("constraints")),
        "output_format": _normalize_text(fields.get("output_format")),
        "examples": _normalize_text(fields.get("examples")),
    }

    if optimized["task"] and not optimized["task"].rstrip().endswith((".", "?", "!")):
        optimized["task"] = optimized["task"].rstrip() + "."

    return optimized


def _extract_prefixed_section(text: str, key: str) -> str | None:
    pattern = re.compile(rf"(?im)^\s*{re.escape(key)}\s*:\s*(.+)$")
    match = pattern.search(text)
    if not match:
        return None
    return _normalize_text(match.group(1))


def _build_backend_failure_note(exc: Exception, timeout_seconds: int, elapsed_seconds: float) -> str:
    rounded_elapsed = round(max(0.0, elapsed_seconds), 2)
    if isinstance(exc, BackendOperationTimeoutError):
        return (
            f"Backend optimization timed out after {exc.timeout_seconds}s "
            f"(elapsed ~{rounded_elapsed}s, operation={exc.operation_name})."
        )
    if isinstance(exc, TimeoutError):
        return (
            f"Backend/provider reported timeout after ~{rounded_elapsed}s "
            f"(configured timeout={int(timeout_seconds)}s): {exc}"
        )
    return f"Backend optimization failed after ~{rounded_elapsed}s: {exc}"


def _parse_structured_response(raw_text: str, fallback: dict[str, str | None]) -> dict[str, str | None]:
    role = _extract_prefixed_section(raw_text, "Role") or fallback.get("role")
    task = _extract_prefixed_section(raw_text, "Task")
    context = _extract_prefixed_section(raw_text, "Context") or fallback.get("context")
    constraints = _extract_prefixed_section(raw_text, "Constraints") or fallback.get("constraints")
    output_format = _extract_prefixed_section(raw_text, "Output format") or fallback.get("output_format")
    examples = _extract_prefixed_section(raw_text, "Examples") or fallback.get("examples")

    if not task:
        task = _normalize_text(raw_text) or fallback.get("task") or ""

    return _heuristic_improve(
        {
            "role": role,
            "task": task,
            "context": context,
            "constraints": constraints,
            "output_format": output_format,
            "examples": examples,
        }
    )


def _run_with_timeout(func: Any, timeout_seconds: int, operation_name: str) -> Any:
    result_queue: Queue[tuple[str, Any]] = Queue(maxsize=1)

    def _target() -> None:
        try:
            result_queue.put(("ok", func()))
        except Exception as exc:  # pragma: no cover - passthrough for worker-thread exceptions
            result_queue.put(("error", exc))

    worker = Thread(target=_target, daemon=True)
    worker.start()

    try:
        status, payload = result_queue.get(timeout=max(1, int(timeout_seconds)))
    except Empty as exc:
        raise BackendOperationTimeoutError(operation_name, int(timeout_seconds)) from exc

    if status == "error":
        raise payload
    return payload
