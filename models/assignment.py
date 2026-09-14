"""``assignments`` — a crew member proposed (and possibly confirmed or
declined) against one requirement (FR-14/FR-15/FR-16)."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from models.enums import AssignmentStatus
from models.timestamps import utc_now


class Assignment(SQLModel, table=True):
    __tablename__ = "assignments"

    id: int | None = Field(default=None, primary_key=True)
    requirement_id: int = Field(foreign_key="requirements.id", index=True)
    crew_id: int = Field(foreign_key="crew_profiles.user_id", index=True)
    proposed_by: int = Field(foreign_key="users.id")
    status: AssignmentStatus = Field(default=AssignmentStatus.PROPOSED)
    proposed_at: datetime = Field(default_factory=utc_now)
    responded_at: datetime | None = None
