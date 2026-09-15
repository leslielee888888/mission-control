"""Trivial smoke tests proving the app starts and the temp-DB fixture works.

Not a substitute for the real per-feature suites T2+ will add — just
evidence, per §8, that the fixture stands up a real database and the app can
reach it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import Engine, text


def test_engine_connects(engine: Engine) -> None:
    """The temporary SQLite engine is reachable and can run a real query."""
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()
    assert result == 1


def test_all_ten_tables_created(engine: Engine) -> None:
    """All 10 tables from the data model exist in the temporary database."""
    expected = {
        "organizations",
        "users",
        "crew_profiles",
        "skills",
        "crew_skills",
        "availability_windows",
        "missions",
        "requirements",
        "assignments",
        "auth_tokens",
    }
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        actual = {row[0] for row in rows}
    assert expected <= actual


def test_health_check(client: TestClient) -> None:
    """The app starts and the health endpoint proves the DB engine connects."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
