from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from plugin_engine import (
    PluginEndpointConfig,
    PluginLifecycleContext,
    PluginManifest,
    PluginRunContext,
    PluginUiControl,
    PluginUiOption,
)

from plugins.efficiency_analizer_ui._prompt_efficiency_analizer import PromptEfficiencyAnalyzer


_METRIC_GLOSSARY: dict[str, str] = {
    "PSI": "Prompt Stability Index — overall structural consistency of the prompt across all versions (0..1, higher = more stable)",
    "Cache Hit Score": "Estimated probability that a caching layer would serve this prompt from its cache without re-execution (0..1)",
    "Hybrid Similarity": "Weighted blend of Levenshtein, Jaro-Winkler and Jaccard similarity between adjacent prompt versions (0..1)",
    "Context Drift": "Degree of semantic shift in the context segment across consecutive versions (0..1, lower = more stable)",
    "Constraint Strictness": "How prescriptive and binding the constraints section is — strict rules score higher (0..1)",
    "Ambiguity Score": "Level of vagueness and open-ended phrasing detected in the prompt (0..1, lower = clearer)",
    "Injection Surface": "Estimated exposure to prompt-injection attacks — open-ended input slots raise this score (0..1, lower = safer)",
    "Segment Volatility": "Proportion of prompt segments (role/task/context/…) that changed between versions (0..1)",
    "Placeholder Stability": "Consistency of named placeholder variables (e.g. {name}) across all versions (0..1)",
    "Readability": "Flesch-Kincaid-style reading ease estimate for the prompt text (0..1, higher = easier to read)",
    "Token Budget Safety": "Estimated margin before the context-window token limit is reached (0..1, higher = more headroom)",
    "Redundancy": "Presence of duplicate or near-duplicate phrases inside a single version (0..1, lower = less redundant)",
    "Schema Compliance": "How well the output_format section defines a machine-parseable structure (0..1)",
    "Conflict Risk": "Probability of contradictory instructions or constraints within a version (0..1, lower = less risk)",
    "Levenshtein": "Edit-distance-based similarity — counts minimum character insertions, deletions and substitutions (0..1)",
    "Jaro-Winkler": "String similarity metric that rewards common prefixes; works well on short strings (0..1)",
    "Jaccard": "Set-based similarity of word tokens — intersection / union of unique words (0..1)",
    "Token Count": "Number of tokens in the prompt as counted by the selected tiktoken encoding",
    "Prompt Stability Index": "PSI — overall structural consistency of the prompt across all versions (0..1, higher = more stable)",
}


def _annotate_metric_terms(text: str) -> str:
    """Wrap known metric names in <abbr title='...'> for Report tab tooltips."""
    terms = sorted(_METRIC_GLOSSARY, key=len, reverse=True)
    term_lookup = {term.lower(): term for term in terms}
    pattern = re.compile(rf"(?<![\w])({'|'.join(re.escape(term) for term in terms)})(?![\w])", flags=re.IGNORECASE)

    def _replace_metric(match: re.Match[str]) -> str:
        matched_text = match.group(1)
        canonical = term_lookup.get(matched_text.lower())
        if not canonical:
            return matched_text
        description = _METRIC_GLOSSARY[canonical]
        safe_desc = description.replace('"', "&quot;")
        return f'<abbr title="{safe_desc}">{matched_text}</abbr>'

    parts = re.split(r"(<[^>]+>)", text)
    for idx, part in enumerate(parts):
        if part.startswith("<") and part.endswith(">"):
            continue
        parts[idx] = pattern.sub(_replace_metric, part)
    return "".join(parts)

_DEFAULTS: dict[str, Any] = {
    "source_mode": "promptman_versions",
    "base_url": "http://127.0.0.1:8000",
    "access_token": "",
    "project": "",
    "prompt_name": "",
    "version_selector": "all",
    "encoding_name": "cl100k_base",
    "report_format": "both",
    "json_chain": json.dumps(
        {
            "prompts": [
                {
                    "label": "v1",
                    "role": "assistant",
                    "task": "Summarize the user request",
                    "constraints": "Keep it concise",
                    "output_format": "Bullet list",
                    "examples": "Input: long text -> Output: key points",
                    "context": "User asks for a short summary",
                },
                {
                    "label": "v2",
                    "role": "assistant",
                    "task": "Summarize the user request with action items",
                    "constraints": "Use exactly three bullets",
                    "output_format": "Markdown bullets",
                    "examples": "Input: bug report -> Output: findings + actions",
                    "context": "User asks for concise summary and next steps",
                },
            ]
        },
        ensure_ascii=True,
        indent=2,
    ),
}

_STATE: dict[str, Any] = {
    "started_at": None,
    "last_summary": None,
    "last_markdown_report": "",
    "last_rich_report": "",
    **_DEFAULTS,
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _chart_points_from_transitions(transitions: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for item in transitions:
        from_label = str(item.get("from_label") or "?")
        to_label = str(item.get("to_label") or "?")
        points.append(
            {
                "label": f"{from_label}->{to_label}",
                "value": _as_float(item.get(field), 0.0),
            }
        )
    return points


def _chart_points_prompt_tokens(prompts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for item in prompts:
        token_counts = item.get("token_counts") if isinstance(item.get("token_counts"), dict) else {}
        points.append(
            {
                "label": str(item.get("label") or "?"),
                "value": _as_float(token_counts.get("total"), 0.0),
            }
        )
    return points


def _build_tabs(*, report_markdown: str, result: dict[str, Any] | None) -> list[dict[str, Any]]:
    summary = result.get("summary") if isinstance(result, dict) and isinstance(result.get("summary"), dict) else {}
    prompts = result.get("prompts") if isinstance(result, dict) and isinstance(result.get("prompts"), list) else []
    transitions = result.get("transitions") if isinstance(result, dict) and isinstance(result.get("transitions"), list) else []

    _ = summary

    charts = [
        {
            "id": "hybrid-trend",
            "title": "Hybrid Similarity by Transition",
            "tooltip": _METRIC_GLOSSARY["Hybrid Similarity"],
            "kind": "line",
            "points": _chart_points_from_transitions(transitions, "hybrid_similarity"),
            "value_min": 0.0,
            "value_max": 1.0,
            "y_label": "0..1",
        },
        {
            "id": "cache-trend",
            "title": "Cache Hit Score by Transition",
            "tooltip": _METRIC_GLOSSARY["Cache Hit Score"],
            "kind": "line",
            "points": _chart_points_from_transitions(transitions, "cache_hit_score"),
            "value_min": 0.0,
            "value_max": 1.0,
            "y_label": "0..1",
        },
        {
            "id": "drift-trend",
            "title": "Context Drift by Transition",
            "tooltip": _METRIC_GLOSSARY["Context Drift"],
            "kind": "line",
            "points": _chart_points_from_transitions(transitions, "context_drift"),
            "value_min": 0.0,
            "value_max": 1.0,
            "y_label": "0..1",
        },
        {
            "id": "token-volume",
            "title": "Total Tokens by Prompt Version",
            "tooltip": _METRIC_GLOSSARY["Token Count"],
            "kind": "bar",
            "points": _chart_points_prompt_tokens(prompts),
            "y_label": "tokens",
        },
    ]

    return [
        {
            "id": "inputs",
            "label": "Input",
            "body_markdown": "### Input\nConfigure source and analyzer settings, then run analysis.",
            "controls": _modal_controls(),
        },
        {
            "id": "reports",
            "label": "Reports",
            "body_markdown": _annotate_metric_terms(report_markdown),
        },
        {
            "id": "charts",
            "label": "Charts",
            "body_markdown": "### Charts\nTransition trends and token volume for current run.",
            "charts": charts,
        },
    ]


def _modal_controls() -> list[PluginUiControl]:
    return [
        PluginUiControl(
            name="source_mode",
            control_type="dropdown",
            label="Source",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            description="Analyze PromptMan versions or a JSON prompt chain.",
            options=[
                PluginUiOption(label="PromptMan versions", value="promptman_versions"),
                PluginUiOption(label="JSON chain", value="json_chain"),
            ],
            default_value=_DEFAULTS["source_mode"],
            trigger="change",
        ),
        PluginUiControl(
            name="base_url",
            control_type="text",
            label="PromptMan base URL",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            description="Used when source is PromptMan versions.",
            placeholder="http://127.0.0.1:8000",
            default_value=_DEFAULTS["base_url"],
            trigger="change",
        ),
        PluginUiControl(
            name="access_token",
            control_type="text",
            label="Access token (optional)",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            description="Bearer token for protected PromptMan API.",
            placeholder="Paste access token",
            default_value="",
            trigger="change",
        ),
        PluginUiControl(
            name="project",
            control_type="text",
            label="Project",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            description="PromptMan project name.",
            placeholder="my-project",
            default_value="",
            trigger="change",
        ),
        PluginUiControl(
            name="prompt_name",
            control_type="text",
            label="Prompt name",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            description="PromptMan prompt identifier.",
            placeholder="sales_assistant",
            default_value="",
            trigger="change",
        ),
        PluginUiControl(
            name="version_selector",
            control_type="text",
            label="Versions",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            description="Examples: all, 1,3,7, 1-4.",
            placeholder="all",
            default_value="all",
            trigger="change",
        ),
        PluginUiControl(
            name="encoding_name",
            control_type="dropdown",
            label="Tokenizer encoding",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            options=[
                PluginUiOption(label="cl100k_base", value="cl100k_base"),
                PluginUiOption(label="o200k_base", value="o200k_base"),
                PluginUiOption(label="p50k_base", value="p50k_base"),
                PluginUiOption(label="r50k_base", value="r50k_base"),
            ],
            default_value="cl100k_base",
            trigger="change",
        ),
        PluginUiControl(
            name="report_format",
            control_type="dropdown",
            label="Report format",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            options=[
                PluginUiOption(label="Markdown", value="markdown"),
                PluginUiOption(label="Rich text", value="rich"),
                PluginUiOption(label="Both", value="both"),
            ],
            default_value="both",
            trigger="change",
        ),
        PluginUiControl(
            name="json_chain",
            control_type="textarea",
            label="JSON prompt chain",
            endpoint_name="update_control",
            init_endpoint_name="update_control_init",
            description="Used when source is JSON chain. Accepts either list or object with prompts[].",
            placeholder='{"prompts": [{"task": "..."}]}',
            default_value=_DEFAULTS["json_chain"],
            trigger="change",
        ),
        PluginUiControl(
            name="run_analysis",
            control_type="button",
            label="Run efficiency analysis",
            endpoint_name="run_analysis",
            description="Run segmentation, token counting, similarity, cache estimate, drift, and PSI.",
            trigger="click",
        ),
    ]


def _build_modal_spec(*, body_markdown: str, status: str, result: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "title": "Prompt Efficiency Analyzer",
        "description": "Deterministic local prompt analysis without LLM calls.",
        "body_markdown": body_markdown,
        "tabs": _build_tabs(report_markdown=body_markdown, result=result),
        "active_tab": "inputs" if result is None else "reports",
        "controls": [],
        "allow_stop": True,
        "stop_label": "Stop Analyzer",
        "close_label": "Close",
        "primary_action_label": "Run efficiency analysis",
        "status": status,
    }


def _build_intro_body() -> str:
    return (
        "### Prompt Efficiency Analyzer\n"
        "This workbench runs local deterministic analysis:\n\n"
        "- Prompt segmentation\n"
        "- Token counting (tiktoken)\n"
        "- Similarity metrics (Levenshtein, Jaro-Winkler, Jaccard)\n"
        "- Cache hit score and PSI\n"
        "- Context drift analysis\n"
        "- Segment volatility and placeholder stability\n"
        "- Constraint strictness and ambiguity signals\n"
        "- Output schema compliance and redundancy\n"
        "- Conflict risk, injection surface, readability, and token budget safety\n"
        "- Rich/Markdown report generation\n\n"
        "Choose source, configure fields, and click **Run efficiency analysis**."
    )


def _current_value(name: str) -> Any:
    if name in _STATE:
        return _STATE[name]
    return _DEFAULTS.get(name, "")


def _update_control(control_name: str, value: Any) -> Any:
    if control_name not in _DEFAULTS:
        return value

    if control_name in {"source_mode", "encoding_name", "report_format"}:
        normalized = str(value or _DEFAULTS[control_name]).strip().lower()
        if control_name == "source_mode" and normalized not in {"promptman_versions", "json_chain"}:
            normalized = "promptman_versions"
        if control_name == "encoding_name" and normalized not in {"cl100k_base", "o200k_base", "p50k_base", "r50k_base"}:
            normalized = "cl100k_base"
        if control_name == "report_format" and normalized not in {"markdown", "rich", "both"}:
            normalized = "both"
        _STATE[control_name] = normalized
        return normalized

    normalized_text = str(value or "")
    _STATE[control_name] = normalized_text
    return normalized_text


def _render_modal_report(result: dict[str, Any], report_format: str) -> str:
    markdown_text = str(result.get("markdown_report") or "")
    rich_text = str(result.get("rich_report") or "")
    if report_format == "markdown":
        return markdown_text
    if report_format == "rich":
        return f"```text\n{rich_text.strip()}\n```"
    return markdown_text


def plugin_preinit() -> PluginManifest:
    return PluginManifest(
        name="efficiency_analizer_ui",
        version="1.0.0",
        description="Modal workbench for deterministic prompt efficiency analysis.",
        icon="/P_240x240.png",
        min_promptman_version="0.0.0",
        endpoints=[
            PluginEndpointConfig(name="open_workbench", description="Open Prompt Efficiency Analyzer modal", roles=["admin", "developer", "viewer"], launches_modal=True),
            PluginEndpointConfig(name="update_control", description="Update modal control values", roles=["admin", "developer", "viewer"]),
            PluginEndpointConfig(name="run_analysis", description="Run prompt efficiency analysis", roles=["admin", "developer", "viewer"]),
        ],
        ui_controls=[
            PluginUiControl(
                name="open_efficiency_analyzer",
                control_type="button",
                label="Open Prompt Efficiency Analyzer",
                endpoint_name="open_workbench",
                description="Launch modal analyzer for PromptMan versions or JSON prompt chains.",
                trigger="click",
            )
        ],
    )


def plugin_init(context: PluginLifecycleContext) -> None:
    _STATE["started_at"] = datetime.now(UTC).isoformat()


def plugin_postinit(context: PluginLifecycleContext) -> None:
    return None


def plugin_run(context: PluginRunContext) -> dict[str, Any]:
    payload = context.payload if isinstance(context.payload, dict) else {}

    if context.endpoint_name == "health":
        return {"ok": True, "status": "healthy", "started_at": _STATE.get("started_at")}

    if context.endpoint_name == "open_workbench":
        body = _STATE.get("last_markdown_report") or _build_intro_body()
        return {
            "ok": True,
            "message": "Prompt Efficiency Analyzer opened",
            "modal": _build_modal_spec(body_markdown=str(body), status="Ready", result=None),
        }

    if context.endpoint_name == "update_control_init":
        control_name = str(payload.get("control_name") or "").strip()
        value = _current_value(control_name)
        return {"ok": True, "value": value, "message": f"Initialized {control_name}", "status": "Control initialized"}

    if context.endpoint_name == "update_control":
        control_name = str(payload.get("control_name") or "").strip()
        updated = _update_control(control_name, payload.get("value"))
        return {"ok": True, "value": updated, "message": f"Updated {control_name}", "status": "Control updated"}

    if context.endpoint_name == "run_analysis":
        if context.modal_stop_requested:
            return {"ok": False, "message": "Analyzer stopped", "status": "Stopped", "logs": ["Stop was requested before analysis."]}

        controls = payload.get("controls") if isinstance(payload.get("controls"), dict) else {}
        source_mode = str(controls.get("source_mode", _STATE.get("source_mode", "promptman_versions")))
        encoding_name = str(controls.get("encoding_name", _STATE.get("encoding_name", "cl100k_base")))
        report_format = str(controls.get("report_format", _STATE.get("report_format", "both")))

        analyzer = PromptEfficiencyAnalyzer(encoding_name=encoding_name)
        try:
            if source_mode == "json_chain":
                chain_json = str(controls.get("json_chain", _STATE.get("json_chain", "")) or "")
                result = analyzer.analyze_prompt_chain_json(chain_json)
            else:
                base_url = str(controls.get("base_url", _STATE.get("base_url", "http://127.0.0.1:8000")) or "http://127.0.0.1:8000")
                project = str(controls.get("project", _STATE.get("project", "")) or "")
                prompt_name = str(controls.get("prompt_name", _STATE.get("prompt_name", "")) or "")
                version_selector = str(controls.get("version_selector", _STATE.get("version_selector", "all")) or "all")
                access_token = str(controls.get("access_token", _STATE.get("access_token", "")) or "")
                if not project.strip() or not prompt_name.strip():
                    raise ValueError("Project and prompt name are required for PromptMan source")
                result = analyzer.analyze_promptman_prompt(
                    base_url=base_url,
                    project=project,
                    prompt_name=prompt_name,
                    version_selector=version_selector,
                    access_token=access_token or None,
                )
        except Exception as exc:
            return {
                "ok": False,
                "message": f"Analysis failed: {exc}",
                "status": "Error",
                "logs": [str(exc)],
            }

        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        psi = summary.get("psi", 0)
        avg_cache_hit = summary.get("avg_cache_hit_score", 0)
        prompt_count = summary.get("prompt_count", 0)

        report_body = _render_modal_report(result, report_format=report_format)
        _STATE["last_summary"] = summary
        _STATE["last_markdown_report"] = str(result.get("markdown_report") or "")
        _STATE["last_rich_report"] = str(result.get("rich_report") or "")

        return {
            "ok": True,
            "message": "Prompt efficiency analysis completed",
            "status": f"Completed (PSI: {psi})",
            "logs": [
                f"Prompt count: {prompt_count}",
                f"PSI: {psi}",
                f"Average cache hit score: {avg_cache_hit}",
            ],
            "result": result,
            "modal": _build_modal_spec(body_markdown=report_body, status=f"Completed (PSI: {psi})", result=result),
        }

    return {"ok": False, "message": f"Unknown endpoint {context.endpoint_name}"}


def plugin_done(context: PluginLifecycleContext) -> None:
    _STATE["started_at"] = None
    _STATE["last_summary"] = None
