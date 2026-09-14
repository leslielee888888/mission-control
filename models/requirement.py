"""``requirements`` — one staffing need on a mission: a skill, a minimum
proficiency, a headcount (FR-8). The unit the matcher runs against (FR-13)."""

from __future__ import annotations

from sqlmodel import Field, Session, SQLModel, select


class Requirement(SQLModel, table=True):
    __tablename__ = "requirements"

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    skill_id: int = Field(foreign_key="skills.id")
    min_proficiency: int
    headcount: int


def get_requirement(session: Session, mission_id: int, requirement_id: int) -> Requirement | None:
    """Fetch a requirement scoped to its mission. No separate ``org_id``
    column here (mirrors ``crew_profiles`` — see ``models/crew_profile.py``):
    tenant scoping happens once, in ``services.mission``, via
    ``models.mission.get_mission`` before this is ever called."""
    requirement = session.get(Requirement, requirement_id)
    if requirement is None or requirement.mission_id != mission_id:
        return None
    return requirement


def list_requirements(session: Session, mission_id: int) -> list[Requirement]:
    statement = (
        select(Requirement).where(Requirement.mission_id == mission_id).order_by(Requirement.id)
    )
    return list(session.exec(statement).all())


def create_requirement(
    session: Session,
    *,
    mission_id: int,
    skill_id: int,
    min_proficiency: int,
    headcount: int,
) -> Requirement:
    requirement = Requirement(
        mission_id=mission_id,
        skill_id=skill_id,
        min_proficiency=min_proficiency,
        headcount=headcount,
    )
    session.add(requirement)
    session.flush()
    return requirement
