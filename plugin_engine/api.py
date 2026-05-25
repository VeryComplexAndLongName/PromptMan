from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

import auth as auth_service

from .contracts import (
    PluginActionResult,
    PluginCatalogEntry,
    PluginDiagnosticsOut,
    PluginModalControlUpdateRequest,
    PluginModalSessionOut,
    PluginModalStartRequest,
)


router = APIRouter(prefix="/v1/plugins", tags=["Plugins"])


def _get_engine(request: Request):  # type: ignore[no-untyped-def]
    engine = getattr(request.app.state, "plugin_engine", None)
    if engine is None:
        raise HTTPException(status_code=500, detail="Plugin engine is not configured")
    return engine


@router.get("", response_model=list[PluginCatalogEntry])
def list_plugins(request: Request, _: object = Depends(auth_service.get_current_user)) -> list[PluginCatalogEntry]:
    return _get_engine(request).list_plugins()


@router.post("/_rescan", response_model=PluginActionResult)
async def rescan_plugins(request: Request, _: object = Depends(auth_service.require_admin)) -> PluginActionResult:
    return await _get_engine(request).rescan(auto_activate=True)


@router.post("/{plugin_name}/_load", response_model=PluginActionResult)
async def load_plugin(plugin_name: str, request: Request, _: object = Depends(auth_service.require_admin)) -> PluginActionResult:
    return await _get_engine(request).load_plugin(plugin_name)


@router.post("/{plugin_name}/_reload", response_model=PluginActionResult)
async def reload_plugin(plugin_name: str, request: Request, _: object = Depends(auth_service.require_admin)) -> PluginActionResult:
    return await _get_engine(request).reload_plugin(plugin_name)


@router.delete("/{plugin_name}", response_model=PluginActionResult)
async def unload_plugin(plugin_name: str, request: Request, _: object = Depends(auth_service.require_admin)) -> PluginActionResult:
    return await _get_engine(request).unload_plugin(plugin_name)


@router.post("/{plugin_name}/health", response_model=PluginActionResult)
async def run_plugin_health(plugin_name: str, request: Request, _: object = Depends(auth_service.require_admin)) -> PluginActionResult:
    return await _get_engine(request).run_health_check(plugin_name)


@router.get("/{plugin_name}/_diagnostics", response_model=PluginDiagnosticsOut)
def get_plugin_diagnostics(plugin_name: str, request: Request, _: object = Depends(auth_service.require_admin)) -> PluginDiagnosticsOut:
    return _get_engine(request).get_plugin_diagnostics(plugin_name)


@router.get("/{plugin_name}/modals", response_model=list[PluginModalSessionOut])
def list_plugin_modals(plugin_name: str, request: Request, _: object = Depends(auth_service.get_current_user)) -> list[PluginModalSessionOut]:
    return _get_engine(request).list_modal_sessions(plugin_name)


@router.post("/{plugin_name}/modals", response_model=PluginModalSessionOut)
async def start_plugin_modal(
    plugin_name: str,
    data: PluginModalStartRequest,
    request: Request,
    current_user: object = Depends(auth_service.get_current_user),
) -> PluginModalSessionOut:
    return await _get_engine(request).start_modal_session(plugin_name, request, current_user, data)


@router.get("/{plugin_name}/modals/{session_id}", response_model=PluginModalSessionOut)
def get_plugin_modal(plugin_name: str, session_id: str, request: Request, _: object = Depends(auth_service.get_current_user)) -> PluginModalSessionOut:
    return _get_engine(request).get_modal_session(plugin_name, session_id)


@router.patch("/{plugin_name}/modals/{session_id}/controls/{control_name}", response_model=PluginModalSessionOut)
async def update_plugin_modal_control(
    plugin_name: str,
    session_id: str,
    control_name: str,
    data: PluginModalControlUpdateRequest,
    request: Request,
    current_user: object = Depends(auth_service.get_current_user),
) -> PluginModalSessionOut:
    return await _get_engine(request).update_modal_control(plugin_name, session_id, control_name, request, current_user, data)


@router.post("/{plugin_name}/modals/{session_id}/stop", response_model=PluginModalSessionOut)
async def stop_plugin_modal(plugin_name: str, session_id: str, request: Request, _: object = Depends(auth_service.get_current_user)) -> PluginModalSessionOut:
    return await _get_engine(request).stop_modal_session(plugin_name, session_id)


@router.delete("/{plugin_name}/modals/{session_id}", response_model=PluginActionResult)
async def close_plugin_modal(plugin_name: str, session_id: str, request: Request, _: object = Depends(auth_service.get_current_user)) -> PluginActionResult:
    return await _get_engine(request).close_modal_session(plugin_name, session_id)