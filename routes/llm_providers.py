from collections.abc import Callable

from loguru import logger


def list_llm_providers_route(provider_catalog: Callable[[], list[dict]]) -> list[dict]:
    logger.info("llm.providers.list")
    return provider_catalog()
