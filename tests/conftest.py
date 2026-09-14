"""Shared pytest fixtures.

Per §8 coding constraint: tests run against a real temporary SQLite database,
never a mocked DB layer, so what the suite proves (tenant isolation, the
state machine, the matcher's scoring) actually holds against real SQL, not
just against a mock's expectations.
"""

from __future__ import annotations

import tempfile
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

import models  # noqa: F401  (imported for its side effect: registers all entities)
from models.database import create_db_and_tables, get_session, make_engine, session_dependency_for
from models.enums import Role
from models.organization import Organization
from models.user import User
from services.auth import hash_password


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


@dataclass(frozen=True)
class SeededUser:
    """A created user plus the plaintext password used to create it (never
    otherwise available once ``User.password_hash`` is set)."""

    id: int
    org_id: int
    email: str
    password: str
    role: Role


@pytest.fixture
def seed_users(session: Session) -> dict[str, SeededUser]:
    """Two orgs, one user per role (plus a second org's Director), with
    known plaintext passwords — shared by every test that needs a real
    logged-in caller instead of duplicating org/user creation.

    ``engine`` is session-scoped (one real SQLite file for the whole test
    run, per the module docstring), so rows from every call to this fixture
    persist side by side — emails get a fresh random suffix each call so
    two tests' seed data never collides on the ``users.email`` unique
    constraint.
    """
    suffix = uuid.uuid4().hex[:8]
    org_a = Organization(name=f"Org A {suffix}")
    org_b = Organization(name=f"Org B {suffix}")
    session.add(org_a)
    session.add(org_b)
    session.flush()
    assert org_a.id is not None
    assert org_b.id is not None

    def make(org_id: int, role: Role, email: str, password: str) -> SeededUser:
        user = User(
            org_id=org_id,
            email=email,
            password_hash=hash_password(password),
            role=role,
            name=email.split("@")[0],
        )
        session.add(user)
        session.flush()
        assert user.id is not None
        return SeededUser(id=user.id, org_id=org_id, email=email, password=password, role=role)

    users = {
        "director_a": make(
            org_a.id, Role.DIRECTOR, f"director.a.{suffix}@example.com", "correct-horse-a"
        ),
        "lead_a": make(
            org_a.id, Role.MISSION_LEAD, f"lead.a.{suffix}@example.com", "correct-horse-b"
        ),
        "crew_a": make(
            org_a.id, Role.CREW_MEMBER, f"crew.a.{suffix}@example.com", "correct-horse-c"
        ),
        "director_b": make(
            org_b.id, Role.DIRECTOR, f"director.b.{suffix}@example.com", "correct-horse-d"
        ),
    }
    session.commit()
    return users
