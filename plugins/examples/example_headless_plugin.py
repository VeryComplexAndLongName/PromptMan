from __future__ import annotations

from typing import Any

from loguru import logger

from plugin_engine import PluginEndpointConfig, PluginHookConfig, PluginLifecycleContext, PluginManifest, PluginRunContext


_COUNTERS: dict[str, Any] = {
    "before": 0,
    "after": 0,
}


def plugin_preinit() -> PluginManifest:
    return PluginManifest(
        name="example_headless",
        version="1.0.0",
        description="Headless example plugin without UI controls. Demonstrates before/after hooks around the version endpoint.",
        icon="/PromptMan_240x240.png",
        min_promptman_version="0.0.0",
        endpoints=[
            PluginEndpointConfig(name="observe_before", description="Internal before hook", roles=["admin"]),
            PluginEndpointConfig(name="observe_after", description="Internal after hook", roles=["admin"]),
            PluginEndpointConfig(name="ping", description="Return plugin counters", roles=["admin", "developer", "viewer"]),
        ],
        hooks=[
            PluginHookConfig(
                target_method="GET",
                target_path="/v1/version",
                before_endpoint="observe_before",
                after_endpoint="observe_after",
                failure_limit=3,
            )
        ],
    )


def plugin_init(context: PluginLifecycleContext) -> None:
    return None


def plugin_postinit(context: PluginLifecycleContext) -> None:
    return None


def plugin_run(context: PluginRunContext) -> dict[str, Any]:
    if context.endpoint_name == "health":
        return {"ok": True, "before": _COUNTERS["before"], "after": _COUNTERS["after"]}

    if context.endpoint_name == "observe_before":
        _COUNTERS["before"] += 1
        logger.info("example_headless.before path={} count={}", context.request.path, _COUNTERS["before"])
        return {"ok": True, "stage": "before", "count": _COUNTERS["before"]}

    if context.endpoint_name == "observe_after":
        _COUNTERS["after"] += 1
        logger.info("example_headless.after path={} count={} status={}", context.request.path, _COUNTERS["after"], context.response_status_code)
        return {"ok": True, "stage": "after", "count": _COUNTERS["after"]}

    if context.endpoint_name == "observe_before_init":
        return {"value": _COUNTERS["before"]}

    if context.endpoint_name == "observe_after_init":
        return {"value": _COUNTERS["after"]}

    if context.endpoint_name == "ping_init":
        return {"value": None}

    if context.endpoint_name == "ping":
        return {"ok": True, "before": _COUNTERS["before"], "after": _COUNTERS["after"]}

    return {"ok": False, "message": f"Unknown endpoint {context.endpoint_name}"}


def plugin_done(context: PluginLifecycleContext) -> None:
    return None