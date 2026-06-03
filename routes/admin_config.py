import hashlib
import json
from typing import Literal
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener, urlopen
from urllib.request import Request as UrlRequest

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

import app_settings
import auth as auth_service
from app_core.api_version import API_V1
from cache.shared_cache import cache_get_or_set
from crud.common import get_global_config, set_global_config
from database import get_db
from models import User
from runtime_cache import reset_runtime_cache

# Router is registered without extra prefix in main.py.
router = APIRouter(prefix=f"{API_V1}/admin/config", tags=["Admin Config"])

PROVIDER_CATALOG: dict[str, dict[str, str]] = {
    "openai": {"default_base_url": "https://api.openai.com/v1", "kind": "openai-compatible"},
    "ollama": {"default_base_url": "http://127.0.0.1:11434", "kind": "ollama"},
    "anthropic": {"default_base_url": "https://api.anthropic.com/v1", "kind": "openai-compatible"},
    "gemini": {"default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "kind": "openai-compatible"},
}

BACKEND_OPTIONS: list[str] = ["leo"]
PROVIDER_MODELS_CACHE_TTL_SECONDS = 20


class LlmAutoConfigureRequest(BaseModel):
    provider: str = Field(default="ollama", min_length=1)
    strategy: Literal["uniform", "intelligent"] = "intelligent"
    base_url: str | None = None
    api_token: str | None = None
    preferred_model: str | None = None


def _pick_best_model(models: list[str], *, tier: Literal["simple", "primary"], preferred: str | None = None) -> str:
    if preferred and preferred in models:
        return preferred

    if not models:
        return ""

    def _is_embedding_model(model_name: str) -> bool:
        lowered = model_name.lower()
        return "embed" in lowered or "embedding" in lowered or "rerank" in lowered

    candidate_models = [model for model in models if not _is_embedding_model(model)]
    if not candidate_models:
        candidate_models = list(models)

    positive_simple = ("mini", "small", "flash", "haiku", "3b", "2b", "1b")
    positive_primary = ("gpt-4", "sonnet", "opus", "pro", "70b", "32b", "27b", "14b", "13b", "8b")
    negative_primary = ("mini", "small", "flash", "haiku", "1b", "2b", "3b")
    chat_markers = ("llama", "qwen", "gpt", "claude", "gemini", "mistral", "deepseek", "phi", "instruct")

    scored: list[tuple[int, str]] = []
    for model in candidate_models:
        name = model.lower()
        score = 0
        if tier == "simple":
            score += sum(18 for token in positive_simple if token in name)
            score += 4 if "instruct" in name else 0
            score -= 10 if "70b" in name or "32b" in name else 0
        else:
            score += sum(16 for token in positive_primary if token in name)
            score -= sum(12 for token in negative_primary if token in name)
            score += 4 if "instruct" in name else 0
        score += sum(3 for marker in chat_markers if marker in name)
        if _is_embedding_model(name):
            score -= 40
        scored.append((score, model))

    scored.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    return scored[0][1]


def _default_model_for_provider(provider: str, tier: Literal["simple", "primary"]) -> str:
    default_by_provider: dict[str, dict[str, str]] = {
        "ollama": {"simple": "llama3.2:3b", "primary": "llama3.1:8b"},
        "openai": {"simple": "gpt-4o-mini", "primary": "gpt-4o"},
        "anthropic": {"simple": "claude-3-5-haiku-latest", "primary": "claude-3-5-sonnet-latest"},
        "gemini": {"simple": "gemini-2.0-flash", "primary": "gemini-1.5-pro"},
    }
    return default_by_provider.get(provider, {}).get(tier, "")


def _build_llm_plan(
    *,
    provider: str,
    base_url: str,
    preferred_model: str | None,
    strategy: Literal["uniform", "intelligent"],
    discovered_models: list[str],
) -> dict[str, object]:
    simple_model = _pick_best_model(discovered_models, tier="simple") or _default_model_for_provider(provider, "simple")
    primary_model = (
        _pick_best_model(discovered_models, tier="primary", preferred=preferred_model)
        or _default_model_for_provider(provider, "primary")
        or simple_model
    )

    if strategy == "uniform":
        if preferred_model and preferred_model.strip():
            unified = preferred_model.strip()
        elif discovered_models:
            unified = discovered_models[0]
        else:
            unified = primary_model or simple_model
        primary_model = unified
        simple_model = unified

    config_updates: dict[str, str] = {
        "OPTIMIZER_PROVIDER": provider,
        "OPTIMIZER_MODEL": primary_model,
        "OPTIMIZER_BASE_URL": base_url,
        "PROMPT_COMPRESSION_PROVIDER": provider,
        "PROMPT_COMPRESSION_MODEL": simple_model,
        "PROMPT_COMPRESSION_BASE_URL": base_url,
        "TEST_LLM_PROVIDER": provider,
        "TEST_LLM_MODEL": primary_model,
        "TEST_LLM_BASE_URL": base_url,
        "TEST_LLM_USE_OPTIMIZER_FALLBACK": "false",
    }

    if provider == "ollama":
        config_updates["OLLAMA_BASE_URL"] = base_url

    return {
        "selected_models": {
            "primary": primary_model,
            "simple": simple_model,
        },
        "config_updates": config_updates,
    }


def _fetch_provider_models(provider_name: str, base_url: str, token: str) -> list[str]:
    if provider_name == "ollama":
        return _fetch_ollama_models(base_url)
    return _fetch_openai_models(base_url, token)


def _provider_models_cache_key(provider_name: str, base_url: str, token: str) -> str:
    token_fp = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12] if token else ""
    return f"admin:provider-models:{provider_name}:{base_url.rstrip('/')}:{token_fp}"


def _fetch_provider_models_cached(provider_name: str, base_url: str, token: str) -> list[str]:
    cache_key = _provider_models_cache_key(provider_name, base_url, token)
    return cache_get_or_set(
        cache_key,
        PROVIDER_MODELS_CACHE_TTL_SECONDS,
        lambda: _fetch_provider_models(provider_name, base_url, token),
    )


def _http_get_json(url: str, headers: dict[str, str] | None = None, timeout_seconds: float = 12.0) -> dict | list:
    request = UrlRequest(url, headers=headers or {}, method="GET")
    host = (urlparse(url).hostname or "").lower()
    bypass_proxy = host in {"localhost", "::1"} or host.startswith("127.")
    try:
        if bypass_proxy:
            opener = build_opener(ProxyHandler({}))
            response_ctx = opener.open(request, timeout=timeout_seconds)
        else:
            response_ctx = urlopen(request, timeout=timeout_seconds)
        with response_ctx as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload)
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"Provider request failed: {exc}") from exc


def _resolve_provider_base_url(provider: str, base_url_override: str | None) -> str:
    if base_url_override and base_url_override.strip():
        return base_url_override.strip().rstrip("/")
    configured = app_settings.get("OPTIMIZER_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return PROVIDER_CATALOG.get(provider, {}).get("default_base_url", "").rstrip("/")


def _resolve_provider_token(api_token_override: str | None) -> str:
    if api_token_override and api_token_override.strip():
        return api_token_override.strip()
    return app_settings.get("OPTIMIZER_API_TOKEN", "").strip()


def _fetch_openai_models(base_url: str, token: str) -> list[str]:
    if not token:
        return []
    payload = _http_get_json(
        f"{base_url.rstrip('/')}/models",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    data = payload.get("data", []) if isinstance(payload, dict) else []
    models = [item.get("id", "") for item in data if isinstance(item, dict)]
    return sorted([m for m in models if m])


def _fetch_ollama_models(base_url: str) -> list[str]:
    payload = _http_get_json(f"{base_url.rstrip('/')}/api/tags")
    rows = payload.get("models", []) if isinstance(payload, dict) else []
    models = [item.get("name", "") for item in rows if isinstance(item, dict)]
    return sorted([m for m in models if m])


@router.get("/", summary="List all global config settings")
def list_global_config(
    _: User = Depends(auth_service.require_admin),
) -> dict[str, str]:
    return app_settings.all_settings()


@router.get("/meta/providers", summary="List supported optimizer providers and backends")
def list_optimizer_provider_meta(
    _: User = Depends(auth_service.require_admin),
) -> dict[str, object]:
    return {
        "providers": [
            {
                "name": name,
                "default_base_url": data["default_base_url"],
                "kind": data.get("kind", "openai-compatible"),
            }
            for name, data in PROVIDER_CATALOG.items()
        ],
        "backends": BACKEND_OPTIONS,
    }


@router.get("/meta/providers/{provider}/models", summary="List available models for a provider")
def list_optimizer_provider_models(
    provider: str,
    base_url: str | None = Query(default=None),
    api_token: str | None = Query(default=None),
    _: User = Depends(auth_service.require_admin),
) -> dict[str, object]:
    provider_name = provider.strip().lower()
    if provider_name not in PROVIDER_CATALOG:
        raise HTTPException(status_code=404, detail=f"Unsupported provider: {provider}")

    resolved_base_url = _resolve_provider_base_url(provider_name, base_url)
    resolved_token = _resolve_provider_token(api_token)

    warning: str | None = None
    try:
        models = _fetch_provider_models_cached(provider_name, resolved_base_url, resolved_token)
    except HTTPException as exc:
        models = []
        warning = str(exc.detail)

    response: dict[str, object] = {
        "provider": provider_name,
        "base_url": resolved_base_url,
        "models": models,
    }
    if warning:
        response["warning"] = warning
    return response


@router.post("/llm/autoconfigure/preview", summary="Preview unified/intelligent LLM plan")
def preview_llm_autoconfigure(
    payload: LlmAutoConfigureRequest,
    _: User = Depends(auth_service.require_admin),
) -> dict[str, object]:
    provider_name = payload.provider.strip().lower()
    if provider_name not in PROVIDER_CATALOG:
        raise HTTPException(status_code=404, detail=f"Unsupported provider: {payload.provider}")

    resolved_base_url = _resolve_provider_base_url(provider_name, payload.base_url)
    resolved_token = _resolve_provider_token(payload.api_token)
    warning: str | None = None
    discovered_models: list[str] = []
    try:
        discovered_models = _fetch_provider_models_cached(provider_name, resolved_base_url, resolved_token)
    except HTTPException as exc:
        warning = str(exc.detail)

    plan = _build_llm_plan(
        provider=provider_name,
        base_url=resolved_base_url,
        preferred_model=payload.preferred_model,
        strategy=payload.strategy,
        discovered_models=discovered_models,
    )

    response: dict[str, object] = {
        "provider": provider_name,
        "strategy": payload.strategy,
        "base_url": resolved_base_url,
        "discovered_models": discovered_models,
        "selected_models": plan["selected_models"],
        "config_updates": plan["config_updates"],
    }
    if warning:
        response["warning"] = warning
    return response


@router.post("/llm/autoconfigure/apply", summary="Apply unified/intelligent LLM plan")
def apply_llm_autoconfigure(
    payload: LlmAutoConfigureRequest,
    db: Session = Depends(get_db),
    _: User = Depends(auth_service.require_admin),
) -> dict[str, object]:
    preview = preview_llm_autoconfigure(payload=payload, _=_)
    updates = dict(preview.get("config_updates", {}))
    if payload.api_token and payload.api_token.strip():
        token = payload.api_token.strip()
        updates["OPTIMIZER_API_TOKEN"] = token
        updates["PROMPT_COMPRESSION_API_TOKEN"] = token
        updates["TEST_LLM_API_TOKEN"] = token

    for key, value in updates.items():
        app_settings.apply(key, value)
        set_global_config(db, key, value)

    safe_updates = {key: ("updated" if "TOKEN" in key else value) for key, value in updates.items()}

    return {
        "status": "applied",
        "provider": preview.get("provider"),
        "strategy": preview.get("strategy"),
        "base_url": preview.get("base_url"),
        "discovered_models": preview.get("discovered_models"),
        "selected_models": preview.get("selected_models"),
        "applied": safe_updates,
        "warning": preview.get("warning"),
    }


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
    await run_in_threadpool(set_global_config, db, key, value)
    if key in {
        "PROMPTMAN_RUNTIME_CACHE_BACKEND",
        "PROMPTMAN_RUNTIME_CACHE_URL",
        "PROMPTMAN_RUNTIME_CACHE_NAMESPACE",
        "PROMPTMAN_RUNTIME_CACHE_DISABLE_INTERNAL",
    }:
        reset_runtime_cache()
    if key == "PROMPTMAN_PLUGINS_SIGNED_ONLY":
        plugin_engine = getattr(request.app.state, "plugin_engine", None)
        if plugin_engine is not None:
            await plugin_engine.rescan(auto_activate=True)
    return {"key": key, "value": value}
