"""``crew_profiles`` — the crew-specific 1:1 extension of a ``crew_member`` user.

Only ever created for the ``crew_member`` role; Directors and Mission Leads are
never matchable, so they never get one (PRD §10 #11).
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class CrewProfile(SQLModel, table=True):
    __tablename__ = "crew_profiles"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    contact: str | None = None
    bio: str | None = None
