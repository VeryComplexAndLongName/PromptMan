from __future__ import annotations

from datetime import datetime, UTC
from typing import Any

from plugin_engine import PluginEndpointConfig, PluginLifecycleContext, PluginManifest, PluginRunContext, PluginUiControl, PluginUiOption


_STATE: dict[str, Any] = {
    "verbose": False,
    "mode": "safe",
    "started_at": None,
}


def plugin_preinit() -> PluginManifest:
    return PluginManifest(
        name="example_ui",
        version="1.0.0",
        description="Example plugin with checkbox, dropdown, and button controls rendered on the Plugins tab.",
        icon="/P_240x240.png",
        min_promptman_version="0.0.0",
        endpoints=[
            PluginEndpointConfig(name="set_verbose", description="Update verbose mode", roles=["admin", "developer"]),
            PluginEndpointConfig(name="set_mode", description="Update plugin mode", roles=["admin", "developer"]),
            PluginEndpointConfig(name="run_demo", description="Run the example action", roles=["admin", "developer", "viewer"]),
        ],
        ui_controls=[
            PluginUiControl(
                name="verbose_toggle",
                control_type="checkbox",
                label="Verbose Mode",
                endpoint_name="set_verbose",
                description="Toggle verbose output for the demo action.",
                default_value=False,
                trigger="change",
            ),
            PluginUiControl(
                name="mode_selector",
                control_type="dropdown",
                label="Mode",
                endpoint_name="set_mode",
                description="Choose how the demo action behaves.",
                default_value="safe",
                options=[
                    PluginUiOption(label="Safe", value="safe"),
                    PluginUiOption(label="Fast", value="fast"),
                    PluginUiOption(label="Deep", value="deep"),
                ],
                trigger="change",
            ),
            PluginUiControl(
                name="run_button",
                control_type="button",
                label="Run Demo",
                endpoint_name="run_demo",
                description="Invoke the main action of the example plugin.",
                trigger="click",
            ),
        ],
    )


def plugin_init(context: PluginLifecycleContext) -> None:
    _STATE["started_at"] = datetime.now(UTC).isoformat()


def plugin_postinit(context: PluginLifecycleContext) -> None:
    return None


def plugin_run(context: PluginRunContext) -> dict[str, Any]:
    if context.endpoint_name == "health":
        return {"ok": True, "status": "healthy", "started_at": _STATE["started_at"]}

    if context.endpoint_name == "set_verbose_init":
        return {"value": bool(_STATE["verbose"]), "message": "Verbose state initialized"}

    if context.endpoint_name == "set_mode_init":
        return {"value": str(_STATE["mode"]), "message": "Mode initialized"}

    if context.endpoint_name == "run_demo_init":
        return {"value": None, "message": "Button control initialized"}

    if context.endpoint_name == "set_verbose":
        value = bool((context.payload or {}).get("value", False))
        _STATE["verbose"] = value
        return {"ok": True, "verbose": value, "message": f"Verbose mode set to {value}"}

    if context.endpoint_name == "set_mode":
        value = str((context.payload or {}).get("value") or "safe").strip().lower()
        if value not in {"safe", "fast", "deep"}:
            value = "safe"
        _STATE["mode"] = value
        return {"ok": True, "mode": value, "message": f"Mode set to {value}"}

    if context.endpoint_name == "run_demo":
        return {
            "ok": True,
            "message": "Example UI plugin executed",
            "mode": _STATE["mode"],
            "verbose": _STATE["verbose"],
            "phase": context.phase,
        }

    return {"ok": False, "message": f"Unknown endpoint {context.endpoint_name}"}


def plugin_done(context: PluginLifecycleContext) -> None:
    _STATE["started_at"] = None