"""Shared pytest fixtures.

Per §8 coding constraint: tests run against a real temporary SQLite database,
never a mocked DB layer, so what the suite proves (tenant isolation, the
state machine, the matcher's scoring) actually holds against real SQL, not
just against a mock's expectations.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

import models  # noqa: F401  (imported for its side effect: registers all entities)
from models.database import create_db_and_tables, get_session, make_engine, session_dependency_for


@pytest.fixture(scope="session")
def engine() -> Generator[Engine, None, None]:
    """A real, temporary, file-based SQLite engine — one per test session."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "test_mission_control.db"
        test_engine = make_engine(f"sqlite:///{db_path}")
        create_db_and_tables(test_engine)
        yield test_engine
        test_engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Generator[Session, None, None]:
    """A session bound to the temporary test engine, one per test function."""
    with Session(engine) as db_session:
        yield db_session


@pytest.fixture
def client(engine: Engine) -> Generator[TestClient, None, None]:
    """A FastAPI ``TestClient`` whose DB dependency is overridden to use the
    temporary test engine instead of the app's default dev-database engine."""
    from main import app

    def get_test_session() -> Generator[Session, None, None]:
        yield from session_dependency_for(engine)

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
