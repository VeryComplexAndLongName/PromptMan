import datetime
import logging
import os
import sys
from typing import Any

from loguru import logger

from app_core.telemetry import telemetry


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
    show_console_source = os.getenv("SHOW_CONSOLE_SOURCE", "").strip().lower() in {"1", "true", "yes", "on"}
    file_rotation = os.getenv("LOG_FILE_ROTATION", "").strip()

    # Windows often keeps file handles locked across dev reload/helper processes,
    # so rotating a shared app.log can fail with WinError 32 during rename.
    if not file_rotation:
        file_rotation = "" if os.name == "nt" else "4 MB"

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
    file_sink: dict[str, Any] = {
        "sink": "logs/app.log",
        "level": "DEBUG",
        "enqueue": True,
        "backtrace": True,
        "diagnose": False,
        "format": "{time:YYYY-MM-DD HH:mm:ss.SSS!UTC} UTC | {level} | {name}:{function}:{line} | {message}",
    }
    if file_rotation:
        file_sink["rotation"] = file_rotation
        file_sink["retention"] = os.getenv("LOG_FILE_RETENTION", "10 days").strip() or "10 days"

    logger.add(**file_sink)

    def _telemetry_sink(message: Any) -> None:
        record = message.record
        telemetry.emit_log(level_name=record["level"].name, message=record["message"])

    logger.add(_telemetry_sink, level="INFO", enqueue=True, backtrace=False, diagnose=False)

    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    uvicorn_access_logger.handlers.clear()
    uvicorn_access_logger.propagate = False
