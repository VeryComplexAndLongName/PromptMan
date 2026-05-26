from __future__ import annotations

from collections.abc import Mapping
from io import StringIO

from rich.console import Console
from rich.table import Table


def build_markdown_report(result: Mapping[str, object]) -> str:
    """Build compact markdown report from analyzer output."""
    summary = result.get("summary", {}) if isinstance(result.get("summary"), dict) else {}
    transitions = result.get("transitions", []) if isinstance(result.get("transitions"), list) else []

    segment_volatility = summary.get("avg_segment_volatility")
    segment_volatility_line = "- Segment Volatility: -"
    if isinstance(segment_volatility, dict) and segment_volatility:
        joined = ", ".join(f"{key}={value}" for key, value in segment_volatility.items())
        segment_volatility_line = f"- Segment Volatility: {joined}"

    lines: list[str] = [
        "## Prompt Efficiency Report",
        f"- Source: {summary.get('source', 'unknown')}",
        f"- Prompt count: {summary.get('prompt_count', 0)}",
        f"- PSI: {summary.get('psi', 0)}",
        f"- Cache Hit Score: {summary.get('avg_cache_hit_score', 0)}",
        f"- Hybrid Similarity: {summary.get('avg_hybrid_similarity', 0)}",
        f"- Context Drift: {summary.get('context_drift_mean', 0)}",
        f"- Constraint Strictness: {summary.get('avg_constraint_strictness', 0)}",
        f"- Ambiguity Score: {summary.get('avg_ambiguity', 0)}",
        f"- Schema Compliance: {summary.get('avg_output_schema_compliance', 0)}",
        f"- Redundancy: {summary.get('avg_redundancy', 0)}",
        f"- Readability: {summary.get('avg_readability_difficulty', 0)}",
        f"- Conflict Risk: {summary.get('max_instruction_conflict_risk', 0)}",
        f"- Injection Surface: {summary.get('max_injection_surface_score', 0)}",
        f"- Placeholder Stability: {summary.get('avg_placeholder_stability', 0)}",
        segment_volatility_line,
        f"- Token Budget Safety: {summary.get('min_token_budget_safety_ratio', 0)}",
        f"- Context window tokens: {summary.get('context_window_tokens', 0)}",
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
                f"context_drift={item.get('context_drift', 0)}, "
                f"placeholder_stability={item.get('placeholder_stability', 0)}, "
                f"token_delta={item.get('token_delta', 0)}"
            )
            volatility = item.get("segment_volatility")
            if isinstance(volatility, dict) and volatility:
                joined = ", ".join(f"{key}={value}" for key, value in volatility.items())
                lines.append(f"  segment_volatility: {joined}")
            added = item.get("placeholder_added")
            removed = item.get("placeholder_removed")
            if isinstance(added, list) and added:
                lines.append(f"  placeholder_added: {', '.join(str(v) for v in added)}")
            if isinstance(removed, list) and removed:
                lines.append(f"  placeholder_removed: {', '.join(str(v) for v in removed)}")

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
    for key in (
        "source",
        "prompt_count",
        "psi",
        "avg_cache_hit_score",
        "avg_hybrid_similarity",
        "context_drift_mean",
        "avg_constraint_strictness",
        "avg_ambiguity",
        "avg_output_schema_compliance",
        "avg_redundancy",
        "avg_readability_difficulty",
        "max_instruction_conflict_risk",
        "max_injection_surface_score",
        "avg_placeholder_count",
        "avg_placeholder_stability",
        "min_token_budget_safety_ratio",
        "context_window_tokens",
    ):
        summary_table.add_row(key, str(summary.get(key, "-")))
    console.print(summary_table)

    transitions_table = Table(title="Prompt Transitions")
    transitions_table.add_column("From")
    transitions_table.add_column("To")
    transitions_table.add_column("Hybrid")
    transitions_table.add_column("Cache")
    transitions_table.add_column("Drift")
    transitions_table.add_column("Placeholders")
    transitions_table.add_column("Token delta")
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
                str(item.get("placeholder_stability", 0)),
                str(item.get("token_delta", 0)),
            )
    else:
        transitions_table.add_row("-", "-", "-", "-", "-", "-", "-")
    console.print(transitions_table)

    segment_volatility = summary.get("avg_segment_volatility")
    if isinstance(segment_volatility, dict) and segment_volatility:
        volatility_table = Table(title="Average Segment Volatility")
        volatility_table.add_column("Segment")
        volatility_table.add_column("Volatility")
        for key, value in segment_volatility.items():
            volatility_table.add_row(str(key), str(value))
        console.print(volatility_table)

    return output_buffer.getvalue()
