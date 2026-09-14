"""``missionctl login`` / ``whoami`` (T2, FR-2/FR-18).

The CLI is a thin ``httpx`` client (FR-18) — these tests stand in for the
API with monkeypatched ``httpx.post``/``httpx.get`` calls rather than a live
server, and point the session cache at a temp file via
``MISSIONCTL_SESSION_FILE`` so runs never touch a developer's real
``~/.missionctl/session.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from cli.main import app

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
