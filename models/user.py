"""``users`` — every person who can log in, across all three roles (§4).

Query helpers live here, alongside the entity (see ``models/__init__.py``).
``get_user`` is the org_id-required shape every later task's own repository
helpers should follow (T2 acceptance criteria) — it returns ``None`` both
when the id doesn't exist at all and when it belongs to a different org, so
a cross-org lookup 404s instead of leaking existence (FR-1).

``get_user_by_email`` and ``get_user_by_id_unscoped`` are the two deliberate
exceptions to that pattern: they back identity *resolution* (login, and
bearer-token lookup in ``api/deps.get_current_user``), which by definition
runs before the caller's org is known. Everything downstream of that must go
through ``get_user``.
"""

from __future__ import annotations

from sqlmodel import Field, Session, SQLModel, select

from models.enums import Role


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organizations.id", index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: Role
    name: str


def get_user_by_email(session: Session, email: str) -> User | None:
    """Look up a user by email, globally (not org-scoped) — the login
    identity-resolution step, before any org context exists."""
    statement = select(User).where(User.email == email)
    return session.exec(statement).first()


def get_user_by_id_unscoped(session: Session, user_id: int) -> User | None:
    """Look up a user by primary key, globally (not org-scoped).

    Used only by ``api/deps.get_current_user`` to resolve a bearer token to
    its owner before any org context exists. Every other caller must use
    ``get_user(session, org_id, user_id)`` instead.
    """
    return session.get(User, user_id)


def get_user(session: Session, org_id: int, user_id: int) -> User | None:
    """Fetch a user by id, scoped to ``org_id`` (FR-1, the tenant-scoping
    pattern every T3+ repository helper follows)."""
    user = session.get(User, user_id)
    if user is None or user.org_id != org_id:
        return None
    return user


def list_crew_members(session: Session, org_id: int) -> list[User]:
    """Every ``crew_member``-role user in an org — the candidate pool the
    matcher's retrieval stage starts from (FR-13). Directors and Mission
    Leads are never matchable (PRD §10 #11), so they're excluded here rather
    than filtered out by every caller."""
    statement = (
        select(User).where(User.org_id == org_id, User.role == Role.CREW_MEMBER).order_by(User.id)
    )
    return list(session.exec(statement).all())
