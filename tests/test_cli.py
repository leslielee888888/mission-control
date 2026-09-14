"""``missionctl login`` / ``whoami`` (T2, FR-2/FR-18).

The CLI is a thin ``httpx`` client (FR-18) — these tests stand in for the
API with monkeypatched ``httpx.post``/``httpx.get`` calls rather than a live
server, and point the session cache at a temp file via
``MISSIONCTL_SESSION_FILE`` so runs never touch a developer's real
``~/.missionctl/session.json``.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine
from sqlmodel import Session
from typer.testing import CliRunner

from cli.main import app
from tests.conftest import SeededUser

runner = CliRunner()


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"1"
        self.reason_phrase = "error"
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture(autouse=True)
def _session_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "session.json"
    monkeypatch.setenv("MISSIONCTL_SESSION_FILE", str(path))
    return path


def test_login_success_stores_the_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_response = _FakeResponse(
        200,
        {
            "token": "abc123",
            "user": {"id": 1, "org_id": 1, "email": "a@x.com", "name": "a", "role": "director"},
        },
    )
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: fake_response)

    result = runner.invoke(app, ["login", "a@x.com", "secret"])

    assert result.exit_code == 0
    session_path = Path(tmp_path / "session.json")
    stored = json.loads(session_path.read_text())
    assert stored["token"] == "abc123"
    assert stored["user"]["email"] == "a@x.com"


def test_login_failure_does_not_store_a_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_response = _FakeResponse(401, {"detail": "Email or password is incorrect"})
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: fake_response)

    result = runner.invoke(app, ["login", "a@x.com", "wrong"])

    assert result.exit_code != 0
    assert not (tmp_path / "session.json").exists()


def test_whoami_without_a_stored_session_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ["whoami"])

    assert result.exit_code != 0
    assert "not logged in" in result.output.lower()


def test_whoami_with_a_stored_session_calls_the_api(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps({"token": "abc123", "user": {"email": "a@x.com"}}))

    fake_response = _FakeResponse(
        200, {"id": 1, "org_id": 1, "email": "a@x.com", "name": "a", "role": "director"}
    )
    seen_headers: dict[str, str] = {}

    def fake_get(url: str, headers: dict[str, str]) -> _FakeResponse:
        seen_headers.update(headers)
        return fake_response

    monkeypatch.setattr(httpx, "get", fake_get)

    result = runner.invoke(app, ["whoami"])

    assert result.exit_code == 0
    assert seen_headers["Authorization"] == "Bearer abc123"
    assert "a@x.com" in result.output


def test_version_prints_json() -> None:
    """§10 #15: JSON output everywhere, not just the workflow commands."""
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert json.loads(result.output) == {"version": "0.1.0"}


def test_cli_module_never_imports_models_or_services_directly() -> None:
    """FR-18's actual point, checked statically: the CLI is a genuine HTTP
    client of the API, never a shortcut straight into the domain/data
    layers. If a future command imports ``models``/``services`` to "save a
    round trip," this fails the build instead of quietly drifting."""
    source = (Path(__file__).parent.parent / "cli" / "main.py").read_text(encoding="utf-8")
    forbidden = ("import models", "from models", "import services", "from services")
    hits = [needle for needle in forbidden if needle in source]
    assert not hits, f"cli/main.py must talk to the API over HTTP only (FR-18); found: {hits}"


# --- CLI-as-real-HTTP-client integration tests (T7, FR-18) ------------------
#
# Everything above monkeypatches individual httpx calls to stand in for the
# API. These tests instead point the CLI's *real* httpx.get/post/patch/put/
# delete calls at the real FastAPI app (the same one T2-T6's own test suites
# exercise) through an in-process ASGI transport -- genuine HTTP request/
# response framing (headers, JSON bodies, status codes, FastAPI routing and
# RBAC dependencies all run for real), just without opening an actual TCP
# socket. This is what actually proves FR-18 end to end for a given command,
# rather than trusting that the mocked-response tests above match the real
# API's shape.


@pytest.fixture
def live_cli(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[None, None, None]:
    from fastapi.testclient import TestClient

    from main import app as fastapi_app
    from models.database import get_session, session_dependency_for

    def get_test_session() -> Generator[Session, None, None]:
        yield from session_dependency_for(engine)

    fastapi_app.dependency_overrides[get_session] = get_test_session
    # `TestClient` (Starlette's) is used as the real ASGI bridge here rather
    # than a bare `httpx.ASGITransport` -- that transport only implements
    # the *async* transport interface, and the CLI's httpx calls are
    # synchronous (§8 coding constraint applies to the CLI too).
    test_client = TestClient(fastapi_app, base_url="http://testserver")

    def _bridge(method: str) -> Any:
        def call(url: str, **kwargs: Any) -> httpx.Response:
            # The CLI always builds URLs off `_api_base_url()`; swap that
            # prefix for the in-process transport's base, keeping the real
            # path/query the CLI constructed.
            path = url.removeprefix("http://127.0.0.1:8000")
            return getattr(test_client, method)(path, **kwargs)

        return call

    monkeypatch.setattr(httpx, "get", _bridge("get"))
    monkeypatch.setattr(httpx, "post", _bridge("post"))
    monkeypatch.setattr(httpx, "patch", _bridge("patch"))
    monkeypatch.setattr(httpx, "put", _bridge("put"))
    monkeypatch.setattr(httpx, "delete", _bridge("delete"))
    monkeypatch.setenv("MISSIONCTL_SESSION_FILE", str(tmp_path / "session.json"))

    yield

    test_client.close()
    fastapi_app.dependency_overrides.clear()


def _cli_login(user: SeededUser) -> None:
    result = runner.invoke(app, ["login", user.email, user.password])
    assert result.exit_code == 0, result.output


def test_crew_list_via_cli_returns_the_org_roster(
    live_cli: None, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    crew = seed_users["crew_a"]
    _cli_login(director)

    result = runner.invoke(app, ["crew", "list"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert any(entry["email"] == crew.email for entry in payload)


def test_crew_list_via_cli_allows_mission_lead_too(
    live_cli: None, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    _cli_login(lead)

    result = runner.invoke(app, ["crew", "list"])

    assert result.exit_code == 0


def test_crew_list_via_cli_forbidden_for_a_crew_member(
    live_cli: None, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    _cli_login(crew)

    result = runner.invoke(app, ["crew", "list"])

    assert result.exit_code != 0
    assert "director" in result.output.lower()
    assert "traceback" not in result.output.lower()


def test_crew_list_via_cli_excludes_other_orgs_crew(
    live_cli: None, seed_users: dict[str, SeededUser]
) -> None:
    director_b = seed_users["director_b"]
    crew_a = seed_users["crew_a"]
    _cli_login(director_b)

    result = runner.invoke(app, ["crew", "list"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert all(entry["email"] != crew_a.email for entry in payload)


def test_mission_list_via_cli_round_trips_through_the_real_api(
    live_cli: None, seed_users: dict[str, SeededUser]
) -> None:
    """A second spot check beyond `crew list`: any CLI command, run against
    the real API, gets real JSON back -- not a shortcut around HTTP."""
    lead = seed_users["lead_a"]
    _cli_login(lead)

    create_result = runner.invoke(
        app,
        [
            "mission",
            "create",
            "Resupply Run",
            "Ferry parts to the station",
            "2026-05-01",
            "2026-05-10",
        ],
    )
    assert create_result.exit_code == 0, create_result.output
    created = json.loads(create_result.output)

    list_result = runner.invoke(app, ["mission", "list"])

    assert list_result.exit_code == 0
    missions = json.loads(list_result.output)
    assert any(mission["id"] == created["id"] for mission in missions)
