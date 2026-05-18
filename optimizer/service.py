from __future__ import annotations

import base64
import hashlib
import os
from threading import Lock
from typing import Any

from loguru import logger

from optimizer.result import OptimizationResult
from optimizer.errors import BackendOperationTimeoutError
from optimizer.base import PromptOptimizerBackend
from optimizer.leo_backend import LeoPromptOptimizerBackend
from optimizer.utils import (
    _normalize_text,
    _build_full_prompt,
    _heuristic_improve,
    _extract_prefixed_section,
    _build_backend_failure_note,
    _parse_structured_response,
    _run_with_timeout,
)
from cache.shared_cache import OPTIMIZATION_CACHE_TTL_SECONDS, build_optimization_cache_key, cache_get_or_set

_runtime_config_lock = Lock()


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


def build_optimizer_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if overrides is None:
        with _runtime_config_lock:
            source = dict(_runtime_optimize_config)
    else:
        source = overrides

    runtime_provider = source.get("llm_provider", source.get("runtime_llm_provider"))
    runtime_model = source.get("llm_model", source.get("runtime_llm_model"))
    runtime_base_url = source.get("llm_base_url", source.get("runtime_llm_base_url"))
    runtime_timeout_seconds = source.get("llm_timeout_seconds", source.get("runtime_llm_timeout_seconds"))
    runtime_api_token = source.get("llm_api_token", source.get("effective_llm_api_token"))
    runtime_api_token_encrypted = source.get("llm_api_token_encrypted")

    env_provider = os.getenv("OPTIMIZER_PROVIDER", os.getenv("OPTIMIZE_LLM_PROVIDER", "")).strip().lower() or None
    env_model = os.getenv("OPTIMIZER_MODEL", os.getenv("OPTIMIZE_LLM_MODEL", "")).strip() or None
    env_base_url = os.getenv("OPTIMIZER_BASE_URL", os.getenv("OLLAMA_BASE_URL", "")).strip() or None
    env_api_token_encrypted = os.getenv("OPTIMIZER_API_TOKEN", os.getenv("OPTIMIZE_LLM_API_TOKEN", "")).strip() or None
    env_timeout_raw = os.getenv("OPTIMIZER_TIMEOUT_SECONDS", os.getenv("OPTIMIZE_LLM_TIMEOUT_SECONDS", "")).strip()
    env_timeout_seconds = int(env_timeout_raw) if env_timeout_raw.isdigit() else None

    effective_provider = (runtime_provider or env_provider or "openai").strip().lower()
    default_model_by_provider = {
        "ollama": "qwen2.5:0.5b",
        "openai": "gpt-4o-mini",
        "anthropic": "claude-3-haiku",
        "groq": "llama3-8b-8192",
        "gemini": "gemini-1.5-flash",
        "mistral": "mistral-small-latest",
    }
    effective_model = (runtime_model or env_model or default_model_by_provider.get(effective_provider, "gpt-4o-mini")).strip()
    effective_base_url = (runtime_base_url or env_base_url or "").strip()
    effective_timeout_seconds = int(runtime_timeout_seconds or env_timeout_seconds or 120)
    effective_api_token = runtime_api_token or _decrypt_token(runtime_api_token_encrypted or env_api_token_encrypted)

    return {
        "runtime_llm_provider": runtime_provider,
        "runtime_llm_model": runtime_model,
        "runtime_llm_base_url": runtime_base_url,
        "runtime_llm_timeout_seconds": runtime_timeout_seconds,
        "runtime_has_llm_api_token": runtime_api_token_encrypted is not None,
        "env_llm_provider": env_provider,
        "env_llm_model": env_model,
        "env_llm_base_url": env_base_url,
        "env_llm_timeout_seconds": env_timeout_seconds,
        "env_has_llm_api_token": env_api_token_encrypted is not None,
        "effective_llm_provider": effective_provider,
        "effective_llm_model": effective_model,
        "effective_llm_base_url": effective_base_url,
        "effective_llm_timeout_seconds": effective_timeout_seconds,
        "effective_has_llm_api_token": effective_api_token is not None,
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


# ---------------------------------------------------------------------------
# Backend registry and public API
# ---------------------------------------------------------------------------

_BACKEND_REGISTRY: dict[str, PromptOptimizerBackend] = {
    "leo": LeoPromptOptimizerBackend(),
}


def get_active_optimizer_backend_name() -> str:
    configured = os.getenv("OPTIMIZER_BACKEND", "leo").strip().lower() or "leo"
    if configured not in _BACKEND_REGISTRY:
        logger.warning("optimize.backend.unknown configured={} fallback=leo", configured)
        return "leo"
    return configured


def get_active_optimizer_backend() -> PromptOptimizerBackend:
    return _BACKEND_REGISTRY[get_active_optimizer_backend_name()]


def optimize_prompt_with_active_backend(fields: dict[str, str | None], config_override: dict[str, Any] | None = None) -> OptimizationResult:
    backend = get_active_optimizer_backend()
    config = build_optimizer_config(config_override)
    cache_key = build_optimization_cache_key(fields, config, backend.name)
    return cache_get_or_set(cache_key, OPTIMIZATION_CACHE_TTL_SECONDS, lambda: backend.optimize(fields, config))


def list_available_models(
    provider: str,
    *,
    base_url: str | None = None,
    timeout_seconds: int = 5,
    api_token: str | None = None,
    config_override: dict[str, Any] | None = None,
) -> list[str]:
    backend = get_active_optimizer_backend()
    return backend.list_models(
        provider,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_token=api_token,
        config_override=config_override,
    )
