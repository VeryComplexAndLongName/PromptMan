from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LlmProviderCatalogEntry:
    key: str
    label: str
    base_url: str
    requires_api_token: bool
    models: tuple[str, ...]


_PROVIDER_CATALOG: tuple[LlmProviderCatalogEntry, ...] = (
    LlmProviderCatalogEntry(
        key="ollama",
        label="Ollama (Local)",
        base_url="http://127.0.0.1:11434",
        requires_api_token=False,
        models=(
            "qwen2.5:3b-instruct-q4_K_M",
            "qwen2.5:0.5b",
            "qwen3:4b",
            "llama3.2:1b",
            "llama3.2:latest",
            "llama3.1:latest",
            "deepseek-r1:latest",
            "codellama:latest",
            "gemma2:2b",
        ),
    ),
    LlmProviderCatalogEntry(
        key="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        requires_api_token=True,
        # OpenAI model availability is account/subscription-specific — no static catalog.
        # Without an API token the endpoint returns []; with a token the caller can
        # supply a token-based override or the UI allows free-form model entry.
        models=(),
    ),
    LlmProviderCatalogEntry(
        key="anthropic",
        label="Anthropic Claude",
        base_url="https://api.anthropic.com",
        requires_api_token=True,
        models=(),
    ),
    LlmProviderCatalogEntry(
        key="groq",
        label="Groq",
        base_url="https://api.groq.com/openai/v1",
        requires_api_token=True,
        models=(),
    ),
    LlmProviderCatalogEntry(
        key="gemini",
        label="Google Gemini",
        base_url="https://generativelanguage.googleapis.com",
        requires_api_token=True,
        models=(),
    ),
    LlmProviderCatalogEntry(
        key="mistral",
        label="Mistral",
        base_url="https://api.mistral.ai",
        requires_api_token=True,
        models=(),
    ),
)


def list_llm_provider_entries() -> list[LlmProviderCatalogEntry]:
    return list(_PROVIDER_CATALOG)


def get_llm_provider_entry(provider: str | None) -> LlmProviderCatalogEntry | None:
    normalized = (provider or "").strip().lower()
    for entry in _PROVIDER_CATALOG:
        if entry.key == normalized:
            return entry
    return None


def get_llm_provider_models(provider: str | None) -> list[str]:
    entry = get_llm_provider_entry(provider)
    if entry is None:
        return []
    return list(entry.models)
