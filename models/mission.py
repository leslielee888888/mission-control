"""``missions`` — one mission in one org, moving through the FR-9 lifecycle.

Query helpers follow the ``get_x(session, org_id, id)`` tenant-scoping
pattern established by ``models.user.get_user`` (FR-1): a cross-org id reads
back as ``None``, indistinguishable from "doesn't exist", so callers 404
instead of 403.
"""

from __future__ import annotations

from datetime import date

from sqlmodel import Field, Session, SQLModel, select

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


def get_mission(session: Session, org_id: int, mission_id: int) -> Mission | None:
    """Fetch a mission by id, scoped to ``org_id`` (FR-1 tenant-scoping pattern)."""
    mission = session.get(Mission, mission_id)
    if mission is None or mission.org_id != org_id:
        return None
    return mission


def list_missions(session: Session, org_id: int) -> list[Mission]:
    statement = select(Mission).where(Mission.org_id == org_id).order_by(Mission.id)
    return list(session.exec(statement).all())


def create_mission(
    session: Session,
    *,
    org_id: int,
    created_by: int,
    name: str,
    description: str,
    start_date: date,
    end_date: date,
) -> Mission:
    """Insert a new mission row, starting in ``draft`` (the field default) —
    FR-8. Caller commits."""
    mission = Mission(
        org_id=org_id,
        created_by=created_by,
        name=name,
        description=description,
        start_date=start_date,
        end_date=end_date,
    )
    session.add(mission)
    session.flush()
    return mission
