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
    """The SQLAlchemy database URL, overridable via env var. Tests do not use
    this — they build an isolated temporary-file engine directly via
    ``make_engine()`` (see ``tests/conftest.py``) so a developer's
    ``MISSION_CONTROL_DATABASE_URL`` can never leak into the test suite."""
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


def session_dependency_for(bound_engine: Engine) -> Generator[Session, None, None]:
    """Yield one synchronous ``Session`` bound to ``bound_engine``.

    Shared by ``get_session`` (bound to the module-level dev/prod engine) and
    ``tests/conftest.py`` (bound to a temporary test engine), so session
    semantics — commit/rollback handling, ``expire_on_commit`` — live in
    exactly one place instead of being hand-duplicated per call site.
    """
    with Session(bound_engine) as session:
        yield session


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding one synchronous session per request."""
    yield from session_dependency_for(engine)
