"""Engine + session wiring for the synchronous SQLAlchemy/SQLModel layer.

Deliberately synchronous throughout (§8 coding constraint) — plain
``sqlite3`` via SQLAlchemy's sync engine, no ``aiosqlite``.
"""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

DEFAULT_DATABASE_URL = "sqlite:///./mission_control.db"


def get_database_url() -> str:
    """The SQLAlchemy database URL, overridable via env var (tests use this
    to point at a real temporary SQLite file instead of the dev DB)."""
    return os.environ.get("MISSION_CONTROL_DATABASE_URL", DEFAULT_DATABASE_URL)


def make_engine(database_url: str | None = None) -> Engine:
    """Build a new engine for ``database_url`` (or the default/env URL).

    ``check_same_thread=False`` is required for SQLite when the engine is
    shared across FastAPI's threadpool-executed request handlers; it is safe
    here because each request gets its own ``Session``.
    """
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, echo=False)


engine: Engine = make_engine()


def create_db_and_tables(bound_engine: Engine | None = None) -> None:
    """Create every table registered on ``SQLModel.metadata`` (idempotent)."""
    SQLModel.metadata.create_all(bound_engine or engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding one synchronous session per request."""
    with Session(engine) as session:
        yield session
