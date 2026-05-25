from __future__ import annotations

import asyncio
import base64
import json
import importlib.util
import inspect
from datetime import UTC, datetime
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from loguru import logger

import app_settings
import auth as auth_service
from app_core.api_version import API_V1

from .contracts import (
    PluginActionResult,
    PluginCatalogEntry,
    PluginDiagnosticsOut,
    PluginEndpointConfig,
    PluginEndpointDiagnosticEntry,
    PluginHookConfig,
    PluginHookDiagnosticEntry,
    PluginLifecycleContext,
    PluginManifest,
    PluginModalControlUpdateRequest,
    PluginModalSessionOut,
    PluginModalSpec,
    PluginModalStartRequest,
    PluginRequestSnapshot,
    PluginRunContext,
    PluginSignatureEnvelope,
    PluginSignerRecord,
    PluginUiControl,
)


@dataclass(slots=True)
class HookRuntimeState:
    consecutive_failures: int = 0
    blocked: bool = False
    last_error: str | None = None


@dataclass(slots=True)
class EndpointRuntimeState:
    consecutive_failures: int = 0
    blocked: bool = False
    last_error: str | None = None


@dataclass(slots=True)
class PluginRecord:
    name: str
    source_path: Path
    manifest: PluginManifest
    module: ModuleType | None = None
    state: str = "discovered"
    compatible: bool = True
    available: bool = False
    last_error: str | None = None
    unavailable_reason: str | None = None
    health_failures: int = 0
    signature_status: str = "unsigned"
    signature_signer: str | None = None
    signature_error: str | None = None
    registered_route_names: list[str] = field(default_factory=list)
    active_routes: list[str] = field(default_factory=list)
    init_results: dict[str, Any] = field(default_factory=dict)
    hook_states: dict[str, HookRuntimeState] = field(default_factory=dict)
    endpoint_states: dict[str, EndpointRuntimeState] = field(default_factory=dict)
    lifecycle_active: bool = False


@dataclass(slots=True)
class PluginModalSession:
    session_id: str
    plugin_name: str
    entrypoint: str
    control_values: dict[str, Any]
    modal: PluginModalSpec
    state: str = "opening"
    logs: list[str] = field(default_factory=list)
    stop_requested: bool = False
    last_result: Any = None
    last_error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class PluginEngine:
    def __init__(self, app: FastAPI, *, plugins_dir: Path, app_version: str) -> None:
        self.app = app
        self.plugins_dir = plugins_dir
        self.app_version = app_version
        self.trusted_signers_path = self.plugins_dir / "trusted_signers.json"
        self.records: dict[str, PluginRecord] = {}
        self.modal_sessions: dict[str, PluginModalSession] = {}
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        await self.rescan(auto_activate=True)

    async def shutdown(self) -> None:
        for plugin_name in list(self.records.keys()):
            try:
                await self.unload_plugin(plugin_name, remove_from_catalog=False)
            except Exception as exc:
                logger.exception("plugins.shutdown.error plugin={} error={}", plugin_name, exc)

    def list_plugins(self) -> list[PluginCatalogEntry]:
        items = [self._record_to_catalog_entry(record) for record in self.records.values()]
        return sorted(items, key=lambda item: item.name.lower())

    def get_plugin_diagnostics(self, plugin_name: str) -> PluginDiagnosticsOut:
        record = self.records.get(plugin_name)
        if record is None:
            raise HTTPException(status_code=404, detail="Plugin not found")
        return PluginDiagnosticsOut(
            plugin_name=record.name,
            state=record.state,
            available=record.available,
            lifecycle_active=record.lifecycle_active,
            health_failures=record.health_failures,
            signature_status=record.signature_status,
            signature_signer=record.signature_signer,
            signature_error=record.signature_error,
            unavailable_reason=record.unavailable_reason,
            endpoint_diagnostics=[
                PluginEndpointDiagnosticEntry(
                    endpoint_name=endpoint_name,
                    consecutive_failures=state.consecutive_failures,
                    blocked=state.blocked,
                    last_error=state.last_error,
                )
                for endpoint_name, state in sorted(record.endpoint_states.items())
            ],
            hook_diagnostics=[
                PluginHookDiagnosticEntry(
                    hook_key=hook_key,
                    consecutive_failures=state.consecutive_failures,
                    blocked=state.blocked,
                    last_error=state.last_error,
                )
                for hook_key, state in sorted(record.hook_states.items())
            ],
        )

    async def rescan(self, *, auto_activate: bool = True) -> PluginActionResult:
        async with self._lock:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            discovered_paths = sorted(
                path
                for path in self.plugins_dir.rglob("*.py")
                if path.is_file() and not path.name.startswith("_") and path.name != "__init__.py"
            )
            for path in discovered_paths:
                try:
                    await self._discover_or_load_path(path, activate=auto_activate)
                except Exception as exc:
                    plugin_name = path.stem
                    signature_status, signature_signer, signature_error = self._verify_plugin_signature(path)
                    fallback_manifest = PluginManifest(
                        name=plugin_name,
                        version="unknown",
                        description="Plugin preinit failed",
                        min_promptman_version="0.0.0",
                    )
                    self.records[plugin_name] = PluginRecord(
                        name=plugin_name,
                        source_path=path,
                        manifest=fallback_manifest,
                        state="error",
                        compatible=False,
                        available=False,
                        last_error=str(exc),
                        signature_status=signature_status,
                        signature_signer=signature_signer,
                        signature_error=signature_error,
                    )
                    logger.exception("plugins.rescan.discover_failed file={} error={}", path, exc)
            return PluginActionResult(message="Plugin rescan completed")

    async def load_plugin(self, plugin_name: str) -> PluginActionResult:
        record = self.records.get(plugin_name)
        if record is None:
            raise HTTPException(status_code=404, detail="Plugin not found")
        async with self._lock:
            await self._discover_or_load_path(record.source_path, activate=True, force_reload=True)
            updated = self.records[plugin_name]
            return PluginActionResult(message="Plugin loaded", plugin_name=plugin_name, state=updated.state)

    async def reload_plugin(self, plugin_name: str) -> PluginActionResult:
        record = self.records.get(plugin_name)
        if record is None:
            raise HTTPException(status_code=404, detail="Plugin not found")
        async with self._lock:
            await self.unload_plugin(plugin_name, remove_from_catalog=False)
            await self._discover_or_load_path(record.source_path, activate=True, force_reload=True)
            updated = self.records[plugin_name]
            return PluginActionResult(message="Plugin reloaded", plugin_name=plugin_name, state=updated.state)

    async def unload_plugin(self, plugin_name: str, *, remove_from_catalog: bool = False) -> PluginActionResult:
        record = self.records.get(plugin_name)
        if record is None:
            raise HTTPException(status_code=404, detail="Plugin not found")

        self._close_modal_sessions_for_plugin(plugin_name)

        if record.lifecycle_active and record.module and hasattr(record.module, "plugin_done"):
            try:
                await self._call_with_timeout(
                    getattr(record.module, "plugin_done"),
                    PluginLifecycleContext(self.app, self, record.name, record.manifest, dict(record.init_results)),
                    timeout_seconds=record.manifest.lifecycle_timeout_seconds,
                )
            except Exception as exc:
                logger.exception("plugins.done.error plugin={} error={}", plugin_name, exc)
                record.last_error = str(exc)

        self._unregister_plugin_routes(record)
        record.lifecycle_active = False
        record.available = False
        record.state = "stopped"
        record.unavailable_reason = record.unavailable_reason or "Plugin unloaded"
        if remove_from_catalog:
            self.records.pop(plugin_name, None)
        return PluginActionResult(message="Plugin unloaded", plugin_name=plugin_name, state=record.state)

    async def execute_plugin_endpoint(
        self,
        plugin_name: str,
        endpoint_name: str,
        *,
        request: Request,
        current_user: Any | None,
        payload: Any,
        phase: str = "runtime",
        hook: PluginHookConfig | None = None,
        response_status_code: int | None = None,
        modal_session_id: str | None = None,
        modal_action: str | None = None,
        modal_controls: dict[str, Any] | None = None,
        modal_stop_requested: bool = False,
        internal: bool = False,
    ) -> Any:
        record = self.records.get(plugin_name)
        if record is None:
            raise HTTPException(status_code=404, detail="Plugin not found")

        if not internal and (not record.available or record.state not in {"running", "unavailable"}):
            raise HTTPException(status_code=503, detail="Plugin is not active")

        if endpoint_name == "health":
            timeout_seconds = record.manifest.health_timeout_seconds
            endpoint_config = None
        else:
            endpoint_config = self._get_endpoint_config(record, endpoint_name)
            timeout_seconds = endpoint_config.timeout_seconds if endpoint_config else record.manifest.lifecycle_timeout_seconds
            if not internal:
                self._ensure_endpoint_roles(current_user, endpoint_config)

        snapshot = PluginRequestSnapshot(
            method=request.method,
            path=request.url.path,
            route_path=self._resolve_route_path(request),
            query=dict(request.query_params),
            headers={key: value for key, value in request.headers.items() if key.lower() in {"content-type", "authorization"}},
        )
        run_context = PluginRunContext(
            app=self.app,
            engine=self,
            plugin_name=record.name,
            manifest=record.manifest,
            endpoint_name=endpoint_name,
            current_user=current_user,
            payload=payload,
            request=snapshot,
            phase=phase,  # type: ignore[arg-type]
            hook=hook,
            response_status_code=response_status_code,
            modal_session_id=modal_session_id,
            modal_action=modal_action,
            modal_controls=modal_controls,
            modal_stop_requested=modal_stop_requested,
        )

        try:
            if not record.module or not hasattr(record.module, "plugin_run"):
                raise RuntimeError("plugin_run is not available")
            result = await self._call_with_timeout(
                getattr(record.module, "plugin_run"),
                run_context,
                timeout_seconds=timeout_seconds,
            )
            if endpoint_name == "health":
                self._mark_health_success(record)
            elif phase in {"runtime", "modal"} and not endpoint_name.endswith("_init"):
                self._mark_runtime_success(record, endpoint_name)
            return result
        except Exception as exc:
            if endpoint_name == "health":
                await self._mark_health_failure(record, exc)
            elif phase in {"runtime", "modal"} and not endpoint_name.endswith("_init"):
                await self._mark_runtime_failure(record, endpoint_name, exc)
            raise

    def list_modal_sessions(self, plugin_name: str | None = None) -> list[PluginModalSessionOut]:
        sessions = self.modal_sessions.values()
        if plugin_name is not None:
            sessions = [session for session in sessions if session.plugin_name == plugin_name]
        return sorted((self._modal_session_to_out(session) for session in sessions), key=lambda item: item.created_at)

    def get_modal_session(self, plugin_name: str, session_id: str) -> PluginModalSessionOut:
        session = self._get_modal_session_record(plugin_name, session_id)
        return self._modal_session_to_out(session)

    async def start_modal_session(
        self,
        plugin_name: str,
        request: Request,
        current_user: Any | None,
        start_request: PluginModalStartRequest,
    ) -> PluginModalSessionOut:
        record = self.records.get(plugin_name)
        if record is None:
            raise HTTPException(status_code=404, detail="Plugin not found")

        control_values = dict(start_request.controls or {})
        session = PluginModalSession(
            session_id=uuid4().hex,
            plugin_name=plugin_name,
            entrypoint=start_request.endpoint_name,
            control_values=control_values,
            modal=PluginModalSpec(title=plugin_name),
        )
        self.modal_sessions[session.session_id] = session

        payload = start_request.payload or {}
        try:
            result = await self.execute_plugin_endpoint(
                plugin_name,
                start_request.endpoint_name,
                request=request,
                current_user=current_user,
                payload=payload,
                phase="modal",
                modal_session_id=session.session_id,
                modal_action="start",
                modal_controls=dict(session.control_values),
            )
        except Exception:
            session.state = "error"
            session.last_error = "Failed to start modal session"
            session.updated_at = datetime.now(UTC)
            raise

        modal_payload: dict[str, Any] | None = None
        if isinstance(result, dict):
            candidate = result.get("modal")
            if isinstance(candidate, dict):
                modal_payload = candidate
            elif "title" in result or "controls" in result:
                modal_payload = result
        if modal_payload is None:
            self.modal_sessions.pop(session.session_id, None)
            raise HTTPException(status_code=400, detail="Plugin run did not return a modal specification")

        session.modal = self._normalize_modal_spec(modal_payload, plugin_name)
        self._apply_modal_result(session, result)
        await self._hydrate_modal_controls(session, request=request, current_user=current_user)
        session.state = "running"
        session.updated_at = datetime.now(UTC)
        return self._modal_session_to_out(session)

    async def update_modal_control(
        self,
        plugin_name: str,
        session_id: str,
        control_name: str,
        request: Request,
        current_user: Any | None,
        update_request: PluginModalControlUpdateRequest,
    ) -> PluginModalSessionOut:
        session = self._get_modal_session_record(plugin_name, session_id)
        if session.stop_requested or session.state in {"stopped", "completed"}:
            raise HTTPException(status_code=409, detail="Modal session is stopped")

        control = self._find_modal_control(session.modal, control_name)
        if control is None:
            raise HTTPException(status_code=404, detail="Modal control not found")

        payload_controls = dict(update_request.controls or session.control_values)
        payload_controls[control_name] = update_request.value
        session.control_values = payload_controls

        try:
            result = await self.execute_plugin_endpoint(
                plugin_name,
                control.endpoint_name,
                request=request,
                current_user=current_user,
                payload={"value": update_request.value, "control_name": control_name, "controls": payload_controls},
                phase="modal",
                modal_session_id=session.session_id,
                modal_action=control_name,
                modal_controls=dict(payload_controls),
            )
        except Exception as exc:
            session.state = "error"
            session.last_error = str(exc)
            session.updated_at = datetime.now(UTC)
            raise

        self._apply_modal_result(session, result)
        if isinstance(result, dict) and "value" in result:
            session.control_values[control_name] = result["value"]
        session.state = "running"
        session.updated_at = datetime.now(UTC)
        return self._modal_session_to_out(session)

    async def stop_modal_session(self, plugin_name: str, session_id: str) -> PluginModalSessionOut:
        session = self._get_modal_session_record(plugin_name, session_id)
        session.stop_requested = True
        session.state = "stopped"
        session.updated_at = datetime.now(UTC)
        session.logs.append("Modal session stopped by PromptMan")
        return self._modal_session_to_out(session)

    async def close_modal_session(self, plugin_name: str, session_id: str) -> PluginActionResult:
        session = self._get_modal_session_record(plugin_name, session_id)
        if not session.stop_requested and session.state not in {"stopped", "completed", "error"}:
            session.stop_requested = True
            session.state = "stopped"
        self.modal_sessions.pop(session_id, None)
        return PluginActionResult(message="Modal session closed", plugin_name=plugin_name, state=session.state)

    def _modal_session_to_out(self, session: PluginModalSession) -> PluginModalSessionOut:
        return PluginModalSessionOut(
            session_id=session.session_id,
            plugin_name=session.plugin_name,
            endpoint_name=session.entrypoint,
            state=session.state,
            modal=session.modal,
            control_values=dict(session.control_values),
            logs=list(session.logs),
            stop_requested=session.stop_requested,
            last_result=jsonable_encoder(session.last_result) if session.last_result is not None else None,
            last_error=session.last_error,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
        )

    def _get_modal_session_record(self, plugin_name: str, session_id: str) -> PluginModalSession:
        session = self.modal_sessions.get(session_id)
        if session is None or session.plugin_name != plugin_name:
            raise HTTPException(status_code=404, detail="Modal session not found")
        return session

    def _find_modal_control(self, modal: PluginModalSpec, control_name: str) -> PluginUiControl | None:
        for control in modal.controls:
            if control.name == control_name:
                return control
        return None

    def _normalize_modal_spec(self, modal: PluginModalSpec | dict[str, Any], plugin_name: str) -> PluginModalSpec:
        if isinstance(modal, PluginModalSpec):
            return modal
        data = dict(modal or {})
        if not data.get("title"):
            data["title"] = f"{plugin_name} Modal"
        return PluginModalSpec.model_validate(data)

    def _build_control_default(self, control: PluginUiControl) -> Any:
        if control.default_value is not None:
            return control.default_value
        if control.control_type == "checkbox":
            return False
        return ""

    async def _hydrate_modal_controls(self, session: PluginModalSession, *, request: Request, current_user: Any | None) -> None:
        for control in session.modal.controls:
            if control.name in session.control_values and session.control_values[control.name] is not None:
                continue
            init_endpoint = control.init_endpoint_name or f"{control.endpoint_name}_init"
            if not init_endpoint:
                session.control_values[control.name] = self._build_control_default(control)
                continue
            try:
                init_result = await self.execute_plugin_endpoint(
                    session.plugin_name,
                    init_endpoint,
                    request=request,
                    current_user=current_user,
                    payload={
                        "source": "modal-init",
                        "control_name": control.name,
                        "controls": dict(session.control_values),
                    },
                    phase="init-endpoint",
                    modal_session_id=session.session_id,
                    modal_action="init",
                    modal_controls=dict(session.control_values),
                    internal=True,
                )
                if isinstance(init_result, dict) and "value" in init_result:
                    session.control_values[control.name] = init_result["value"]
                else:
                    session.control_values[control.name] = self._build_control_default(control)
            except Exception as exc:
                logger.warning("plugins.modal.init.failed plugin={} control={} error={}", session.plugin_name, control.name, exc)
                session.control_values[control.name] = self._build_control_default(control)

    def _apply_modal_result(self, session: PluginModalSession, result: Any) -> None:
        session.last_result = result
        session.updated_at = datetime.now(UTC)
        if isinstance(result, dict):
            if result.get("message"):
                session.logs.append(str(result["message"]))
            if result.get("status"):
                session.modal.status = str(result["status"])
            if "logs" in result and isinstance(result["logs"], list):
                session.logs.extend(str(item) for item in result["logs"] if str(item).strip())
            modal_payload = result.get("modal")
            if isinstance(modal_payload, dict):
                session.modal = self._normalize_modal_spec(modal_payload, session.plugin_name)

    def _close_modal_sessions_for_plugin(self, plugin_name: str) -> None:
        for session_id, session in list(self.modal_sessions.items()):
            if session.plugin_name != plugin_name:
                continue
            session.stop_requested = True
            session.state = "stopped"
            session.logs.append("Modal session closed because plugin unloaded")
            self.modal_sessions.pop(session_id, None)

    async def run_before_hooks(self, request: Request) -> None:
        for record, hook in self._matching_hooks(request.method, request.url.path):
            if not hook.before_endpoint:
                continue
            hook_key = self._hook_key(record.name, hook, "before")
            state = record.hook_states.setdefault(hook_key, HookRuntimeState())
            if state.blocked:
                continue
            try:
                await self.execute_plugin_endpoint(
                    record.name,
                    hook.before_endpoint,
                    request=request,
                    current_user=None,
                    payload={"stage": "before", "target": hook.target_path},
                    phase="hook",
                    hook=hook,
                    internal=True,
                )
                state.consecutive_failures = 0
                state.last_error = None
            except Exception as exc:
                state.consecutive_failures += 1
                state.last_error = str(exc)
                logger.warning(
                    "plugins.hook.before.failed plugin={} target={} failures={} error={}",
                    record.name,
                    hook.target_path,
                    state.consecutive_failures,
                    exc,
                )
                if state.consecutive_failures >= max(1, hook.failure_limit):
                    state.blocked = True
                    logger.error("plugins.hook.before.blocked plugin={} target={}", record.name, hook.target_path)

    async def run_after_hooks(self, request: Request, response: Response) -> None:
        for record, hook in self._matching_hooks(request.method, request.url.path):
            if not hook.after_endpoint:
                continue
            hook_key = self._hook_key(record.name, hook, "after")
            state = record.hook_states.setdefault(hook_key, HookRuntimeState())
            if state.blocked:
                continue
            try:
                await self.execute_plugin_endpoint(
                    record.name,
                    hook.after_endpoint,
                    request=request,
                    current_user=None,
                    payload={"stage": "after", "target": hook.target_path, "status_code": response.status_code},
                    phase="hook",
                    hook=hook,
                    response_status_code=response.status_code,
                    internal=True,
                )
                state.consecutive_failures = 0
                state.last_error = None
            except Exception as exc:
                state.consecutive_failures += 1
                state.last_error = str(exc)
                logger.warning(
                    "plugins.hook.after.failed plugin={} target={} failures={} error={}",
                    record.name,
                    hook.target_path,
                    state.consecutive_failures,
                    exc,
                )
                if state.consecutive_failures >= max(1, hook.failure_limit):
                    state.blocked = True
                    logger.error("plugins.hook.after.blocked plugin={} target={}", record.name, hook.target_path)

    async def run_health_check(self, plugin_name: str) -> PluginActionResult:
        record = self.records.get(plugin_name)
        if record is None:
            raise HTTPException(status_code=404, detail="Plugin not found")
        was_unavailable = record.state == "unavailable" or not record.available or not record.active_routes
        synthetic_request = self._synthetic_request(f"{API_V1}/plugins/{plugin_name}/health", "POST")
        try:
            await self.execute_plugin_endpoint(
                plugin_name,
                "health",
                request=synthetic_request,
                current_user=None,
                payload={"source": "health-endpoint"},
                phase="health",
                internal=True,
            )
            if was_unavailable:
                await self._restore_record_after_health(record)
            return PluginActionResult(message="Plugin health check passed", plugin_name=plugin_name, state=record.state)
        except Exception as exc:
            return PluginActionResult(message=f"Plugin health check failed: {exc}", plugin_name=plugin_name, state=record.state)

    def _record_to_catalog_entry(self, record: PluginRecord) -> PluginCatalogEntry:
        return PluginCatalogEntry(
            name=record.manifest.name,
            version=record.manifest.version,
            description=record.manifest.description,
            icon=record.manifest.icon,
            source_path=str(record.source_path),
            state=record.state,
            compatible=record.compatible,
            available=record.available,
            min_promptman_version=record.manifest.min_promptman_version,
            max_promptman_version=record.manifest.max_promptman_version,
            last_error=record.last_error,
            unavailable_reason=record.unavailable_reason,
            health_failures=record.health_failures,
            signature_status=record.signature_status,
            signature_signer=record.signature_signer,
            signature_error=record.signature_error,
            runtime_failures={key: state.consecutive_failures for key, state in record.endpoint_states.items() if state.consecutive_failures},
            endpoints=list(record.manifest.endpoints),
            ui_controls=list(record.manifest.ui_controls),
            hooks=list(record.manifest.hooks),
            init_results=dict(record.init_results),
            active_routes=list(record.active_routes),
        )

    async def _discover_or_load_path(self, path: Path, *, activate: bool, force_reload: bool = False) -> None:
        signature_status, signature_signer, signature_error = self._verify_plugin_signature(path)
        if signature_status == "invalid":
            raise RuntimeError(signature_error or f"Invalid plugin signature for {path.name}")
        if self._signed_plugins_required() and signature_status != "verified":
            raise RuntimeError(f"Unsigned plugin {path.name} rejected because PROMPTMAN_PLUGINS_SIGNED_ONLY is enabled")
        module = self._import_module(path, force_reload=force_reload)
        manifest = self._load_manifest(module)
        existing = self.records.get(manifest.name)
        if existing is not None and existing.registered_route_names:
            await self.unload_plugin(manifest.name, remove_from_catalog=False)
        record = PluginRecord(
            name=manifest.name,
            source_path=path,
            manifest=manifest,
            module=module,
            signature_status=signature_status,
            signature_signer=signature_signer,
            signature_error=signature_error,
        )
        self.records[manifest.name] = record

        compatible, reason = self._check_version_compatibility(manifest)
        if not compatible:
            record.compatible = False
            record.available = False
            record.state = "incompatible"
            record.unavailable_reason = reason
            return

        if not activate:
            record.state = "discovered"
            return

        await self._activate_record(record)

    async def _activate_record(self, record: PluginRecord) -> None:
        self._register_plugin_routes(record)
        record.state = "loading"
        try:
            await self._run_record_startup(record, payload_source="plugin-load")
            record.available = True
            record.state = "running"
            record.unavailable_reason = None
            self.app.openapi_schema = None
            logger.info("plugins.loaded name={} version={}", record.name, record.manifest.version)
        except Exception as exc:
            record.available = False
            record.state = "error"
            record.last_error = str(exc)
            record.lifecycle_active = False
            logger.exception("plugins.activate.failed plugin={} error={}", record.name, exc)
            self._unregister_plugin_routes(record)

    async def _run_record_startup(self, record: PluginRecord, *, payload_source: str) -> None:
        lifecycle_context = PluginLifecycleContext(self.app, self, record.name, record.manifest, record.init_results)
        await self._call_with_timeout(
            getattr(record.module, "plugin_init"),
            lifecycle_context,
            timeout_seconds=record.manifest.lifecycle_timeout_seconds,
        )
        record.lifecycle_active = True
        for endpoint in record.manifest.endpoints:
            init_name = f"{endpoint.name}_init"
            init_request = self._synthetic_request(f"{API_V1}/plugins/{record.name}/{init_name}", endpoint.method)
            try:
                result = await self.execute_plugin_endpoint(
                    record.name,
                    init_name,
                    request=init_request,
                    current_user=None,
                    payload={"source": payload_source},
                    phase="init-endpoint",
                    internal=True,
                )
                record.init_results[init_name] = jsonable_encoder(result)
            except Exception as exc:
                logger.warning("plugins.init_endpoint.failed plugin={} endpoint={} error={}", record.name, init_name, exc)
                record.init_results[init_name] = {"ok": False, "error": str(exc)}
        await self._call_with_timeout(
            getattr(record.module, "plugin_postinit"),
            lifecycle_context,
            timeout_seconds=record.manifest.lifecycle_timeout_seconds,
        )

    async def _restore_record_after_health(self, record: PluginRecord) -> None:
        if not record.module:
            return
        if not record.registered_route_names:
            self._register_plugin_routes(record)
        if not record.lifecycle_active:
            await self._run_record_startup(record, payload_source="health-recovery")
        record.available = True
        record.state = "running"
        record.unavailable_reason = None
        self.app.openapi_schema = None
        logger.info("plugins.recovered plugin={} via=health", record.name)

    def _register_plugin_routes(self, record: PluginRecord) -> None:
        record.registered_route_names.clear()
        record.active_routes.clear()
        for endpoint in record.manifest.endpoints:
            self._add_dynamic_route(record, endpoint.name, endpoint, endpoint.name)
            self._add_dynamic_route(record, f"{endpoint.name}_init", endpoint, f"{endpoint.name}_init")

    def _add_dynamic_route(self, record: PluginRecord, route_suffix: str, endpoint: PluginEndpointConfig, endpoint_name: str) -> None:
        method = endpoint.method.upper()
        path = f"{API_V1}/plugins/{record.name}/{route_suffix}"
        route_name = f"plugin_{record.name}_{route_suffix}"

        async def handler(request: Request, current_user: Any = Depends(auth_service.get_current_user)) -> Response:
            payload = await self._extract_payload(request)
            result = await self.execute_plugin_endpoint(
                record.name,
                endpoint_name,
                request=request,
                current_user=current_user,
                payload=payload,
            )
            if isinstance(result, Response):
                return result
            return JSONResponse(content=jsonable_encoder(result))

        handler.__name__ = route_name
        self.app.add_api_route(
            path,
            handler,
            methods=[method],
            name=route_name,
            tags=[f"Plugin:{record.name}"],
            summary=f"{record.name}:{endpoint_name}",
            description=endpoint.description,
            include_in_schema=endpoint.include_in_schema,
        )
        record.registered_route_names.append(route_name)
        record.active_routes.append(f"{method} {path}")
        self.app.openapi_schema = None

    def _unregister_plugin_routes(self, record: PluginRecord) -> None:
        names = set(record.registered_route_names)
        if not names:
            return
        self.app.router.routes = [
            route
            for route in self.app.router.routes
            if not (isinstance(route, APIRoute) and route.name in names)
        ]
        record.registered_route_names.clear()
        record.active_routes.clear()
        self.app.openapi_schema = None

    def _matching_hooks(self, method: str, path: str) -> list[tuple[PluginRecord, PluginHookConfig]]:
        matches: list[tuple[PluginRecord, PluginHookConfig]] = []
        for record in self.records.values():
            if not record.available:
                continue
            for hook in record.manifest.hooks:
                if hook.target_method != method.upper():
                    continue
                if re.fullmatch(self._path_template_to_regex(hook.target_path), path):
                    matches.append((record, hook))
        return matches

    def _path_template_to_regex(self, path_template: str) -> str:
        escaped = re.escape(path_template)
        return re.sub(r"\\\{[^/]+\\\}", r"[^/]+", escaped)

    def _hook_key(self, plugin_name: str, hook: PluginHookConfig, phase: str) -> str:
        return f"{plugin_name}:{phase}:{hook.target_method}:{hook.target_path}:{hook.before_endpoint}:{hook.after_endpoint}"

    def _import_module(self, path: Path, *, force_reload: bool) -> ModuleType:
        relative_name = path.relative_to(self.plugins_dir).with_suffix("").as_posix().replace("/", "__")
        unique_name = f"promptman_plugin_{relative_name}_{path.stat().st_mtime_ns}"
        if force_reload:
            for module_name in [name for name in list(sys.modules.keys()) if name.startswith(f"promptman_plugin_{relative_name}_")]:
                sys.modules.pop(module_name, None)
        spec = importlib.util.spec_from_file_location(unique_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to import plugin from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = module
        spec.loader.exec_module(module)
        return module

    def _load_manifest(self, module: ModuleType) -> PluginManifest:
        self._ensure_contract(module)
        raw_manifest = module.plugin_preinit()
        if isinstance(raw_manifest, PluginManifest):
            return raw_manifest
        return PluginManifest.model_validate(raw_manifest)

    def _ensure_contract(self, module: ModuleType) -> None:
        for name in ("plugin_preinit", "plugin_init", "plugin_postinit", "plugin_run", "plugin_done"):
            if not hasattr(module, name):
                raise RuntimeError(f"Plugin is missing required function: {name}")

    def _check_version_compatibility(self, manifest: PluginManifest) -> tuple[bool, str | None]:
        if self._compare_versions(self.app_version, manifest.min_promptman_version) < 0:
            return False, f"PromptMan {self.app_version} is lower than required {manifest.min_promptman_version}"
        if manifest.max_promptman_version and self._compare_versions(self.app_version, manifest.max_promptman_version) > 0:
            return False, f"PromptMan {self.app_version} is higher than supported {manifest.max_promptman_version}"
        return True, None

    def _compare_versions(self, left: str, right: str) -> int:
        def tokenize(value: str) -> list[int]:
            numbers = [int(part) for part in re.findall(r"\d+", value)]
            return numbers or [0]

        left_tokens = tokenize(left)
        right_tokens = tokenize(right)
        max_len = max(len(left_tokens), len(right_tokens))
        left_tokens.extend([0] * (max_len - len(left_tokens)))
        right_tokens.extend([0] * (max_len - len(right_tokens)))
        if left_tokens < right_tokens:
            return -1
        if left_tokens > right_tokens:
            return 1
        return 0

    async def _call_with_timeout(self, func: Any, *args: Any, timeout_seconds: int) -> Any:
        if inspect.iscoroutinefunction(func):
            return await asyncio.wait_for(func(*args), timeout=max(1, int(timeout_seconds)))
        return await asyncio.wait_for(run_in_threadpool(func, *args), timeout=max(1, int(timeout_seconds)))

    async def _extract_payload(self, request: Request) -> Any:
        body = await request.body()
        if not body:
            return {}
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                return await request.json()
            except Exception:
                return {"raw": body.decode("utf-8", errors="replace")}
        return {"raw": body.decode("utf-8", errors="replace")}

    def _get_endpoint_config(self, record: PluginRecord, endpoint_name: str) -> PluginEndpointConfig | None:
        base_name = endpoint_name[:-5] if endpoint_name.endswith("_init") else endpoint_name
        for endpoint in record.manifest.endpoints:
            if endpoint.name == base_name:
                return endpoint
        if endpoint_name == "health":
            return None
        raise HTTPException(status_code=404, detail="Plugin endpoint not found")

    def _ensure_endpoint_roles(self, current_user: Any | None, endpoint_config: PluginEndpointConfig | None) -> None:
        if endpoint_config is None:
            return
        if current_user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        if endpoint_config.roles and current_user.role not in endpoint_config.roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Role is not allowed for this plugin endpoint")

    async def _mark_health_failure(self, record: PluginRecord, exc: Exception) -> None:
        record.health_failures += 1
        record.last_error = str(exc)
        logger.warning("plugins.health.failed plugin={} failures={} error={}", record.name, record.health_failures, exc)
        if record.health_failures >= 3:
            await self._deactivate_record(record, "Health check failed 3 times in a row")
            logger.error("plugins.health.unavailable plugin={}", record.name)

    def _mark_health_success(self, record: PluginRecord) -> None:
        record.health_failures = 0
        if record.state not in {"unavailable", "stopped"}:
            record.available = True
            record.state = "running"
            record.unavailable_reason = None

    def _mark_runtime_success(self, record: PluginRecord, endpoint_name: str) -> None:
        state = record.endpoint_states.setdefault(endpoint_name, EndpointRuntimeState())
        state.consecutive_failures = 0
        state.blocked = False
        state.last_error = None

    async def _mark_runtime_failure(self, record: PluginRecord, endpoint_name: str, exc: Exception) -> None:
        state = record.endpoint_states.setdefault(endpoint_name, EndpointRuntimeState())
        state.consecutive_failures += 1
        state.last_error = str(exc)
        logger.warning(
            "plugins.runtime.failed plugin={} endpoint={} failures={} error={}",
            record.name,
            endpoint_name,
            state.consecutive_failures,
            exc,
        )
        if state.consecutive_failures >= max(1, int(record.manifest.runtime_failure_limit)):
            state.blocked = True
            await self._deactivate_record(record, f"Endpoint {endpoint_name} failed {state.consecutive_failures} times in a row")

    async def _deactivate_record(self, record: PluginRecord, reason: str) -> None:
        if record.lifecycle_active and record.module and hasattr(record.module, "plugin_done"):
            try:
                await self._call_with_timeout(
                    getattr(record.module, "plugin_done"),
                    PluginLifecycleContext(self.app, self, record.name, record.manifest, dict(record.init_results)),
                    timeout_seconds=record.manifest.lifecycle_timeout_seconds,
                )
            except Exception as exc:
                logger.exception("plugins.deactivate.done_failed plugin={} error={}", record.name, exc)
        record.available = False
        record.state = "unavailable"
        record.unavailable_reason = reason
        record.lifecycle_active = False
        self._unregister_plugin_routes(record)

    def _verify_plugin_signature(self, path: Path) -> tuple[str, str | None, str | None]:
        sidecar_path = path.with_suffix(".signature.json")
        if not sidecar_path.exists():
            return "unsigned", None, None

        if not self.trusted_signers_path.exists():
            return "invalid", None, f"Signature sidecar exists for {path.name}, but trusted_signers.json is missing"

        try:
            envelope = PluginSignatureEnvelope.model_validate(json.loads(sidecar_path.read_text(encoding="utf-8")))
            if envelope.file != path.name:
                return "invalid", envelope.signer_id, f"Signature file target {envelope.file} does not match {path.name}"
            trusted_store_raw = json.loads(self.trusted_signers_path.read_text(encoding="utf-8"))
            signer_payload = trusted_store_raw.get(envelope.signer_id)
            if signer_payload is None:
                return "invalid", envelope.signer_id, f"Unknown signer_id {envelope.signer_id}"
            signer_record = PluginSignerRecord.model_validate({"signer_id": envelope.signer_id, **signer_payload})
            public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(signer_record.public_key.encode("utf-8")))
            signature = base64.b64decode(envelope.signature.encode("utf-8"))
            public_key.verify(signature, path.read_bytes())
            return "verified", signer_record.signer_id, None
        except Exception as exc:
            return "invalid", None, str(exc)

    def _signed_plugins_required(self) -> bool:
        return app_settings.get_bool("PROMPTMAN_PLUGINS_SIGNED_ONLY", default=False)

    def _resolve_route_path(self, request: Request) -> str | None:
        route = request.scope.get("route")
        return getattr(route, "path", None)

    def _synthetic_request(self, path: str, method: str) -> Request:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 0),
            "server": ("127.0.0.1", 80),
            "app": self.app,
        }

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"", "more_body": False}

        return Request(scope, receive)