import os
import tomllib
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI
from loguru import logger
from sqlalchemy.orm import Session


def resolve_app_version() -> str:
    pyproject_path = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject_path.exists():
        try:
            with pyproject_path.open("rb") as fp:
                pyproject = tomllib.load(fp)
            version = pyproject.get("project", {}).get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
        except Exception:
            pass

    return "0.0.0"


def redact_database_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    _, host_part = rest.split("@", 1)
    return f"{scheme}://***@{host_part}"


def run_startup_bootstrap(
    database_url: str,
    init_database_fn: Callable[[], None],
    startup_session_factory: Callable[[], Session],
    bootstrap_fn: Callable[[Session], None],
    close_session_fn: Callable[[Session], None],
) -> None:
    startup_started = perf_counter()
    logger.info("startup.begin")

    migrate_started = perf_counter()
    init_database_fn()
    logger.info("startup.migrations.done duration_ms={:.2f}", (perf_counter() - migrate_started) * 1000)

    bootstrap_started = perf_counter()
    db = startup_session_factory()
    try:
        bootstrap_fn(db)
    finally:
        close_session_fn(db)

    logger.info("startup.bootstrap.done duration_ms={:.2f}", (perf_counter() - bootstrap_started) * 1000)
    logger.info("startup.ready total_duration_ms={:.2f}", (perf_counter() - startup_started) * 1000)
    logger.info(
        "startup.health status=ready pid={} db_url={}",
        os.getpid(),
        redact_database_url(database_url),
    )


def create_lifespan(startup_action: Callable[[], None]) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        startup_action()
        try:
            yield
        finally:
            logger.info("shutdown.begin pid={}", os.getpid())

    return lifespan
