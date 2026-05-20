import datetime
import logging
import os
import sys
from typing import Any

from loguru import logger


def _console_log_format(record: dict[str, Any], show_console_source: bool) -> str:
    def _escape_markup(value: object) -> str:
        return str(value).replace("<", "\\<").replace(">", "\\>")

    message = _escape_markup(record["message"])
    source = f"{_escape_markup(record['name'])}:{_escape_markup(record['function'])}:{record['line']}"
    badge = "<white>APP     </white>"
    message_color = "<level>"

    if message.startswith("request.start"):
        badge = "<blue>HTTP IN </blue>"
        message_color = "<blue>"
    elif message.startswith("request.end"):
        badge = "<green>HTTP OUT</green>"
        message_color = "<green>"
    elif message.startswith("request.error") or message.startswith("request.exception"):
        badge = "<red>HTTP ERR</red>"
        message_color = "<red>"
    elif message.startswith("optimize.gradient"):
        badge = "<magenta>GP      </magenta>"
        message_color = "<magenta>"
    elif message.startswith("optimize.provider"):
        badge = "<yellow>LLM     </yellow>"
        message_color = "<yellow>"
    elif message.startswith("optimize.config"):
        badge = "<cyan>CFG     </cyan>"
        message_color = "<cyan>"
    elif message.startswith("logging.configured"):
        badge = "<green>BOOT    </green>"
        message_color = "<green>"

    source_part = f" <cyan>{source}</cyan> " if show_console_source else ""

    return (
        f"<dim>{record['time'].astimezone(datetime.UTC):YYYY-MM-DD HH:mm:ss.SSS} UTC</dim> "
        f"{badge} "
        f"<level>{record['level'].name:<8}</level> "
        f"{source_part}"
        f"{message_color}{message}</>\n{{exception}}"
    )


def configure_logging() -> None:
    console_log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper() or "INFO"
    show_console_source = os.getenv("SHOW_CONSOLE_SOURCE", "0").strip().lower() in {"1", "true", "yes", "on"}

    os.makedirs("logs", exist_ok=True)
    logger.remove()
    logger.add(
        sys.stderr,
        level=console_log_level,
        enqueue=True,
        backtrace=False,
        diagnose=False,
        colorize=True,
        format=lambda record: _console_log_format(record, show_console_source),
    )
    logger.add(
        "logs/app.log",
        level="DEBUG",
        rotation="4 MB",
        retention="10 days",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS!UTC} UTC | {level} | {name}:{function}:{line} | {message}",
    )

    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers.clear()
    uvicorn_access_logger.propagate = False
