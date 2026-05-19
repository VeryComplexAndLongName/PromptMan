from loguru import logger

from routes.shared import get_personal_config
from schemas import OptimizeConfigOut


def get_optimize_config_route(db, current_user) -> OptimizeConfigOut:  # type: ignore[no-untyped-def]
    cfg = get_personal_config(db, current_user)
    logger.info(
        "optimize.config.get effective_llm_provider={} effective_llm_model={}",
        cfg.get("effective_llm_provider"),
        cfg.get("effective_llm_model"),
    )
    return OptimizeConfigOut(**cfg)
