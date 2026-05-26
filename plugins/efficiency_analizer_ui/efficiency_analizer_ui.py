from __future__ import annotations

import json
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


def _build_modal_spec(*, body_markdown: str, status: str) -> dict[str, Any]:
    return {
        "title": "Prompt Efficiency Analyzer",
        "description": "Deterministic local prompt analysis without LLM calls.",
        "body_markdown": body_markdown,
        "controls": _modal_controls(),
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
    return f"{markdown_text}\n\n---\n\n```text\n{rich_text.strip()}\n```"


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
            "modal": _build_modal_spec(body_markdown=str(body), status="Ready"),
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
            "modal": _build_modal_spec(body_markdown=report_body, status=f"Completed (PSI: {psi})"),
        }

    return {"ok": False, "message": f"Unknown endpoint {context.endpoint_name}"}


def plugin_done(context: PluginLifecycleContext) -> None:
    _STATE["started_at"] = None
    _STATE["last_summary"] = None
