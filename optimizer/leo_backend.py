from __future__ import annotations

import json
import os
import re
import time
from typing import TYPE_CHECKING, Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from loguru import logger

from optimizer.base import PromptOptimizerBackend
from optimizer.result import OptimizationResult
from optimizer.utils import (
    _build_backend_failure_note,
    _build_full_prompt,
    _heuristic_improve,
    _normalize_text,
    _parse_structured_response,
    _run_with_timeout,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


class LeoPromptOptimizerBackend(PromptOptimizerBackend):
    @property
    def name(self) -> str:
        return "leo"

    def _normalize_ollama_base_url(self, base_url: str | None) -> str:
        env_base_url = os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
        candidate = (base_url or env_base_url).strip()
        if not candidate:
            candidate = "http://127.0.0.1:11434"
        candidate = candidate.rstrip("/")
        if candidate.endswith("/api"):
            candidate = candidate[:-4]
        if not candidate.endswith("/v1"):
            candidate = f"{candidate}/v1"
        return candidate

    def _looks_like_ollama_base_url(self, base_url: str | None) -> bool:
        if not base_url:
            return False
        candidate = base_url.strip().lower()
        return ":11434" in candidate or "localhost" in candidate or "127.0.0.1" in candidate or "ollama" in candidate

    def _is_ollama_memory_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "requires more system memory" in message or "insufficient memory" in message

    def _pick_low_memory_ollama_model(self, models: list[str], current_model: str) -> str | None:
        preferred = [
            "qwen2.5:0.5b",
            "qwen2.5:1.5b",
            "llama3.2:1b",
            "gemma2:2b",
            "phi3:mini",
        ]

        normalized_current = (current_model or "").strip().lower()
        normalized_models = [m.strip() for m in models if isinstance(m, str) and m.strip()]
        lower_to_original = {m.lower(): m for m in normalized_models}

        for candidate in preferred:
            candidate_lower = candidate.lower()
            if candidate_lower != normalized_current and candidate_lower in lower_to_original:
                return lower_to_original[candidate_lower]

        size_pattern = re.compile(r"(\d+(?:\.\d+)?)b")
        sized: list[tuple[float, str]] = []
        for model in normalized_models:
            match = size_pattern.search(model.lower())
            if match:
                sized.append((float(match.group(1)), model))

        sized.sort(key=lambda item: item[0])
        for _, model in sized:
            if model.lower() != normalized_current:
                return model

        return None

    def _build_provider(self, provider_name: str, api_token: str | None, base_url: str | None) -> tuple[Any, str]:
        from leo_prompt_optimizer import (
            AnthropicProvider,
            GeminiProvider,
            GroqProvider,
            MistralProvider,
            OpenAIProvider,
        )

        normalized = (provider_name or "openai").strip().lower()
        if normalized == "openai":
            if self._looks_like_ollama_base_url(base_url):
                ollama_key = (api_token or "ollama").strip() or "ollama"
                ollama_url = self._normalize_ollama_base_url(base_url)
                return OpenAIProvider(api_key=ollama_key, base_url=ollama_url), "openai-compat-ollama"

            key: str | None = (api_token or "").strip() or None
            url: str | None = (base_url or "").strip() or None
            return OpenAIProvider(api_key=key, base_url=url), "openai"
        if normalized == "ollama":
            key = (api_token or "ollama").strip() or "ollama"
            url = self._normalize_ollama_base_url(base_url)
            return OpenAIProvider(api_key=key, base_url=url), "ollama"
        if normalized == "anthropic":
            return AnthropicProvider(api_key=api_token), "anthropic"
        if normalized == "groq":
            return GroqProvider(api_key=api_token), "groq"
        if normalized == "gemini":
            return GeminiProvider(api_key=api_token), "gemini"
        if normalized == "mistral":
            return MistralProvider(api_key=api_token), "mistral"

        raise ValueError(f"Unsupported provider: {normalized}")

    def optimize(self, fields: Mapping[str, str | None], config: Mapping[str, Any]) -> OptimizationResult:
        from leo_prompt_optimizer import LeoOptimizer

        provider_name = str(config["effective_llm_provider"])
        model_name = str(config["effective_llm_model"])
        base_url = config.get("effective_llm_base_url")
        api_token = config.get("effective_llm_api_token")
        timeout_seconds = max(5, int(config.get("effective_llm_timeout_seconds") or 120))

        sanitized = {
            "role": _normalize_text(fields.get("role")),
            "task": _normalize_text(fields.get("task")) or "",
            "context": _normalize_text(fields.get("context")),
            "constraints": _normalize_text(fields.get("constraints")),
            "output_format": _normalize_text(fields.get("output_format")),
            "examples": _normalize_text(fields.get("examples")),
        }

        logger.info("optimize.backend.start backend={} provider={} model={}", self.name, provider_name, model_name)
        start_time = time.monotonic()

        try:
            provider, resolved_provider = self._build_provider(provider_name, api_token, base_url)
            optimizer = LeoOptimizer(provider=provider, default_model=model_name)
            raw_result = _run_with_timeout(
                lambda: optimizer.optimize(
                    prompt_draft=_build_full_prompt(sanitized),
                    top_instruction=(
                        "Optimize this prompt for clarity and reliability. "
                        "Prefer preserving structure with fields Role/Task/Context/Constraints/Output format/Examples."
                    ),
                    model=model_name,
                ),
                timeout_seconds,
                "leo.optimize",
            )
            parsed = _parse_structured_response(raw_result or "", sanitized)
            elapsed_seconds = time.monotonic() - start_time
            return OptimizationResult(
                engine=f"{self.name}-{resolved_provider}:{model_name}",
                optimized_fields=parsed,
                optimized_markdown=_build_full_prompt(parsed),
                notes=[
                    "Optimized with active backend.",
                    f"Backend: {self.name}",
                    f"Provider: {resolved_provider}",
                    f"Model: {model_name}",
                ],
                elapsed_seconds=elapsed_seconds,
            )
        except Exception as exc:
            if (provider_name or "").strip().lower() == "ollama" and self._is_ollama_memory_error(exc):
                available_models = self.list_models(
                    "ollama",
                    base_url=base_url,
                    timeout_seconds=max(5, int(config.get("effective_llm_timeout_seconds") or 5)),
                    api_token=api_token,
                    config_override=config,
                )
                low_memory_model = self._pick_low_memory_ollama_model(available_models, model_name)
                if low_memory_model:
                    try:
                        logger.warning(
                            "optimize.backend.retry_low_memory provider={} from_model={} to_model={}",
                            provider_name,
                            model_name,
                            low_memory_model,
                        )
                        retry_provider, resolved_provider = self._build_provider(provider_name, api_token, base_url)
                        retry_optimizer = LeoOptimizer(provider=retry_provider, default_model=low_memory_model)
                        retry_raw_result = _run_with_timeout(
                            lambda: retry_optimizer.optimize(
                                prompt_draft=_build_full_prompt(sanitized),
                                top_instruction=(
                                    "Optimize this prompt for clarity and reliability. "
                                    "Prefer preserving structure with fields Role/Task/Context/Constraints/Output format/Examples."
                                ),
                                model=low_memory_model,
                            ),
                            timeout_seconds,
                            "leo.optimize.retry_low_memory",
                        )
                        retry_parsed = _parse_structured_response(retry_raw_result or "", sanitized)
                        elapsed_seconds = time.monotonic() - start_time
                        return OptimizationResult(
                            engine=f"{self.name}-{resolved_provider}:{low_memory_model}",
                            optimized_fields=retry_parsed,
                            optimized_markdown=_build_full_prompt(retry_parsed),
                            notes=[
                                "Optimized with active backend.",
                                f"Backend: {self.name}",
                                f"Provider: {resolved_provider}",
                                f"Model: {low_memory_model}",
                                f"Switched from {model_name} due to memory constraints.",
                            ],
                            elapsed_seconds=elapsed_seconds,
                        )
                    except Exception as retry_exc:
                        exc = RuntimeError(f"{exc}; retry_with_low_memory_model_failed: {retry_exc}")

            logger.exception("optimize.backend.error backend={} provider={} model={}", self.name, provider_name, model_name)
            elapsed_seconds = time.monotonic() - start_time
            fallback = _heuristic_improve(sanitized)
            return OptimizationResult(
                engine=f"{self.name}-fallback",
                optimized_fields=fallback,
                optimized_markdown=_build_full_prompt(fallback),
                notes=[
                    _build_backend_failure_note(exc, timeout_seconds, elapsed_seconds),
                    "Fallback optimization was used.",
                ],
                elapsed_seconds=elapsed_seconds,
            )

    def list_models(
        self,
        provider: str,
        *,
        base_url: str | None = None,
        timeout_seconds: int = 5,
        api_token: str | None = None,
        config_override: Mapping[str, Any] | None = None,
    ) -> list[str]:
        normalized = (provider or "").strip().lower()
        if normalized == "openai" and self._looks_like_ollama_base_url(base_url):
            normalized = "ollama"

        if normalized == "ollama":
            configured_base_url = (base_url or "").strip()
            if not configured_base_url and config_override:
                configured_base_url = (config_override.get("effective_llm_base_url") or "").strip()
            if not configured_base_url:
                configured_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()

            normalized_openai_base = self._normalize_ollama_base_url(configured_base_url)
            service_base = normalized_openai_base[:-3] if normalized_openai_base.endswith("/v1") else normalized_openai_base
            tags_url = f"{service_base.rstrip('/')}/api/tags"
            try:
                with urllib_request.urlopen(tags_url, timeout=timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                models = payload.get("models") if isinstance(payload, dict) else []
                names = []
                for model in models or []:
                    if isinstance(model, dict):
                        name = (model.get("name") or "").strip()
                        if name:
                            names.append(name)
                return sorted(set(names))
            except (urllib_error.URLError, urllib_error.HTTPError, TimeoutError, json.JSONDecodeError):
                return []

        if normalized == "openai":
            if not (api_token or "").strip():
                return []
            return ["gpt-4o", "gpt-4o-mini", "gpt-4.1-mini"]
        if normalized == "anthropic":
            return ["claude-3-5-sonnet", "claude-3-haiku"]
        if normalized == "groq":
            return ["llama-3.3-70b-versatile", "llama3-8b-8192"]
        if normalized == "gemini":
            return ["gemini-1.5-pro", "gemini-1.5-flash"]
        if normalized == "mistral":
            return ["mistral-large-latest", "mistral-small-latest"]
        return []
