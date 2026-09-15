"""Auth + RBAC + tenant scoping (T2, FR-1/FR-2/FR-3).

Representative cases per §10 #17 / the T2 acceptance checklist, not
exhaustive coverage: login success/failure, missing/invalid token on a
protected route, role-mismatch 403, and cross-org 404.
"""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models.auth_token import AuthToken
from tests.conftest import SeededUser


def test_login_success_issues_a_bearer_token(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]

    response = client.post(
        "/auth/login", json={"email": director.email, "password": director.password}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == director.email
    assert body["user"]["role"] == "director"
    assert body["user"]["org_id"] == director.org_id
    assert isinstance(body["token"], str) and len(body["token"]) > 20


def test_login_stores_only_the_hashed_token(
    client: TestClient, session: Session, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]

    response = client.post(
        "/auth/login", json={"email": director.email, "password": director.password}
    )
    raw_token = response.json()["token"]

    expected_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    stored = session.exec(select(AuthToken)).all()
    assert any(row.token_hash == expected_hash for row in stored)
    # The raw token itself never appears as a stored hash.
    assert all(row.token_hash != raw_token for row in stored)


def test_login_wrong_password_is_401_with_generic_message(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director = seed_users["director_a"]

    response = client.post(
        "/auth/login", json={"email": director.email, "password": "not-the-password"}
    )

    assert response.status_code == 401
    detail = response.json()["detail"].lower()
    assert "email or password is incorrect" in detail
    # Never reveals which one was wrong.
    assert "password" not in detail.replace("email or password is incorrect", "")


def test_login_unknown_email_is_401_with_same_generic_message(client: TestClient) -> None:
    response = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )

    assert response.status_code == 401
    assert response.json()["detail"].lower() == "email or password is incorrect"


def test_protected_route_without_a_token_is_401(client: TestClient) -> None:
    response = client.get("/auth/whoami")

    assert response.status_code == 401


def test_protected_route_with_an_invalid_token_is_401(client: TestClient) -> None:
    response = client.get("/auth/whoami", headers={"Authorization": "Bearer not-a-real-token"})

    assert response.status_code == 401


def test_whoami_with_a_valid_token_returns_the_caller(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    crew = seed_users["crew_a"]
    login_response = client.post(
        "/auth/login", json={"email": crew.email, "password": crew.password}
    )
    token = login_response.json()["token"]

    response = client.get("/auth/whoami", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["email"] == crew.email


def test_disallowed_role_gets_403_naming_the_required_role(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    lead = seed_users["lead_a"]
    login_response = client.post(
        "/auth/login", json={"email": lead.email, "password": lead.password}
    )
    token = login_response.json()["token"]

    response = client.get(
        f"/users/{seed_users['crew_a'].id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert "director" in response.json()["detail"].lower()


def test_cross_org_record_is_404_not_403(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director_a = seed_users["director_a"]
    director_b = seed_users["director_b"]
    login_response = client.post(
        "/auth/login", json={"email": director_a.email, "password": director_a.password}
    )
    token = login_response.json()["token"]

    response = client.get(
        f"/users/{director_b.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_same_org_record_is_visible_to_an_allowed_role(
    client: TestClient, seed_users: dict[str, SeededUser]
) -> None:
    director_a = seed_users["director_a"]
    crew_a = seed_users["crew_a"]
    login_response = client.post(
        "/auth/login", json={"email": director_a.email, "password": director_a.password}
    )
    token = login_response.json()["token"]

    response = client.get(
        f"/users/{crew_a.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == crew_a.email
