from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from plugin_engine import PluginEndpointConfig, PluginLifecycleContext, PluginManifest, PluginRunContext, PluginUiControl, PluginUiOption

_STATE: dict[str, Any] = {
    "query": "",
    "mode": "balanced",
    "verbose": False,
    "started_at": None,
    "last_action": None,
}


def _build_modal_spec() -> dict[str, Any]:
    return {
        "title": "Modal Workbench",
        "description": "A modal-driven example that can be controlled via PromptMan UI or REST endpoints.",
        "body_markdown": (
            "Use this modal to test plugin-driven dialogs.\n\n"
            "The plugin listens for changes through `plugin_run` and exposes a stop button in the modal frame."
        ),
        "controls": [
            PluginUiControl(
                name="query_input",
                control_type="text",
                label="Query",
                endpoint_name="set_query",
                init_endpoint_name="set_query_init",
                description="Free-form text passed into the workbench.",
                placeholder="Type a query...",
                trigger="change",
            ),
            PluginUiControl(
                name="mode_selector",
                control_type="dropdown",
                label="Mode",
                endpoint_name="set_mode",
                init_endpoint_name="set_mode_init",
                description="Choose how the modal behaves.",
                options=[
                    PluginUiOption(label="Fast", value="fast"),
                    PluginUiOption(label="Balanced", value="balanced"),
                    PluginUiOption(label="Deep", value="deep"),
                ],
                default_value="balanced",
                trigger="change",
            ),
            PluginUiControl(
                name="verbose_toggle",
                control_type="checkbox",
                label="Verbose",
                endpoint_name="set_verbose",
                init_endpoint_name="set_verbose_init",
                description="Emit extra details into the modal log.",
                default_value=False,
                trigger="change",
            ),
            PluginUiControl(
                name="run_button",
                control_type="button",
                label="Run Workbench",
                endpoint_name="run_task",
                description="Run the main modal action using the current control values.",
                trigger="click",
            ),
        ],
        "allow_stop": True,
        "stop_label": "Stop Workbench",
        "close_label": "Close Workbench",
        "primary_action_label": "Run Workbench",
        "status": "Ready",
    }


def plugin_preinit() -> PluginManifest:
    return PluginManifest(
        name="example_modal",
        version="1.0.0",
        description="Example plugin that opens a modal workbench and handles it through plugin_run.",
        icon="/P_240x240.png",
        min_promptman_version="0.0.0",
        endpoints=[
            PluginEndpointConfig(name="open_workbench", description="Open the modal workbench", roles=["admin", "developer", "viewer"], launches_modal=True),
            PluginEndpointConfig(name="set_query", description="Store query text", roles=["admin", "developer", "viewer"]),
            PluginEndpointConfig(name="set_mode", description="Store modal mode", roles=["admin", "developer", "viewer"]),
            PluginEndpointConfig(name="set_verbose", description="Toggle verbose mode", roles=["admin", "developer", "viewer"]),
            PluginEndpointConfig(name="run_task", description="Run the modal action", roles=["admin", "developer", "viewer"]),
        ],
        ui_controls=[
            PluginUiControl(
                name="open_workbench_button",
                control_type="button",
                label="Open Workbench",
                endpoint_name="open_workbench",
                description="Launch the modal workbench example.",
                trigger="click",
            ),
        ],
    )


def plugin_init(context: PluginLifecycleContext) -> None:
    _STATE["started_at"] = datetime.now(UTC).isoformat()


def plugin_postinit(context: PluginLifecycleContext) -> None:
    return None


def plugin_run(context: PluginRunContext) -> dict[str, Any]:
    payload = context.payload or {}

    if context.endpoint_name == "health":
        return {"ok": True, "status": "healthy", "started_at": _STATE["started_at"]}

    if context.endpoint_name == "set_query_init":
        return {"value": _STATE["query"], "message": "Query initialized"}

    if context.endpoint_name == "set_mode_init":
        return {"value": _STATE["mode"], "message": "Mode initialized"}

    if context.endpoint_name == "set_verbose_init":
        return {"value": bool(_STATE["verbose"]), "message": "Verbose initialized"}

    if context.endpoint_name == "open_workbench":
        _STATE["last_action"] = "open_workbench"
        return {
            "ok": True,
            "message": "Modal workbench opened",
            "modal": _build_modal_spec(),
        }

    if context.endpoint_name == "set_query":
        value = str(payload.get("value") or "").strip()
        _STATE["query"] = value
        _STATE["last_action"] = "set_query"
        return {"ok": True, "value": value, "message": f"Query set to {value or '<empty>'}", "status": "Query updated"}

    if context.endpoint_name == "set_mode":
        value = str(payload.get("value") or "balanced").strip().lower()
        if value not in {"fast", "balanced", "deep"}:
            value = "balanced"
        _STATE["mode"] = value
        _STATE["last_action"] = "set_mode"
        return {"ok": True, "value": value, "message": f"Mode set to {value}", "status": "Mode updated"}

    if context.endpoint_name == "set_verbose":
        value = bool(payload.get("value", False))
        _STATE["verbose"] = value
        _STATE["last_action"] = "set_verbose"
        return {"ok": True, "value": value, "message": f"Verbose set to {value}", "status": "Verbose updated"}

    if context.endpoint_name == "run_task":
        if context.modal_stop_requested:
            return {"ok": False, "message": "Workbench stopped before execution", "status": "Stopped", "logs": ["Modal stop was requested."]}
        controls = payload.get("controls") if isinstance(payload, dict) else {}
        _STATE["last_action"] = "run_task"
        result_message = (
            f"Executing with query={controls.get('query_input', _STATE['query'])!r}, "
            f"mode={controls.get('mode_selector', _STATE['mode'])!r}, "
            f"verbose={bool(controls.get('verbose_toggle', _STATE['verbose']))}"
        )
        return {
            "ok": True,
            "message": "Workbench run completed",
            "status": "Completed",
            "logs": [result_message],
        }

    return {"ok": False, "message": f"Unknown endpoint {context.endpoint_name}"}


def plugin_done(context: PluginLifecycleContext) -> None:
    _STATE["started_at"] = None
    _STATE["last_action"] = None
