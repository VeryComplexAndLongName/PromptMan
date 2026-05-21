from __future__ import annotations

import base64
import hashlib
import os
from threading import Lock
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from cache.shared_cache import (
    OPTIMIZATION_CACHE_TTL_SECONDS,
    build_optimization_cache_key,
    cache_get_or_set,
)
import app_settings
from optimizer.leo_backend import LeoPromptOptimizerBackend
from optimizer.provider_catalog import get_llm_provider_models, list_llm_provider_entries
from optimizer.result import OptimizationResult
from optimizer.utils import _normalize_text, _parse_structured_response

if TYPE_CHECKING:
    from collections.abc import Mapping

    from optimizer.base import PromptOptimizerBackend

_runtime_config_lock = Lock()

__all__ = [
    "LeoPromptOptimizerBackend",
    "OptimizationResult",
    "_normalize_text",
    "_parse_structured_response",
    "build_optimizer_config",
    "get_active_optimizer_backend",
    "get_active_optimizer_backend_name",
    "get_llm_provider_catalog",
    "get_runtime_optimizer_config",
    "list_available_models",
    "optimize_prompt_with_active_backend",
    "set_runtime_optimizer_config",
]


# ---------------------------------------------------------------------------
# Token encryption utilities
# ---------------------------------------------------------------------------

def _get_encryption_key() -> bytes:
    machine_id = os.getenv("PROMPTMAN_KEY", os.uname().nodename if hasattr(os, "uname") else "default")
    key_material = hashlib.sha256(machine_id.encode()).digest()
    return base64.urlsafe_b64encode(key_material)


def _encrypt_token(token: str | None) -> str | None:
    if not token or not token.strip():
        return None
    try:
        from cryptography.fernet import Fernet

        cipher = Fernet(_get_encryption_key())
        encrypted = cipher.encrypt(token.strip().encode())
        return encrypted.decode("utf-8")
    except Exception as exc:
        logger.warning("Token encryption failed: {}", exc)
        return None


def _decrypt_token(encrypted_token: str | None) -> str | None:
    if not encrypted_token:
        return None
    try:
        from cryptography.fernet import Fernet

        cipher = Fernet(_get_encryption_key())
        decrypted = cipher.decrypt(encrypted_token.encode())
        return decrypted.decode("utf-8")
    except Exception as exc:
        logger.warning("Token decryption failed: {}", exc)
        return None


_runtime_optimize_config: dict[str, Any] = {
    "llm_provider": "openai",
    "llm_model": "gpt-4o-mini",
    "llm_base_url": "",
    "llm_timeout_seconds": 120,
    "llm_api_token_encrypted": None,
}


def build_optimizer_config(overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    # Settings layer (loaded from DB at startup, defaults from _DEFAULTS)
    env_provider = app_settings.get("OPTIMIZER_PROVIDER", "openai")
    env_model = app_settings.get("OPTIMIZER_MODEL", "gpt-4o-mini")
    env_base_url = app_settings.get("OPTIMIZER_BASE_URL", "")
    env_timeout = app_settings.get_int("OPTIMIZER_TIMEOUT_SECONDS", 120)
    env_api_token = app_settings.get("OPTIMIZER_API_TOKEN", "") or None

    # Per-request overrides layer (runtime config or per-user config)
    rt = overrides or {}
    # Accept both runtime payload keys (llm_*) and serialized effective keys
    # so callers can pass config snapshots from auth.serialize_optimizer_config.
    rt_provider = rt.get("llm_provider") or rt.get("effective_llm_provider")
    rt_model = rt.get("llm_model") or rt.get("effective_llm_model")
    rt_base_url = rt.get("llm_base_url") if rt.get("llm_base_url") is not None else rt.get("effective_llm_base_url")
    rt_timeout = rt.get("llm_timeout_seconds") if rt.get("llm_timeout_seconds") is not None else rt.get("effective_llm_timeout_seconds")
    rt_api_token: str | None = rt.get("llm_api_token") or rt.get("effective_llm_api_token")           # plain-text override
    rt_token_enc: str | None = rt.get("llm_api_token_encrypted")  # pre-encrypted override

    # Effective (runtime wins over env)
    effective_provider = ((rt_provider or "").strip().lower() or env_provider) or "openai"
    effective_model = ((rt_model or "").strip() or env_model) or "gpt-4o-mini"
    effective_base_url = rt_base_url if rt_base_url is not None else env_base_url
    effective_timeout = int(rt_timeout) if rt_timeout is not None else env_timeout

    # Resolve token: plain-text override → encrypted override → env token
    if rt_api_token:
        effective_token_enc = _encrypt_token(rt_api_token)
    elif rt_token_enc:
        effective_token_enc = rt_token_enc
    elif env_api_token:
        effective_token_enc = _encrypt_token(env_api_token)
    else:
        effective_token_enc = None

    effective_api_token = _decrypt_token(effective_token_enc)

    return {
        # Runtime / per-user override layer
        "runtime_llm_provider": rt_provider,
        "runtime_llm_model": rt_model,
        "runtime_llm_base_url": rt_base_url,
        "runtime_llm_timeout_seconds": rt_timeout,
        "runtime_has_llm_api_token": bool(rt_token_enc or rt_api_token),
        # Settings / env layer
        "env_llm_provider": env_provider,
        "env_llm_model": env_model,
        "env_llm_base_url": env_base_url,
        "env_llm_timeout_seconds": env_timeout,
        "env_has_llm_api_token": bool(env_api_token),
        # Effective (merged) layer – used by backends and schema
        "effective_llm_provider": effective_provider,
        "effective_llm_model": effective_model,
        "effective_llm_base_url": effective_base_url,
        "effective_llm_timeout_seconds": effective_timeout,
        "effective_has_llm_api_token": bool(effective_token_enc),
        "effective_llm_api_token": effective_api_token,
    }


def set_runtime_optimizer_config(
    llm_provider: str | None = None,
    llm_model: str | None = None,
    llm_base_url: str | None = None,
    llm_timeout_seconds: int | None = None,
    llm_api_token: str | None = None,
) -> dict[str, Any]:
    with _runtime_config_lock:
        if llm_provider is not None:
            _runtime_optimize_config["llm_provider"] = llm_provider.strip().lower() or "openai"
        if llm_model is not None:
            _runtime_optimize_config["llm_model"] = llm_model.strip() or "gpt-4o-mini"
        if llm_base_url is not None:
            _runtime_optimize_config["llm_base_url"] = llm_base_url.strip()
        if llm_timeout_seconds is not None:
            _runtime_optimize_config["llm_timeout_seconds"] = max(5, int(llm_timeout_seconds))
        if llm_api_token is not None:
            _runtime_optimize_config["llm_api_token_encrypted"] = _encrypt_token(llm_api_token)

    logger.info(
        "optimize.config.runtime_set provider={} model={} base_url={} timeout_s={} has_api_token={}",
        _runtime_optimize_config.get("llm_provider"),
        _runtime_optimize_config.get("llm_model"),
        _runtime_optimize_config.get("llm_base_url"),
        _runtime_optimize_config.get("llm_timeout_seconds"),
        bool(llm_api_token and llm_api_token.strip()),
    )
    return get_runtime_optimizer_config()


def get_runtime_optimizer_config() -> dict[str, Any]:
    with _runtime_config_lock:
        return build_optimizer_config(dict(_runtime_optimize_config))


def get_llm_provider_catalog() -> list[dict[str, Any]]:
    return [
        {
            "key": entry.key,
            "label": entry.label,
            "base_url": entry.base_url,
            "requires_api_token": entry.requires_api_token,
            "models": list(entry.models),
        }
        for entry in list_llm_provider_entries()
    ]


# ---------------------------------------------------------------------------
# Backend registry and public API
# ---------------------------------------------------------------------------

_BACKEND_REGISTRY: dict[str, PromptOptimizerBackend] = {
    "leo": LeoPromptOptimizerBackend(),
}


def get_active_optimizer_backend_name() -> str:
    configured = app_settings.get("OPTIMIZER_BACKEND", "leo").strip().lower() or "leo"
    if configured not in _BACKEND_REGISTRY:
        logger.warning("optimize.backend.unknown configured={} fallback=leo", configured)
        return "leo"
    return configured


def get_active_optimizer_backend() -> PromptOptimizerBackend:
    return _BACKEND_REGISTRY[get_active_optimizer_backend_name()]


def optimize_prompt_with_active_backend(fields: Mapping[str, str | None], config_override: Mapping[str, Any] | None = None) -> OptimizationResult:
    backend = get_active_optimizer_backend()
    config = build_optimizer_config(config_override)
    cache_key = build_optimization_cache_key(fields, config, backend.name)
    return cast("OptimizationResult", cache_get_or_set(cache_key, OPTIMIZATION_CACHE_TTL_SECONDS, lambda: backend.optimize(fields, config)))


def list_available_models(
    provider: str,
    *,
    base_url: str | None = None,
    timeout_seconds: int = 5,
    api_token: str | None = None,
    config_override: Mapping[str, Any] | None = None,
) -> list[str]:
    backend = get_active_optimizer_backend()
    return backend.list_models(
        provider,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_token=api_token,
        config_override=config_override,
    )
