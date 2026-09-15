"""Mission lifecycle + approval gate (T4, FR-8/FR-9/FR-10/FR-11/FR-12/FR-17).

Representative cases per §10 #17 / the T4 acceptance checklist, not
exhaustive coverage -- except FR-11's self-approval gate (the crux of this
task) and FR-9's invalid-transition set, which the checklist explicitly
calls out for real coverage: ``test_invalid_mission_transition_is_409``
below is parametrized over every (status, action) pair FR-9's table
disallows, generated from the spec rather than imported from
``services.mission`` so a bug in that table can't hide the drift from its
own test.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from models.enums import MissionStatus
from models.mission import Mission
from tests.conftest import SeededUser


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
    assert response.status_code == 201
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
    payload = {"skill_id": skill_id, "min_proficiency": 3, "headcount": 2, **overrides}
    response = client.post(
        f"/missions/{mission_id}/requirements", json=payload, headers=_auth(token)
    )
    return response


# --- creation + requirements (FR-8) -----------------------------------------


def test_lead_creates_a_mission_in_draft(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]

    mission = _create_mission(client, lead)

    assert mission["status"] == "draft"
    assert mission["created_by"] == lead.id
    assert mission["org_id"] == lead.org_id


def test_director_creates_a_mission(client: TestClient, seed_users: dict[str, SeededUser]) -> None:
    director = seed_users["director_a"]

    mission = _create_mission(client, director)

    assert mission["status"] == "draft"


def test_crew_member_cannot_create_a_mission(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    token = _login(client, crew)

    response = client.post(
        "/missions",
        json={
            "name": "X",
            "description": "d",
            "start_date": "2026-01-01",
            "end_date": "2026-01-02",
        },
        headers=_auth(token),
    )

    assert response.status_code == 403


def test_add_multiple_requirements_across_different_skills(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    piloting = _create_skill(client, director, "Piloting")
    docking = _create_skill(client, director, "Docking")
    mission = _create_mission(client, lead)

    response_a = _add_requirement(client, lead, mission["id"], piloting, headcount=2)
    response_b = _add_requirement(client, lead, mission["id"], docking, headcount=1)

    assert response_a.status_code == 201
    assert response_b.status_code == 201
    detail = client.get(f"/missions/{mission['id']}", headers=_auth(_login(client, lead))).json()
    assert len(detail["requirements"]) == 2


def test_requirement_shows_confirmed_vs_needed_headcount(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Navigation")
    mission = _create_mission(client, lead)
    _add_requirement(client, lead, mission["id"], skill_id, headcount=3)

    response = client.get(f"/missions/{mission['id']}", headers=_auth(_login(client, lead)))

    assert response.status_code == 200
    requirement = response.json()["requirements"][0]
    assert requirement["headcount"] == 3
    assert requirement["confirmed"] == 0  # no assignments exist until T6


def test_requirements_are_frozen_once_a_mission_leaves_draft(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Comms")
    mission = _create_mission(client, lead)
    _add_requirement(client, lead, mission["id"], skill_id)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(_login(client, lead)))

    response = _add_requirement(client, lead, mission["id"], skill_id)

    assert response.status_code == 409


def test_add_requirement_with_unknown_skill_is_404(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    mission = _create_mission(client, lead)

    response = _add_requirement(client, lead, mission["id"], 999_999)

    assert response.status_code == 404


# --- full happy path ---------------------------------------------------


def test_full_happy_path_create_to_complete(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Structural Repair")
    mission = _create_mission(client, lead)
    mission_id = mission["id"]
    assert _add_requirement(client, lead, mission_id, skill_id).status_code == 201

    lead_token = _login(client, lead)
    submit = client.post(f"/missions/{mission_id}/submit", headers=_auth(lead_token))
    assert submit.status_code == 200
    assert submit.json()["status"] == "pending_approval"

    director_token = _login(client, director)
    approve = client.post(f"/missions/{mission_id}/approve", headers=_auth(director_token))
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    activate = client.post(f"/missions/{mission_id}/activate", headers=_auth(lead_token))
    assert activate.status_code == 200
    assert activate.json()["status"] == "active"

    complete = client.post(f"/missions/{mission_id}/complete", headers=_auth(lead_token))
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"


# --- submit (FR-10) ------------------------------------------------------


def test_submit_with_zero_requirements_is_rejected(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    mission = _create_mission(client, lead)

    response = client.post(f"/missions/{mission['id']}/submit", headers=_auth(_login(client, lead)))

    assert response.status_code == 409
    assert "requirement" in response.json()["detail"].lower()


def test_only_the_creator_can_submit(client: TestClient, seed_users: dict[str, SeededUser]) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "EVA")
    mission = _create_mission(client, lead)
    _add_requirement(client, lead, mission["id"], skill_id)

    # director_a didn't create this mission, even though Director is a role
    # that's otherwise allowed to submit missions it *does* own.
    response = client.post(
        f"/missions/{mission['id']}/submit", headers=_auth(_login(client, director))
    )

    assert response.status_code == 403


# --- approval gate (FR-11) — the crux of this task --------------------------


def test_creator_cannot_approve_their_own_mission(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    skill_id = _create_skill(client, director, "Life Support")
    mission = _create_mission(client, director)
    _add_requirement(client, director, mission["id"], skill_id)
    token = _login(client, director)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(token))

    response = client.post(f"/missions/{mission['id']}/approve", headers=_auth(token))

    assert response.status_code == 403
    mission_after = client.get(f"/missions/{mission['id']}", headers=_auth(token)).json()
    assert mission_after["status"] == "pending_approval"


def test_non_creator_director_approves_successfully(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Docking Ops")
    mission = _create_mission(client, lead)
    _add_requirement(client, lead, mission["id"], skill_id)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(_login(client, lead)))

    response = client.post(
        f"/missions/{mission['id']}/approve", headers=_auth(_login(client, director))
    )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"


def test_mission_lead_cannot_approve_even_as_non_creator(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    """Approval is Director-only (FR-11), not just "not the creator" —
    a non-creator Mission Lead still isn't allowed."""
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Piloting II")
    mission = _create_mission(client, director)
    _add_requirement(client, director, mission["id"], skill_id)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(_login(client, director)))

    response = client.post(
        f"/missions/{mission['id']}/approve", headers=_auth(_login(client, lead))
    )

    assert response.status_code == 403


def test_reject_requires_a_reason(client: TestClient, seed_users: dict[str, SeededUser]) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Refueling")
    mission = _create_mission(client, lead)
    _add_requirement(client, lead, mission["id"], skill_id)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(_login(client, lead)))

    response = client.post(
        f"/missions/{mission['id']}/reject",
        json={},
        headers=_auth(_login(client, director)),
    )

    assert response.status_code == 422


def test_reject_by_non_creator_director_returns_mission_to_draft(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Cargo Handling")
    mission = _create_mission(client, lead)
    _add_requirement(client, lead, mission["id"], skill_id)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(_login(client, lead)))

    response = client.post(
        f"/missions/{mission['id']}/reject",
        json={"reason": "Dates conflict with another mission."},
        headers=_auth(_login(client, director)),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "draft"


def test_creator_cannot_reject_their_own_mission(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    skill_id = _create_skill(client, director, "Airlock Cert")
    mission = _create_mission(client, director)
    _add_requirement(client, director, mission["id"], skill_id)
    token = _login(client, director)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(token))

    response = client.post(
        f"/missions/{mission['id']}/reject",
        json={"reason": "Trying to reject my own mission."},
        headers=_auth(token),
    )

    assert response.status_code == 403


# --- activate / complete (FR-12) ----------------------------------------


def test_mission_lead_activates_and_completes(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Orbital Mechanics")
    mission = _create_mission(client, lead)
    _add_requirement(client, lead, mission["id"], skill_id)
    lead_token = _login(client, lead)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(lead_token))
    client.post(f"/missions/{mission['id']}/approve", headers=_auth(_login(client, director)))

    activate = client.post(f"/missions/{mission['id']}/activate", headers=_auth(lead_token))
    assert activate.status_code == 200
    assert activate.json()["status"] == "active"

    complete = client.post(f"/missions/{mission['id']}/complete", headers=_auth(lead_token))
    assert complete.status_code == 200
    assert complete.json()["status"] == "completed"


def test_crew_member_cannot_activate_a_mission(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    # The role gate (`require_role(DIRECTOR, MISSION_LEAD)`) rejects a crew
    # member before the executor ever runs, so the mission's actual status
    # doesn't matter here -- draft is enough to prove the check fires.
    director = seed_users["director_a"]
    crew = seed_users["crew_a"]
    mission = _create_mission(client, director)

    response = client.post(
        f"/missions/{mission['id']}/activate", headers=_auth(_login(client, crew))
    )

    assert response.status_code == 403


# --- under-staffing never blocks activation (FR-17) -------------------------


def test_activation_is_not_blocked_by_understaffing(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    skill_id = _create_skill(client, director, "Zero-G Welding")
    mission = _create_mission(client, lead)
    _add_requirement(
        client, lead, mission["id"], skill_id, headcount=5
    )  # 0 confirmed, never blocks
    lead_token = _login(client, lead)
    client.post(f"/missions/{mission['id']}/submit", headers=_auth(lead_token))
    client.post(f"/missions/{mission['id']}/approve", headers=_auth(_login(client, director)))

    response = client.post(f"/missions/{mission['id']}/activate", headers=_auth(lead_token))

    assert response.status_code == 200
    assert response.json()["status"] == "active"


# --- cancel, from every pre-completed state -----------------------------


@pytest.mark.parametrize("status", ["draft", "pending_approval", "approved", "active"])
def test_cancel_from_each_pre_completed_state(
    client: TestClient,
    session: Session,
    seed_users: dict[str, SeededUser],
    status: str,
) -> None:
    director = seed_users["director_a"]
    mission = Mission(
        org_id=director.org_id,
        created_by=director.id,  # type: ignore[arg-type]
        name="Cancel target",
        description="d",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        status=MissionStatus(status),
    )
    session.add(mission)
    session.commit()
    session.refresh(mission)
    token = _login(client, director)

    response = client.post(f"/missions/{mission.id}/cancel", headers=_auth(token))

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cannot_cancel_a_completed_mission(
    client: TestClient, session: Session, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    mission = Mission(
        org_id=director.org_id,
        created_by=director.id,  # type: ignore[arg-type]
        name="Done",
        description="d",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
        status=MissionStatus.COMPLETED,
    )
    session.add(mission)
    session.commit()
    session.refresh(mission)
    token = _login(client, director)

    response = client.post(f"/missions/{mission.id}/cancel", headers=_auth(token))

    assert response.status_code == 409
    session.refresh(mission)
    assert mission.status == MissionStatus.COMPLETED


# --- every invalid transition -> 409, status unchanged (FR-9) --------------

#: The action -> valid source statuses map, taken straight from FR-9's own
#: Given/When/Then rather than from `services.mission.ALLOWED_TRANSITIONS`,
#: so a bug in that table would actually fail this test instead of agreeing
#: with itself.
_VALID_FROM_STATUSES: dict[str, set[MissionStatus]] = {
    "submit": {MissionStatus.DRAFT},
    "approve": {MissionStatus.PENDING_APPROVAL},
    "reject": {MissionStatus.PENDING_APPROVAL},
    "activate": {MissionStatus.APPROVED},
    "complete": {MissionStatus.ACTIVE},
    "cancel": {
        MissionStatus.DRAFT,
        MissionStatus.PENDING_APPROVAL,
        MissionStatus.APPROVED,
        MissionStatus.ACTIVE,
    },
}

_INVALID_TRANSITION_CASES: list[tuple[MissionStatus, str]] = [
    (mission_status, action)
    for action, valid_from in _VALID_FROM_STATUSES.items()
    for mission_status in MissionStatus
    if mission_status not in valid_from
]


@pytest.mark.parametrize(
    "current_status,action",
    _INVALID_TRANSITION_CASES,
    ids=[f"{s.value}--{a}" for s, a in _INVALID_TRANSITION_CASES],
)
def test_invalid_mission_transition_is_409(
    client: TestClient,
    session: Session,
    seed_users: dict[str, SeededUser],
    current_status: MissionStatus,
    action: str,
) -> None:
    director = seed_users["director_a"]
    mission = Mission(
        org_id=director.org_id,
        created_by=director.id,  # type: ignore[arg-type]
        name="Invalid transition target",
        description="d",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 10),
        status=current_status,
    )
    session.add(mission)
    session.commit()
    session.refresh(mission)
    token = _login(client, director)
    # director_a passes every action's role gate (Director is allowed
    # everywhere); reject additionally needs a well-formed body so a missing
    # `reason` (422) can't masquerade as this test's expected 409.
    body = {"reason": "because"} if action == "reject" else None

    response = client.post(f"/missions/{mission.id}/{action}", json=body, headers=_auth(token))

    assert response.status_code == 409, response.text
    session.refresh(mission)
    assert mission.status == current_status


# --- tenant scoping (FR-1) -----------------------------------------------


def test_cross_org_mission_access_is_404_not_403(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    director_b = seed_users["director_b"]
    mission = _create_mission(client, lead)

    response = client.get(f"/missions/{mission['id']}", headers=_auth(_login(client, director_b)))

    assert response.status_code == 404


def test_cross_org_mission_action_is_404(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    director_b = seed_users["director_b"]
    mission = _create_mission(client, lead)

    response = client.post(
        f"/missions/{mission['id']}/submit", headers=_auth(_login(client, director_b))
    )

    assert response.status_code == 404
