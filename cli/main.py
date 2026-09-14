"""``missionctl`` — a thin HTTP client over the Mission Control API.

Talks to the API over ``httpx`` only; never touches the database or the
``services``/``models`` layers directly (FR-18). Output is JSON,
pretty-printed (§10 #15).

The session (bearer token + basic profile) issued by ``login`` is cached
locally at ``~/.missionctl/session.json`` (override via
``MISSIONCTL_SESSION_FILE``, mainly for tests) so later commands don't need
the token pasted in every time. The file is written best-effort
owner-only (``chmod 600``) since it holds a live bearer token.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

import httpx
import typer

app = typer.Typer(
    name="missionctl",
    help="A thin HTTP client over the Mission Control API.",
)

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


def _api_base_url() -> str:
    return os.environ.get("MISSIONCTL_API_BASE_URL", DEFAULT_API_BASE_URL)


def _session_file() -> Path:
    override = os.environ.get("MISSIONCTL_SESSION_FILE")
    if override:
        return Path(override)
    return Path.home() / ".missionctl" / "session.json"


def _save_session(token: str, user: dict[str, Any]) -> None:
    path = _session_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"token": token, "user": user}, indent=2))
    # Best-effort only — e.g. unsupported on some Windows filesystems.
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def _load_session() -> dict[str, Any] | None:
    path = _session_file()
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _print_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2))


def _error_detail(response: httpx.Response) -> Any:
    if not response.content:
        return response.reason_phrase
    try:
        return response.json().get("detail", response.text)
    except ValueError:
        return response.text


@app.command()
def version() -> None:
    """Print the CLI version."""
    typer.echo("missionctl 0.1.0")


@app.command()
def login(email: str, password: str) -> None:
    """Log in and cache the issued bearer token locally."""
    response = httpx.post(
        f"{_api_base_url()}/auth/login",
        json={"email": email, "password": password},
    )
    if response.status_code != httpx.codes.OK:
        _print_json({"error": _error_detail(response)})
        raise typer.Exit(code=1)

    data = response.json()
    _save_session(data["token"], data["user"])
    _print_json({"status": "logged in", "user": data["user"]})


@app.command()
def whoami() -> None:
    """Show the currently logged-in user, verified against the API."""
    session_data = _load_session()
    if session_data is None:
        _print_json({"error": "Not logged in. Run `missionctl login <email> <password>`."})
        raise typer.Exit(code=1)

    response = httpx.get(
        f"{_api_base_url()}/auth/whoami",
        headers={"Authorization": f"Bearer {session_data['token']}"},
    )
    if response.status_code != httpx.codes.OK:
        _print_json({"error": "Session invalid or expired. Run `missionctl login` again."})
        raise typer.Exit(code=1)

    _print_json(response.json())


if __name__ == "__main__":
    app()
