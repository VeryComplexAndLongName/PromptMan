from collections.abc import Callable

from loguru import logger
from sqlalchemy.orm import Session

from models import User
from routes.shared import get_personal_config


def list_llm_provider_models_route(
    provider: str,
    base_url: str | None,
    api_token: str | None,
    timeout_seconds: int,
    db: Session,
    current_user: User,
    model_lister: Callable[..., list[str]],
) -> list[str]:
    logger.info("llm.provider.models provider={}", provider)
    return model_lister(
        provider,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        api_token=api_token,
        config_override=get_personal_config(db, current_user),
    )


def get_provider_models_route(
    provider: str,
    base_url: str | None,
    api_token: str | None,
    timeout_seconds: int,
    db: Session,
    current_user: User,
    model_lister: Callable[..., list[str]],
) -> list[str]:
    return list_llm_provider_models_route(provider, base_url, api_token, timeout_seconds, db, current_user, model_lister)

