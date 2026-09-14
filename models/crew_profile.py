"""``crew_profiles`` — the crew-specific 1:1 extension of a ``crew_member`` user.

Only ever created for the ``crew_member`` role; Directors and Mission Leads are
never matchable, so they never get one (PRD §10 #11).

No ``org_id`` column here (or on ``crew_skills``/``availability_windows`` —
both FK off ``crew_profiles.user_id``) — tenant scoping for all three tables
happens exactly once, in ``services.crew``, via ``models.user.get_user``
before any of these helpers are ever called. That's why every function below
takes a plain ``user_id``/``crew_id``, not an ``org_id`` — re-deriving org
scope here would be redundant with (and could drift from) that single check.
"""

from __future__ import annotations

from sqlmodel import Field, Session, SQLModel


class CrewProfile(SQLModel, table=True):
    __tablename__ = "crew_profiles"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    contact: str | None = None
    bio: str | None = None


def get_crew_profile(session: Session, user_id: int) -> CrewProfile | None:
    """Fetch the profile row if one has been created; ``None`` otherwise —
    callers that only need to *view* a profile should fall back to defaults
    rather than force a row into existence (see ``services.crew``)."""
    return session.get(CrewProfile, user_id)


def get_or_create_crew_profile(session: Session, user_id: int) -> CrewProfile:
    """Fetch the profile row, creating an empty one if this is the crew
    member's first write (profile update, a skill set, or an availability
    window added) — required before either child table can FK to it."""
    profile = session.get(CrewProfile, user_id)
    if profile is None:
        profile = CrewProfile(user_id=user_id)
        session.add(profile)
        session.flush()
    return profile
