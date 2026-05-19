from loguru import logger

import auth as auth_service
from database import run_db_call
from schemas import OptimizeConfigOut, OptimizeConfigUpdate


def update_optimize_config_route(data: OptimizeConfigUpdate, db, current_user) -> OptimizeConfigOut:  # type: ignore[no-untyped-def]
    logger.info(
        "optimize.config.update llm_provider={} llm_model={}",
        data.llm_provider,
        data.llm_model,
    )
    cfg = run_db_call(db, auth_service.update_personal_config, current_user, data.model_dump())
    return OptimizeConfigOut(**cfg)
