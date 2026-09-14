"""``missions`` — one mission in one org, moving through the FR-9 lifecycle."""

from __future__ import annotations

from datetime import date

from sqlmodel import Field, SQLModel

from models.enums import MissionStatus


class Mission(SQLModel, table=True):
    __tablename__ = "missions"

    id: int | None = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organizations.id", index=True)
    created_by: int = Field(foreign_key="users.id")
    name: str
    description: str
    start_date: date
    end_date: date
    status: MissionStatus = Field(default=MissionStatus.DRAFT)
