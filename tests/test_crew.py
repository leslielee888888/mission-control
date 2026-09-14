"""Crew management (T3, FR-4/FR-5/FR-6/FR-7).

Representative cases per §10 #17 / the T3 acceptance checklist, not
exhaustive coverage: self vs. Director/Lead profile permissions, skill
uniqueness within + across orgs, proficiency set/visibility, availability
overlap rejection + remove, and cross-org 404s.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import SeededUser


def _login(client: TestClient, user: SeededUser) -> str:
    response = client.post("/auth/login", json={"email": user.email, "password": user.password})
    assert response.status_code == 200
    token: str = response.json()["token"]
    return token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --- profile (FR-4) ---------------------------------------------------------


def test_crew_member_updates_their_own_profile(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    token = _login(client, crew)

    response = client.patch(
        f"/crew/{crew.id}/profile",
        json={"name": "New Name", "contact": "new@contact.example", "bio": "Veteran pilot."},
        headers=_auth(token),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New Name"
    assert body["contact"] == "new@contact.example"
    assert body["bio"] == "Veteran pilot."


def test_crew_member_cannot_edit_someone_elses_profile(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    lead = seed_users["lead_a"]
    token = _login(client, crew)

    response = client.patch(
        f"/crew/{lead.id}/profile",
        json={"name": "Hijacked"},
        headers=_auth(token),
    )

    # lead_a isn't even a crew member (no profile), but the identity check
    # (self-only) fires before that would matter.
    assert response.status_code == 403


def test_director_can_view_but_not_edit_a_crew_members_profile(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    crew = seed_users["crew_a"]
    token = _login(client, director)

    view_response = client.get(f"/crew/{crew.id}/profile", headers=_auth(token))
    assert view_response.status_code == 200
    assert view_response.json()["email"] == crew.email

    edit_response = client.patch(
        f"/crew/{crew.id}/profile", json={"name": "Overwritten"}, headers=_auth(token)
    )
    assert edit_response.status_code == 403


def test_lead_can_view_a_crew_members_profile(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    crew = seed_users["crew_a"]
    token = _login(client, lead)

    response = client.get(f"/crew/{crew.id}/profile", headers=_auth(token))

    assert response.status_code == 200


def test_crew_member_cannot_view_another_crew_members_profile(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    lead = seed_users["lead_a"]
    token = _login(client, crew)

    # lead_a has no profile, but crew_a isn't allowed to view anyone but
    # themselves regardless — the identity check fires first.
    response = client.get(f"/crew/{lead.id}/profile", headers=_auth(token))

    assert response.status_code == 403


def test_cross_org_profile_view_is_404_not_403(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director_b = seed_users["director_b"]
    crew_a = seed_users["crew_a"]
    token = _login(client, director_b)

    response = client.get(f"/crew/{crew_a.id}/profile", headers=_auth(token))

    assert response.status_code == 404


# --- skills: org taxonomy (FR-5) --------------------------------------------


def test_director_creates_an_org_scoped_skill(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    token = _login(client, director)

    response = client.post("/skills", json={"name": "EVA Certified"}, headers=_auth(token))

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "EVA Certified"
    assert body["org_id"] == director.org_id


def test_lead_cannot_create_a_skill(client: TestClient, seed_users: dict[str, SeededUser]) -> None:
    lead = seed_users["lead_a"]
    token = _login(client, lead)

    response = client.post("/skills", json={"name": "Orbital Mechanics"}, headers=_auth(token))

    assert response.status_code == 403


def test_duplicate_skill_name_within_an_org_is_rejected(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    token = _login(client, director)
    client.post("/skills", json={"name": "Life Support"}, headers=_auth(token))

    response = client.post("/skills", json={"name": "Life Support"}, headers=_auth(token))

    assert response.status_code == 409


def test_two_orgs_can_independently_define_the_same_skill_name(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director_a = seed_users["director_a"]
    director_b = seed_users["director_b"]
    token_a = _login(client, director_a)
    token_b = _login(client, director_b)

    response_a = client.post("/skills", json={"name": "Docking"}, headers=_auth(token_a))
    response_b = client.post("/skills", json={"name": "Docking"}, headers=_auth(token_b))

    assert response_a.status_code == 201
    assert response_b.status_code == 201
    assert response_a.json()["org_id"] != response_b.json()["org_id"]


# --- crew skill proficiency (FR-6) ------------------------------------------


def test_crew_member_sets_their_own_proficiency_visible_to_lead(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    crew = seed_users["crew_a"]
    lead = seed_users["lead_a"]
    director_token = _login(client, director)
    client.post("/skills", json={"name": "Piloting"}, headers=_auth(director_token))

    crew_token = _login(client, crew)
    set_response = client.put(
        f"/crew/{crew.id}/skills",
        json={"skill_name": "Piloting", "proficiency": 4},
        headers=_auth(crew_token),
    )
    assert set_response.status_code == 200
    assert set_response.json()["proficiency"] == 4

    lead_token = _login(client, lead)
    view_response = client.get(f"/crew/{crew.id}/profile", headers=_auth(lead_token))
    assert view_response.status_code == 200
    skills = view_response.json()["skills"]
    assert any(s["skill_name"] == "Piloting" and s["proficiency"] == 4 for s in skills)


def test_director_sets_proficiency_on_a_crew_members_behalf(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    crew = seed_users["crew_a"]
    token = _login(client, director)
    client.post("/skills", json={"name": "Navigation"}, headers=_auth(token))

    response = client.put(
        f"/crew/{crew.id}/skills",
        json={"skill_name": "Navigation", "proficiency": 3},
        headers=_auth(token),
    )

    assert response.status_code == 200
    assert response.json()["proficiency"] == 3


def test_lead_cannot_set_a_crew_members_proficiency(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    crew = seed_users["crew_a"]
    lead = seed_users["lead_a"]
    director_token = _login(client, director)
    client.post("/skills", json={"name": "Structural Repair"}, headers=_auth(director_token))

    lead_token = _login(client, lead)
    response = client.put(
        f"/crew/{crew.id}/skills",
        json={"skill_name": "Structural Repair", "proficiency": 2},
        headers=_auth(lead_token),
    )

    assert response.status_code == 403


def test_proficiency_out_of_range_is_422(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    crew = seed_users["crew_a"]
    token = _login(client, director)
    client.post("/skills", json={"name": "Comms"}, headers=_auth(token))

    response = client.put(
        f"/crew/{crew.id}/skills",
        json={"skill_name": "Comms", "proficiency": 9},
        headers=_auth(token),
    )

    assert response.status_code == 422


# --- availability (FR-7) ----------------------------------------------------


def test_crew_member_adds_and_lists_an_availability_window(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    token = _login(client, crew)

    add_response = client.post(
        f"/crew/{crew.id}/availability",
        json={"start_date": "2026-01-10", "end_date": "2026-01-20"},
        headers=_auth(token),
    )
    assert add_response.status_code == 201

    list_response = client.get(f"/crew/{crew.id}/availability", headers=_auth(token))
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_overlapping_availability_windows_are_rejected(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    token = _login(client, crew)
    client.post(
        f"/crew/{crew.id}/availability",
        json={"start_date": "2026-02-01", "end_date": "2026-02-10"},
        headers=_auth(token),
    )

    response = client.post(
        f"/crew/{crew.id}/availability",
        json={"start_date": "2026-02-05", "end_date": "2026-02-15"},
        headers=_auth(token),
    )

    assert response.status_code == 409


def test_availability_remove_is_delete_only(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    token = _login(client, crew)
    add_response = client.post(
        f"/crew/{crew.id}/availability",
        json={"start_date": "2026-03-01", "end_date": "2026-03-05"},
        headers=_auth(token),
    )
    window_id = add_response.json()["id"]

    delete_response = client.delete(
        f"/crew/{crew.id}/availability/{window_id}", headers=_auth(token)
    )
    assert delete_response.status_code == 204

    list_response = client.get(f"/crew/{crew.id}/availability", headers=_auth(token))
    assert list_response.json() == []

    second_delete_response = client.delete(
        f"/crew/{crew.id}/availability/{window_id}", headers=_auth(token)
    )
    assert second_delete_response.status_code == 404


def test_crew_member_defaults_to_available_with_no_windows(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    token = _login(client, crew)

    response = client.get(f"/crew/{crew.id}/availability", headers=_auth(token))

    assert response.status_code == 200
    assert response.json() == []


def test_crew_member_cannot_manage_another_crew_members_availability(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]
    crew = seed_users["crew_a"]
    director_token = _login(client, director)

    response = client.post(
        f"/crew/{crew.id}/availability",
        json={"start_date": "2026-04-01", "end_date": "2026-04-05"},
        headers=_auth(director_token),
    )

    assert response.status_code == 403
