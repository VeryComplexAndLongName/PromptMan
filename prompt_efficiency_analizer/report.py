from __future__ import annotations

from collections.abc import Mapping
from io import StringIO

from rich.console import Console
from rich.table import Table


def build_markdown_report(result: Mapping[str, object]) -> str:
    """Build compact markdown report from analyzer output."""
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    transitions = result.get("transitions", []) if isinstance(result.get("transitions"), list) else []

    lines: list[str] = [
        "## Prompt Efficiency Report",
        f"- Source: {summary.get('source', 'unknown')}",
        f"- Prompt count: {summary.get('prompt_count', 0)}",
        f"- PSI: {summary.get('psi', 0)}",
        f"- Avg cache hit score: {summary.get('avg_cache_hit_score', 0)}",
        f"- Avg similarity (hybrid): {summary.get('avg_hybrid_similarity', 0)}",
        f"- Mean context drift: {summary.get('context_drift_mean', 0)}",
        "",
        "### Transitions",
    ]

    if not transitions:
        lines.append("- Not enough prompts for transition analysis.")
    else:
        for item in transitions:
            if not isinstance(item, dict):
                continue
            lines.append(
                "- "
                f"{item.get('from_label', '?')} -> {item.get('to_label', '?')}: "
                f"hybrid={item.get('hybrid_similarity', 0)}, "
                f"cache={item.get('cache_hit_score', 0)}, "
                f"context_drift={item.get('context_drift', 0)}"
            )

    return "\n".join(lines)


def build_rich_report_text(result: Mapping[str, object]) -> str:
    """Render analyzer output as plain text via rich for terminal-friendly diagnostics."""
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    transitions = result.get("transitions", []) if isinstance(result.get("transitions"), list) else []

    output_buffer = StringIO()
    console = Console(record=True, file=output_buffer, force_terminal=False, color_system=None, width=120)

    summary_table = Table(title="Prompt Efficiency Summary")
    summary_table.add_column("Metric")
    summary_table.add_column("Value")
    for key in ("source", "prompt_count", "psi", "avg_cache_hit_score", "avg_hybrid_similarity", "context_drift_mean"):
        summary_table.add_row(key, str(summary.get(key, "-")))
    console.print(summary_table)

    transitions_table = Table(title="Prompt Transitions")
    transitions_table.add_column("From")
    transitions_table.add_column("To")
    transitions_table.add_column("Hybrid")
    transitions_table.add_column("Cache")
    transitions_table.add_column("Drift")
    if transitions:
        for item in transitions:
            if not isinstance(item, dict):
                continue
            transitions_table.add_row(
                str(item.get("from_label", "?")),
                str(item.get("to_label", "?")),
                str(item.get("hybrid_similarity", 0)),
                str(item.get("cache_hit_score", 0)),
                str(item.get("context_drift", 0)),
            )
    else:
        transitions_table.add_row("-", "-", "-", "-", "-")
    console.print(transitions_table)

    return output_buffer.getvalue()
