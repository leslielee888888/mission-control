"""Matching engine: retrieval + ranking (T5, FR-13).

Representative cases per §10 #17 / the T5 acceptance checklist, not
exhaustive coverage: each hard-filter predicate exercised in isolation with
a minimal one-crew fixture (the point of Pipe and Filter -- see
``services/matcher.py``), ranking order hand-verified against a small
constructed scenario, the "no cap" behavior, and the zero-eligible case.
Pure scoring functions are tested directly with hand-picked numbers since
they take no session. One end-to-end test through the real API/route confirms
the wiring (auth, org scoping, JSON shape) without re-deriving every case at
that layer.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlmodel import Session

from models.assignment import Assignment
from models.availability_window import create_availability_window
from models.crew_profile import get_or_create_crew_profile
from models.crew_skill import upsert_crew_skill
from models.enums import AssignmentStatus, Role
from models.mission import Mission, create_mission
from models.organization import Organization
from models.requirement import Requirement, create_requirement
from models.skill import Skill, create_skill
from models.user import User
from services.auth import hash_password
from services.matcher import (
    has_no_conflicting_confirmed_assignment,
    has_skill_at_proficiency,
    is_available_for_window,
    is_eligible,
    match_mission,
    match_requirement,
    score_availability_margin,
    score_proficiency_surplus,
    score_workload,
)
from tests.conftest import SeededUser

# --- shared fixtures -----------------------------------------------------


def _make_org(session: Session, name: str = "Org") -> Organization:
    org = Organization(name=name)
    session.add(org)
    session.flush()
    assert org.id is not None
    return org


def _make_crew(session: Session, org_id: int, name: str) -> User:
    user = User(
        org_id=org_id,
        email=f"{name.lower().replace(' ', '.')}@example.com",
        password_hash=hash_password("irrelevant"),
        role=Role.CREW_MEMBER,
        name=name,
    )
    session.add(user)
    session.flush()
    assert user.id is not None
    get_or_create_crew_profile(session, user.id)
    return user


def _make_skill(session: Session, org_id: int, name: str) -> Skill:
    skill = create_skill(session, org_id=org_id, name=name, category=None)
    session.flush()
    assert skill.id is not None
    return skill


def _set_proficiency(session: Session, crew_id: int, skill_id: int, proficiency: int) -> None:
    upsert_crew_skill(session, crew_id=crew_id, skill_id=skill_id, proficiency=proficiency)


def _make_mission(
    session: Session, org_id: int, created_by: int, start: date, end: date, name: str = "Mission"
) -> Mission:
    mission = create_mission(
        session,
        org_id=org_id,
        created_by=created_by,
        name=name,
        description="d",
        start_date=start,
        end_date=end,
    )
    session.flush()
    assert mission.id is not None
    return mission


def _make_requirement(
    session: Session, mission_id: int, skill_id: int, min_proficiency: int = 3, headcount: int = 1
) -> Requirement:
    requirement = create_requirement(
        session,
        mission_id=mission_id,
        skill_id=skill_id,
        min_proficiency=min_proficiency,
        headcount=headcount,
    )
    session.flush()
    assert requirement.id is not None
    return requirement


def _add_unavailability(session: Session, crew_id: int, start: date, end: date) -> None:
    create_availability_window(session, crew_id=crew_id, start_date=start, end_date=end)


def _confirm_assignment(
    session: Session, requirement_id: int, crew_id: int, proposer_id: int
) -> None:
    assignment = Assignment(
        requirement_id=requirement_id,
        crew_id=crew_id,
        proposed_by=proposer_id,
        status=AssignmentStatus.CONFIRMED,
    )
    session.add(assignment)
    session.flush()


# --- retrieval: each hard filter, exercised independently ------------------


def test_has_skill_at_proficiency_false_when_crew_lacks_the_skill(session: Session) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "No Skill")
    skill = _make_skill(session, org.id, "Piloting")
    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id, min_proficiency=3)
    session.commit()

    assert has_skill_at_proficiency(session, crew, mission, requirement) is False


def test_has_skill_at_proficiency_false_when_below_minimum(session: Session) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "Low Prof")
    skill = _make_skill(session, org.id, "Docking")
    _set_proficiency(session, crew.id, skill.id, proficiency=2)
    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id, min_proficiency=3)
    session.commit()

    assert has_skill_at_proficiency(session, crew, mission, requirement) is False


def test_has_skill_at_proficiency_true_when_at_or_above_minimum(session: Session) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "Meets Prof")
    skill = _make_skill(session, org.id, "Navigation")
    _set_proficiency(session, crew.id, skill.id, proficiency=3)
    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id, min_proficiency=3)
    session.commit()

    assert has_skill_at_proficiency(session, crew, mission, requirement) is True


def test_is_available_for_window_false_when_unavailability_overlaps(session: Session) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "Unavailable")
    skill = _make_skill(session, org.id, "Comms")
    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id)
    _add_unavailability(session, crew.id, date(2026, 6, 5), date(2026, 6, 6))
    session.commit()

    assert is_available_for_window(session, crew, mission, requirement) is False


def test_is_available_for_window_true_when_no_overlap(session: Session) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "Available")
    skill = _make_skill(session, org.id, "EVA")
    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id)
    _add_unavailability(session, crew.id, date(2026, 7, 1), date(2026, 7, 10))
    session.commit()

    assert is_available_for_window(session, crew, mission, requirement) is True


def test_has_no_conflicting_confirmed_assignment_false_on_overlap(session: Session) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "Double Booked")
    skill = _make_skill(session, org.id, "Refueling")
    other_mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 15))
    other_requirement = _make_requirement(session, other_mission.id, skill.id)
    _confirm_assignment(session, other_requirement.id, crew.id, proposer_id=crew.id)

    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 10), date(2026, 6, 20))
    requirement = _make_requirement(session, mission.id, skill.id)
    session.commit()

    assert has_no_conflicting_confirmed_assignment(session, crew, mission, requirement) is False


def test_has_no_conflicting_confirmed_assignment_true_when_none_exist(session: Session) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "Clear")
    skill = _make_skill(session, org.id, "Structural Repair")
    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id)
    session.commit()

    assert has_no_conflicting_confirmed_assignment(session, crew, mission, requirement) is True


def test_has_no_conflicting_confirmed_assignment_true_when_non_overlapping(
    session: Session,
) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "Non Overlapping")
    skill = _make_skill(session, org.id, "Cargo Handling")
    other_mission = _make_mission(session, org.id, crew.id, date(2026, 1, 1), date(2026, 1, 10))
    other_requirement = _make_requirement(session, other_mission.id, skill.id)
    _confirm_assignment(session, other_requirement.id, crew.id, proposer_id=crew.id)

    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id)
    session.commit()

    assert has_no_conflicting_confirmed_assignment(session, crew, mission, requirement) is True


def test_is_eligible_true_only_when_every_filter_passes(session: Session) -> None:
    org = _make_org(session)
    crew = _make_crew(session, org.id, "Fully Eligible")
    skill = _make_skill(session, org.id, "Zero-G Welding")
    _set_proficiency(session, crew.id, skill.id, proficiency=4)
    mission = _make_mission(session, org.id, crew.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id, min_proficiency=3)
    session.commit()

    assert is_eligible(session, crew, mission, requirement) is True


# --- ranking: pure scoring functions ----------------------------------------


def test_score_proficiency_surplus_at_minimum_is_zero() -> None:
    assert score_proficiency_surplus(crew_proficiency=3, min_proficiency=3) == 0.0


def test_score_proficiency_surplus_at_max_surplus_is_one() -> None:
    assert score_proficiency_surplus(crew_proficiency=5, min_proficiency=1) == 1.0


def test_score_workload_zero_assignments_scores_highest() -> None:
    assert score_workload(0) == 1.0
    assert score_workload(1) == 0.5
    assert score_workload(3) == 0.25


def test_score_availability_margin_none_is_max_score() -> None:
    assert score_availability_margin(None) == 1.0


def test_score_availability_margin_zero_gap_is_zero() -> None:
    assert score_availability_margin(0) == 0.0


def test_score_availability_margin_scales_and_caps() -> None:
    assert score_availability_margin(15, cap_days=30) == 0.5
    assert score_availability_margin(60, cap_days=30) == 1.0  # clamped at the cap


# --- ranking order, hand-verified against a constructed scenario -----------


def test_ranking_order_is_hand_verifiable(session: Session) -> None:
    org = _make_org(session)
    skill = _make_skill(session, org.id, "Piloting")
    creator = _make_crew(session, org.id, "Creator")
    mission = _make_mission(session, org.id, creator.id, date(2026, 6, 1), date(2026, 6, 30))
    requirement = _make_requirement(session, mission.id, skill.id, min_proficiency=3)

    # Best: max proficiency surplus (5), no workload, no constraints at all.
    best = _make_crew(session, org.id, "Best Candidate")
    _set_proficiency(session, best.id, skill.id, proficiency=5)

    # Middle: exactly at the minimum, no workload, no constraints.
    middle = _make_crew(session, org.id, "Middle Candidate")
    _set_proficiency(session, middle.id, skill.id, proficiency=3)

    # Worst: exactly at the minimum too, but carries one confirmed
    # assignment elsewhere (lower workload score) and a tight (but
    # non-overlapping) unavailability window right after the mission ends
    # (lower availability-margin score).
    worst = _make_crew(session, org.id, "Worst Candidate")
    _set_proficiency(session, worst.id, skill.id, proficiency=3)
    other_mission = _make_mission(
        session, org.id, creator.id, date(2026, 1, 1), date(2026, 1, 5), name="Other"
    )
    other_requirement = _make_requirement(session, other_mission.id, skill.id)
    _confirm_assignment(session, other_requirement.id, worst.id, proposer_id=creator.id)
    _add_unavailability(session, worst.id, date(2026, 7, 1), date(2026, 7, 5))
    session.commit()

    candidates = match_requirement(session, org.id, mission, requirement)

    assert [c.crew.id for c in candidates] == [best.id, middle.id, worst.id]
    assert candidates[0].score > candidates[1].score > candidates[2].score
    # Hand-verified: best has surplus (5-3)/4=0.5, workload 1.0 (no
    # confirmed assignments), margin 1.0 (no constraints at all):
    # 0.5*0.5 + 0.3*1.0 + 0.2*1.0 = 0.75
    assert candidates[0].score == 0.75
    # middle: surplus 0.0 (exactly at minimum), workload 1.0, margin 1.0
    # -> 0.5*0.0 + 0.3*1.0 + 0.2*1.0 = 0.5
    assert candidates[1].score == 0.5
    # worst: surplus 0.0, workload 1/(1+1)=0.5 (one confirmed assignment),
    # margin: nearest constraint is the unavailability window starting the
    # day right after the mission ends -> gap 0 days -> margin 0.0
    # -> 0.5*0.0 + 0.3*0.5 + 0.2*0.0 = 0.15
    assert round(candidates[2].score, 4) == 0.15


# --- no top-N cap ------------------------------------------------------------


def test_returns_every_eligible_candidate_no_cap(session: Session) -> None:
    org = _make_org(session)
    skill = _make_skill(session, org.id, "Life Support")
    creator = _make_crew(session, org.id, "Creator2")
    mission = _make_mission(session, org.id, creator.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id, min_proficiency=1)

    eligible_ids = []
    for i in range(7):
        crew = _make_crew(session, org.id, f"Bulk Candidate {i}")
        _set_proficiency(session, crew.id, skill.id, proficiency=3)
        eligible_ids.append(crew.id)
    session.commit()

    candidates = match_requirement(session, org.id, mission, requirement)

    assert len(candidates) == 7
    assert {c.crew.id for c in candidates} == set(eligible_ids)


# --- zero eligible candidates -----------------------------------------------


def test_zero_eligible_candidates_returns_empty_list(session: Session) -> None:
    org = _make_org(session)
    skill = _make_skill(session, org.id, "Airlock Cert")
    creator = _make_crew(session, org.id, "Creator3")
    mission = _make_mission(session, org.id, creator.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill.id, min_proficiency=3)
    # A crew member exists in the org but nobody holds the skill at all.
    _make_crew(session, org.id, "Unskilled")
    session.commit()

    candidates = match_requirement(session, org.id, mission, requirement)

    assert candidates == []


# --- org scoping -------------------------------------------------------------


def test_crew_in_a_different_org_is_never_a_candidate(session: Session) -> None:
    org_a = _make_org(session, "Org A")
    org_b = _make_org(session, "Org B")
    skill_a = _make_skill(session, org_a.id, "Piloting II")
    creator = _make_crew(session, org_a.id, "Creator4")
    mission = _make_mission(session, org_a.id, creator.id, date(2026, 6, 1), date(2026, 6, 10))
    requirement = _make_requirement(session, mission.id, skill_a.id, min_proficiency=1)

    # Same skill *name*, but a different skill row in a different org -- and
    # a crew member who belongs to org_b, not org_a.
    skill_b = _make_skill(session, org_b.id, "Piloting II")
    outsider = _make_crew(session, org_b.id, "Outsider")
    _set_proficiency(session, outsider.id, skill_b.id, proficiency=5)
    session.commit()

    candidates = match_requirement(session, org_a.id, mission, requirement)

    assert candidates == []


# --- match_mission: every requirement on a mission --------------------------


def test_match_mission_covers_every_requirement(session: Session) -> None:
    org = _make_org(session)
    skill_a = _make_skill(session, org.id, "Skill A")
    skill_b = _make_skill(session, org.id, "Skill B")
    creator = _make_crew(session, org.id, "Creator5")
    mission = _make_mission(session, org.id, creator.id, date(2026, 6, 1), date(2026, 6, 10))
    _make_requirement(session, mission.id, skill_a.id)
    _make_requirement(session, mission.id, skill_b.id)
    session.commit()

    results = match_mission(session, org.id, mission.id)

    assert len(results) == 2
    assert {r.requirement.skill_id for r in results} == {skill_a.id, skill_b.id}


# --- end-to-end through the real API/route ----------------------------------


def _login(client: TestClient, user: SeededUser) -> str:
    response = client.post("/auth/login", json={"email": user.email, "password": user.password})
    assert response.status_code == 200
    token: str = response.json()["token"]
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_match_endpoint_returns_ranked_candidates_with_breakdown(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    director_token = _login(client, director)

    skill = client.post(
        "/skills", json={"name": "Orbital Mechanics"}, headers=_auth(director_token)
    ).json()
    client.put(
        f"/crew/{crew.id}/skills",
        json={"skill_name": "Orbital Mechanics", "proficiency": 4},
        headers=_auth(_login(client, crew)),
    )

    lead_token = _login(client, lead)
    mission = client.post(
        "/missions",
        json={
            "name": "Match Test Mission",
            "description": "d",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
        },
        headers=_auth(lead_token),
    ).json()
    requirement = client.post(
        f"/missions/{mission['id']}/requirements",
        json={"skill_id": skill["id"], "min_proficiency": 3, "headcount": 1},
        headers=_auth(lead_token),
    ).json()

    response = client.get(f"/missions/{mission['id']}/match", headers=_auth(lead_token))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["requirement_id"] == requirement["id"]
    assert len(body[0]["candidates"]) == 1
    candidate = body[0]["candidates"][0]
    assert candidate["crew_id"] == crew.id
    # surplus (4-3)/4=0.25, workload 1.0 (no confirmed assignments), margin
    # 1.0 (no constraints) -> 0.5*0.25 + 0.3*1.0 + 0.2*1.0 = 0.625
    assert candidate["score"] == 0.625
    assert "proficiency_surplus" in candidate["breakdown"]
    assert "workload" in candidate["breakdown"]
    assert "availability_margin" in candidate["breakdown"]


def test_match_endpoint_single_requirement_filter(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    lead = seed_users["lead_a"]
    director_token = _login(client, director)
    lead_token = _login(client, lead)

    skill_a = client.post(
        "/skills", json={"name": "Skill A2"}, headers=_auth(director_token)
    ).json()
    skill_b = client.post(
        "/skills", json={"name": "Skill B2"}, headers=_auth(director_token)
    ).json()
    mission = client.post(
        "/missions",
        json={
            "name": "Two Requirement Mission",
            "description": "d",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
        },
        headers=_auth(lead_token),
    ).json()
    req_a = client.post(
        f"/missions/{mission['id']}/requirements",
        json={"skill_id": skill_a["id"], "min_proficiency": 1, "headcount": 1},
        headers=_auth(lead_token),
    ).json()
    client.post(
        f"/missions/{mission['id']}/requirements",
        json={"skill_id": skill_b["id"], "min_proficiency": 1, "headcount": 1},
        headers=_auth(lead_token),
    )

    response = client.get(
        f"/missions/{mission['id']}/match",
        params={"requirement_id": req_a["id"]},
        headers=_auth(lead_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["requirement_id"] == req_a["id"]


def test_match_endpoint_mission_not_found_is_404(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]

    response = client.get("/missions/999999/match", headers=_auth(_login(client, lead)))

    assert response.status_code == 404


def test_match_endpoint_forbidden_for_crew_member(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    mission = client.post(
        "/missions",
        json={
            "name": "RBAC Test Mission",
            "description": "d",
            "start_date": "2026-08-01",
            "end_date": "2026-08-10",
        },
        headers=_auth(_login(client, lead)),
    ).json()

    response = client.get(f"/missions/{mission['id']}/match", headers=_auth(_login(client, crew)))

    assert response.status_code == 403
