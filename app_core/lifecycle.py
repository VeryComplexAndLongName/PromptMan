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


def run_shutdown_bootstrap(shutdown_action: Callable[[], None] | None = None) -> None:
    shutdown_started = perf_counter()
    logger.info("shutdown.begin pid={}", os.getpid())
    if shutdown_action is not None:
        shutdown_action()
    logger.info("shutdown.done duration_ms={:.2f}", (perf_counter() - shutdown_started) * 1000)


def create_startup_action(
    database_url: str,
    init_database_fn: Callable[[], None],
    startup_session_factory: Callable[[], Session],
    bootstrap_fn: Callable[[Session], None],
    close_session_fn: Callable[[Session], None],
) -> Callable[[], None]:
    def startup_action() -> None:
        run_startup_bootstrap(
            database_url,
            init_database_fn,
            startup_session_factory,
            bootstrap_fn,
            close_session_fn,
        )

    return startup_action


def chain_actions(*actions: Callable[[], None] | None) -> Callable[[], None]:
    def chained_action() -> None:
        for action in actions:
            if action is not None:
                action()

    return chained_action


def create_app_lifespan(
    startup_action: Callable[[], None],
    shutdown_action: Callable[[], None] | None = None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        startup_action()
        plugin_engine = getattr(app.state, "plugin_engine", None)
        if plugin_engine is not None:
            try:
                await plugin_engine.startup()
            except Exception as exc:
                logger.exception("plugins.startup.error error={}", exc)
        try:
            yield
        finally:
            if plugin_engine is not None:
                try:
                    await plugin_engine.shutdown()
                except Exception as exc:
                    logger.exception("plugins.shutdown.error error={}", exc)
            run_shutdown_bootstrap(shutdown_action)

    return lifespan
