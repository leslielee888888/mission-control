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


# --- shared plumbing for every command below this point (T3+) --------------


def _require_session() -> dict[str, Any]:
    session_data = _load_session()
    if session_data is None:
        _print_json({"error": "Not logged in. Run `missionctl login <email> <password>`."})
        raise typer.Exit(code=1)
    return session_data


def _auth_headers(session_data: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {session_data['token']}"}


def _handle_response(response: httpx.Response) -> Any:
    """Print+exit on any error status; otherwise return the parsed body (or
    ``None`` for a body-less response, e.g. a 204)."""
    if response.status_code >= httpx.codes.BAD_REQUEST:
        _print_json({"error": _error_detail(response)})
        raise typer.Exit(code=1)
    return response.json() if response.content else None


# --- profile (FR-4) ---------------------------------------------------------

profile_app = typer.Typer(help="Crew profile self-service (FR-4).")
app.add_typer(profile_app, name="profile")


@profile_app.command("show")
def profile_show(
    user_id: int | None = typer.Argument(
        None, help="Crew member id to view (defaults to yourself)."
    ),
) -> None:
    """View a crew profile: your own, or (Director/Lead) another crew
    member's in your org, read-only."""
    session_data = _require_session()
    target = user_id if user_id is not None else session_data["user"]["id"]
    response = httpx.get(
        f"{_api_base_url()}/crew/{target}/profile",
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@profile_app.command("update")
def profile_update(
    name: str | None = typer.Option(None, help="New display name."),
    contact: str | None = typer.Option(None, help="New contact info."),
    bio: str | None = typer.Option(None, help="New bio."),
) -> None:
    """Update your own name/contact/bio (PATCH-style: only given fields
    change)."""
    session_data = _require_session()
    user_id = session_data["user"]["id"]
    payload = {
        key: value
        for key, value in {"name": name, "contact": contact, "bio": bio}.items()
        if value is not None
    }
    response = httpx.patch(
        f"{_api_base_url()}/crew/{user_id}/profile",
        json=payload,
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


# --- skills: org taxonomy (FR-5) + crew proficiency (FR-6) -----------------

skills_app = typer.Typer(help="Org skill taxonomy and crew skill proficiency (FR-5/FR-6).")
app.add_typer(skills_app, name="skills")


@skills_app.command("add")
def skills_add(
    name: str,
    category: str | None = typer.Option(None, help="Optional free-text category tag."),
) -> None:
    """Create an org-scoped skill (Director only)."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/skills",
        json={"name": name, "category": category},
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@skills_app.command("list")
def skills_list() -> None:
    """List your org's skill taxonomy."""
    session_data = _require_session()
    response = httpx.get(f"{_api_base_url()}/skills", headers=_auth_headers(session_data))
    _print_json(_handle_response(response))


@skills_app.command("set")
def skills_set(
    skill: str,
    proficiency: int,
    user_id: int | None = typer.Option(
        None, "--user", help="Crew member id to set on behalf of (Director only)."
    ),
) -> None:
    """Set your own (or, as Director, another crew member's) proficiency
    (1-5) on an org skill."""
    session_data = _require_session()
    target = user_id if user_id is not None else session_data["user"]["id"]
    response = httpx.put(
        f"{_api_base_url()}/crew/{target}/skills",
        json={"skill_name": skill, "proficiency": proficiency},
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


# --- availability (FR-7) ----------------------------------------------------

availability_app = typer.Typer(help="Crew availability windows (FR-7).")
app.add_typer(availability_app, name="availability")


@availability_app.command("add")
def availability_add(start: str, end: str) -> None:
    """Add an unavailability window (self only), as YYYY-MM-DD dates."""
    session_data = _require_session()
    user_id = session_data["user"]["id"]
    response = httpx.post(
        f"{_api_base_url()}/crew/{user_id}/availability",
        json={"start_date": start, "end_date": end},
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@availability_app.command("remove")
def availability_remove(window_id: int) -> None:
    """Delete an unavailability window (delete-only, no edit)."""
    session_data = _require_session()
    user_id = session_data["user"]["id"]
    response = httpx.delete(
        f"{_api_base_url()}/crew/{user_id}/availability/{window_id}",
        headers=_auth_headers(session_data),
    )
    _handle_response(response)
    _print_json({"status": "removed", "id": window_id})


@availability_app.command("list")
def availability_list() -> None:
    """List your own unavailability windows."""
    session_data = _require_session()
    user_id = session_data["user"]["id"]
    response = httpx.get(
        f"{_api_base_url()}/crew/{user_id}/availability",
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


# --- missions: lifecycle + approval gate (FR-8/FR-9/FR-10/FR-11/FR-12) -----

mission_app = typer.Typer(
    help="Mission CRUD, requirements, and the 6-state lifecycle (FR-8..FR-12)."
)
app.add_typer(mission_app, name="mission")


@mission_app.command("create")
def mission_create(name: str, description: str, start: str, end: str) -> None:
    """Create a mission (Mission Lead or Director); starts in `draft`, as
    YYYY-MM-DD dates."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/missions",
        json={"name": name, "description": description, "start_date": start, "end_date": end},
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("add-requirement")
def mission_add_requirement(
    mission_id: int, skill_id: int, min_proficiency: int, headcount: int
) -> None:
    """Attach a requirement (skill, minimum proficiency, headcount) to a
    `draft` mission."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/missions/{mission_id}/requirements",
        json={"skill_id": skill_id, "min_proficiency": min_proficiency, "headcount": headcount},
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("submit")
def mission_submit(mission_id: int) -> None:
    """Submit a `draft` mission for approval (creator only)."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/missions/{mission_id}/submit",
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("approve")
def mission_approve(mission_id: int) -> None:
    """Approve a `pending_approval` mission (Director, not its creator)."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/missions/{mission_id}/approve",
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("reject")
def mission_reject(
    mission_id: int,
    reason: str = typer.Option(..., "--reason", help="Why the mission is being rejected."),
) -> None:
    """Reject a `pending_approval` mission back to `draft` (Director, not
    its creator); requires a reason."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/missions/{mission_id}/reject",
        json={"reason": reason},
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("activate")
def mission_activate(mission_id: int) -> None:
    """Activate an `approved` mission (Mission Lead or Director)."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/missions/{mission_id}/activate",
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("complete")
def mission_complete(mission_id: int) -> None:
    """Complete an `active` mission (Mission Lead or Director)."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/missions/{mission_id}/complete",
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("cancel")
def mission_cancel(mission_id: int) -> None:
    """Cancel a mission from any pre-completed state (Mission Lead or
    Director)."""
    session_data = _require_session()
    response = httpx.post(
        f"{_api_base_url()}/missions/{mission_id}/cancel",
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("show")
def mission_show(mission_id: int) -> None:
    """Show a mission's status, requirements, and fulfillment (FR-17)."""
    session_data = _require_session()
    response = httpx.get(
        f"{_api_base_url()}/missions/{mission_id}",
        headers=_auth_headers(session_data),
    )
    _print_json(_handle_response(response))


@mission_app.command("list")
def mission_list() -> None:
    """List missions in your org."""
    session_data = _require_session()
    response = httpx.get(f"{_api_base_url()}/missions", headers=_auth_headers(session_data))
    _print_json(_handle_response(response))


if __name__ == "__main__":
    app()
