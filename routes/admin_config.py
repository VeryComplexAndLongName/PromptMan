from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import app_settings
import auth as auth_service
from app_core.api_version import API_V1
from crud.common import get_global_config, set_global_config
from database import get_db
from models import User

# Router is registered without extra prefix in main.py.
router = APIRouter(prefix=f"{API_V1}/admin/config", tags=["Admin Config"])


@router.get("/", summary="List all global config settings")
def list_global_config(
    _: User = Depends(auth_service.require_admin),
) -> dict[str, str]:
    return app_settings.all_settings()


@router.get("/{key}", summary="Get a single global config value")
def read_global_config(
    key: str,
    db: Session = Depends(get_db),
    _: User = Depends(auth_service.require_admin),
) -> dict[str, str]:
    value = get_global_config(db, key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Config key {key!r} not found")
    return {"key": key, "value": value}


@router.put("/{key}", summary="Update a global config value")
async def update_global_config(
    key: str,
    value: str,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(auth_service.require_admin),
) -> dict[str, str]:
    try:
        app_settings.apply(key, value)  # validate key first
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    set_global_config(db, key, value)
    if key == "PROMPTMAN_PLUGINS_SIGNED_ONLY":
        plugin_engine = getattr(request.app.state, "plugin_engine", None)
        if plugin_engine is not None:
            await plugin_engine.rescan(auto_activate=True)
    return {"key": key, "value": value}
