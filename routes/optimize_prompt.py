from routes.shared import get_personal_config
from loguru import logger
from schemas import PromptData, PromptOptimizeResponse

def build_prompt_optimize_response(result) -> PromptOptimizeResponse:  # type: ignore[no-untyped-def]
    optimized_dict = result.optimized_fields
    if not isinstance(optimized_dict, dict):
        optimized_dict = {}
    optimized = PromptData(
        role=optimized_dict.get("role"),
        task=optimized_dict.get("task") or "",
        context=optimized_dict.get("context"),
        constraints=optimized_dict.get("constraints"),
        output_format=optimized_dict.get("output_format"),
        examples=optimized_dict.get("examples"),
    )
    return PromptOptimizeResponse(
        engine=result.engine,
        optimized=optimized,
        optimized_markdown=result.optimized_markdown,
        notes=result.notes,
        elapsed_seconds=result.elapsed_seconds,
    )


def optimize_prompt_route(data: PromptData, db, current_user, optimizer) -> PromptOptimizeResponse:  # type: ignore[no-untyped-def]
    logger.info("optimize.request.start")
    result = optimizer(data.model_dump(), get_personal_config(db, current_user))
    logger.info("optimize.request.done engine={}", result.engine)
    return build_prompt_optimize_response(result)
