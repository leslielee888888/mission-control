"""Assignments: propose, respond, double-booking guard (T6, FR-14/FR-15/
FR-16).

Representative cases per §10 #17 / the T6 acceptance checklist — except the
double-booking guard (FR-16), which the checklist explicitly calls out for
real coverage since it's the whole point of this task: it must fire for an
assignment that was proposed manually (``test_double_booking_guard_fires_
on_manually_proposed_assignment`` below never calls the matcher at all, only
``assign propose``), not just one a matcher run happened to originate.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from models.crew_profile import get_or_create_crew_profile
from models.enums import Role
from models.user import User
from services.auth import hash_password
from tests.conftest import SeededUser

# --- shared helpers (mirrors tests/test_mission.py's / tests/test_matcher.py's) ---


def _login(client: TestClient, user: SeededUser) -> str:
    response = client.post("/auth/login", json={"email": user.email, "password": user.password})
    assert response.status_code == 200
    token: str = response.json()["token"]
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_skill(client: TestClient, director: SeededUser, name: str) -> int:
    token = _login(client, director)
    response = client.post("/skills", json={"name": name}, headers=_auth(token))
    assert response.status_code == 201, response.text
    skill_id: int = response.json()["id"]
    return skill_id


def _create_mission(
    client: TestClient,
    creator: SeededUser,
    *,
    name: str = "Rescue Op",
    start: str = "2026-05-01",
    end: str = "2026-05-10",
) -> dict:
    token = _login(client, creator)
    response = client.post(
        "/missions",
        json={"name": name, "description": "A mission", "start_date": start, "end_date": end},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    result: dict = response.json()
    return result


def _add_requirement(
    client: TestClient, actor: SeededUser, mission_id: int, skill_id: int, **overrides: int
) -> dict:
    token = _login(client, actor)
    payload = {"skill_id": skill_id, "min_proficiency": 1, "headcount": 1, **overrides}
    response = client.post(
        f"/missions/{mission_id}/requirements", json=payload, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    result: dict = response.json()
    return result


def _propose(
    client: TestClient, proposer: SeededUser, mission_id: int, requirement_id: int, crew_id: int
):
    token = _login(client, proposer)
    return client.post(
        "/assignments",
        json={"mission_id": mission_id, "requirement_id": requirement_id, "crew_id": crew_id},
        headers=_auth(token),
    )


def _respond(client: TestClient, actor: SeededUser, assignment_id: int, action: str):
    token = _login(client, actor)
    return client.post(
        f"/assignments/{assignment_id}/respond",
        json={"action": action},
        headers=_auth(token),
    )


def _make_crew(session: Session, org_id: int, name: str) -> SeededUser:
    """A second crew member beyond ``seed_users``'s ``crew_a`` — needed for
    headcount/double-booking scenarios that involve more than one."""
    password = "correct-horse-extra"
    suffix = uuid.uuid4().hex[:8]
    user = User(
        org_id=org_id,
        email=f"{name.lower().replace(' ', '.')}.{suffix}@example.com",
        password_hash=hash_password(password),
        role=Role.CREW_MEMBER,
        name=name,
    )
    session.add(user)
    session.flush()
    assert user.id is not None
    get_or_create_crew_profile(session, user.id)
    session.commit()
    return SeededUser(
        id=user.id, org_id=org_id, email=user.email, password=password, role=Role.CREW_MEMBER
    )


# --- propose (FR-14) ---------------------------------------------------


def test_propose_creates_assignment_in_proposed_status(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    skill_id = _create_skill(client, director, "Piloting")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id, headcount=2)

    response = _propose(client, lead, mission["id"], requirement["id"], crew.id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "proposed"
    assert body["crew_id"] == crew.id
    assert body["requirement_id"] == requirement["id"]
    assert body["mission_id"] == mission["id"]


def test_propose_beyond_headcount_is_rejected(
    client: TestClient, session: Session, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew_a = seed_users["crew_a"]
    crew_b = _make_crew(session, director.org_id, "Second Crew")
    skill_id = _create_skill(client, director, "Docking")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id, headcount=1)
    first = _propose(client, lead, mission["id"], requirement["id"], crew_a.id)
    assert first.status_code == 201, first.text

    second = _propose(client, lead, mission["id"], requirement["id"], crew_b.id)

    assert second.status_code == 409
    assert "headcount" in second.json()["detail"].lower()


def test_crew_member_cannot_propose_an_assignment(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    skill_id = _create_skill(client, director, "Comms")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id)

    response = _propose(client, crew, mission["id"], requirement["id"], crew.id)

    assert response.status_code == 403


# --- respond: accept / decline (FR-15) ----------------------------------


def test_accept_confirms_the_assignment(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    skill_id = _create_skill(client, director, "Navigation")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id)
    assignment = _propose(client, lead, mission["id"], requirement["id"], crew.id).json()

    response = _respond(client, crew, assignment["id"], "accept")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"


def test_decline_declines_and_a_subsequent_propose_refills_the_slot(
    client: TestClient, session: Session, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew_a = seed_users["crew_a"]
    crew_b = _make_crew(session, director.org_id, "Refill Crew")
    skill_id = _create_skill(client, director, "Refueling")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id, headcount=1)
    assignment = _propose(client, lead, mission["id"], requirement["id"], crew_a.id).json()

    decline = _respond(client, crew_a, assignment["id"], "decline")
    assert decline.status_code == 200, decline.text
    assert decline.json()["status"] == "declined"

    # headcount is recalculated by reading, not stored -- the declined
    # assignment no longer counts, so this now-open slot can be refilled.
    refill = _propose(client, lead, mission["id"], requirement["id"], crew_b.id)
    assert refill.status_code == 201, refill.text


def test_only_the_named_crew_member_can_respond(
    client: TestClient, session: Session, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew_a = seed_users["crew_a"]
    crew_b = _make_crew(session, director.org_id, "Not The One")
    skill_id = _create_skill(client, director, "Cargo Handling")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id)
    assignment = _propose(client, lead, mission["id"], requirement["id"], crew_a.id).json()

    other_crew_response = _respond(client, crew_b, assignment["id"], "accept")
    lead_response = _respond(client, lead, assignment["id"], "accept")
    director_response = _respond(client, director, assignment["id"], "accept")

    assert other_crew_response.status_code == 403
    assert lead_response.status_code == 403
    assert director_response.status_code == 403


def test_responding_twice_is_rejected(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    skill_id = _create_skill(client, director, "Structural Repair")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id)
    assignment = _propose(client, lead, mission["id"], requirement["id"], crew.id).json()
    assert _respond(client, crew, assignment["id"], "decline").status_code == 200

    response = _respond(client, crew, assignment["id"], "accept")

    assert response.status_code == 409


# --- double-booking guard (FR-16) — the crux of this task -------------------


def test_double_booking_guard_fires_on_manually_proposed_assignment(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    """The guard must fire even though this assignment was created with a
    plain ``assign propose`` call — no matcher run happened anywhere in this
    test — since assignments can be proposed manually, entirely bypassing
    the matcher's own filtering (FR-16)."""
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    skill_id = _create_skill(client, director, "Zero-G Welding")

    first_mission = _create_mission(
        client, lead, name="First Mission", start="2026-06-01", end="2026-06-15"
    )
    first_requirement = _add_requirement(client, lead, first_mission["id"], skill_id)
    first_assignment = _propose(
        client, lead, first_mission["id"], first_requirement["id"], crew.id
    ).json()
    confirm = _respond(client, crew, first_assignment["id"], "accept")
    assert confirm.status_code == 200, confirm.text

    # Overlaps the first mission's [06-01, 06-15] window.
    second_mission = _create_mission(
        client, lead, name="Second Mission", start="2026-06-10", end="2026-06-20"
    )
    second_requirement = _add_requirement(client, lead, second_mission["id"], skill_id)
    second_assignment = _propose(
        client, lead, second_mission["id"], second_requirement["id"], crew.id
    ).json()
    assert second_assignment["status"] == "proposed"  # propose itself doesn't guard

    response = _respond(client, crew, second_assignment["id"], "accept")

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert str(first_mission["id"]) in detail
    assert "First Mission" in detail
    # The rejected accept must not have changed the assignment's status.
    listing = client.get("/assignments", headers=_auth(_login(client, lead))).json()
    still_proposed = next(a for a in listing if a["id"] == second_assignment["id"])
    assert still_proposed["status"] == "proposed"


def test_no_double_booking_guard_when_dates_do_not_overlap(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    skill_id = _create_skill(client, director, "Airlock Cert")

    first_mission = _create_mission(
        client, lead, name="January Mission", start="2026-01-01", end="2026-01-10"
    )
    first_requirement = _add_requirement(client, lead, first_mission["id"], skill_id)
    first_assignment = _propose(
        client, lead, first_mission["id"], first_requirement["id"], crew.id
    ).json()
    assert _respond(client, crew, first_assignment["id"], "accept").status_code == 200

    second_mission = _create_mission(
        client, lead, name="July Mission", start="2026-07-01", end="2026-07-10"
    )
    second_requirement = _add_requirement(client, lead, second_mission["id"], skill_id)
    second_assignment = _propose(
        client, lead, second_mission["id"], second_requirement["id"], crew.id
    ).json()

    response = _respond(client, crew, second_assignment["id"], "accept")

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "confirmed"


# --- tenant scoping (FR-1) -----------------------------------------------


def test_propose_against_a_cross_org_mission_is_404(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    director_b = seed_users["director_b"]
    skill_id = _create_skill(client, seed_users["director_a"], "Orbital Mechanics")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id)

    response = _propose(client, director_b, mission["id"], requirement["id"], crew.id)

    assert response.status_code == 404


def test_respond_to_a_cross_org_assignment_is_404(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    director_b = seed_users["director_b"]
    skill_id = _create_skill(client, director, "Life Support")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id)
    assignment = _propose(client, lead, mission["id"], requirement["id"], crew.id).json()

    response = _respond(client, director_b, assignment["id"], "accept")

    assert response.status_code == 404


# --- assignment list, scoped by role -------------------------------------


def test_assignment_list_scoped_to_role(
    client: TestClient, session: Session, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew_a = seed_users["crew_a"]
    crew_b = _make_crew(session, director.org_id, "Listing Crew")
    skill_id = _create_skill(client, director, "EVA")
    mission = _create_mission(client, lead)
    requirement = _add_requirement(client, lead, mission["id"], skill_id, headcount=2)
    _propose(client, lead, mission["id"], requirement["id"], crew_a.id)
    _propose(client, lead, mission["id"], requirement["id"], crew_b.id)

    crew_a_listing = client.get("/assignments", headers=_auth(_login(client, crew_a))).json()
    org_listing = client.get("/assignments", headers=_auth(_login(client, lead))).json()

    assert {a["crew_id"] for a in crew_a_listing} == {crew_a.id}
    assert {a["crew_id"] for a in org_listing} == {crew_a.id, crew_b.id}
