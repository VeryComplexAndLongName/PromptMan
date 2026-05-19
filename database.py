import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Concatenate, ParamSpec, TypeVar

from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from alembic import command

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./prompts.db")

is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")

P = ParamSpec("P")
T = TypeVar("T")
DatabaseSession = Session

sync_engine_kwargs: dict[str, Any] = {
    "pool_pre_ping": True,
}

if is_sqlite:
    sync_engine_kwargs.update(
        {
            "connect_args": {
                "check_same_thread": False,
                "timeout": 30,
            },
        }
    )
else:
    sync_engine_kwargs.update(
        {
            "pool_size": 20,
            "max_overflow": 40,
            "pool_timeout": 30,
            "pool_recycle": 1800,
        }
    )

startup_engine = create_engine(SQLALCHEMY_DATABASE_URL, **sync_engine_kwargs)
engine = startup_engine
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

StartupSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=startup_engine)


if is_sqlite:
    @event.listens_for(startup_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()


class Base(DeclarativeBase):
    pass


def close_db_session(db: DatabaseSession) -> None:
    db.close()


def run_db_call(db: DatabaseSession, operation: Callable[Concatenate[DatabaseSession, P], T], /, *args: P.args, **kwargs: P.kwargs) -> T:
    return operation(db, *args, **kwargs)


def _run_alembic_upgrade() -> None:
    project_root = Path(__file__).resolve().parent
    alembic_ini_path = project_root / "alembic.ini"
    if not alembic_ini_path.exists():
        return

    alembic_config = Config(str(alembic_ini_path))
    alembic_config.set_main_option("script_location", str(project_root / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)
    command.upgrade(alembic_config, "head")


def init_database(bind=None) -> None:  # type: ignore[no-untyped-def]
    if bind is not None:
        Base.metadata.create_all(bind=bind)
        return

    _run_alembic_upgrade()
    Base.metadata.create_all(bind=startup_engine)
