"""``crew_skills`` — a crew member's proficiency (1-5) at one org skill (FR-6).

Composite primary key on ``(crew_id, skill_id)``: it both identifies the row
and enforces "one proficiency per crew/skill pair" without a separate
surrogate id or unique constraint.
"""

from __future__ import annotations

from sqlmodel import Field, Session, SQLModel, select


class CrewSkill(SQLModel, table=True):
    __tablename__ = "crew_skills"

    crew_id: int = Field(foreign_key="crew_profiles.user_id", primary_key=True)
    skill_id: int = Field(foreign_key="skills.id", primary_key=True)
    proficiency: int = Field(ge=1, le=5)


def list_crew_skills(session: Session, crew_id: int) -> list[CrewSkill]:
    statement = select(CrewSkill).where(CrewSkill.crew_id == crew_id)
    return list(session.exec(statement).all())


def upsert_crew_skill(
    session: Session, *, crew_id: int, skill_id: int, proficiency: int
) -> CrewSkill:
    """Set a crew member's proficiency on a skill, creating the row on first
    set and overwriting it on every later one (FR-6 has no separate
    "already holds this skill" error — setting again just updates it)."""
    existing = session.get(CrewSkill, (crew_id, skill_id))
    if existing is not None:
        existing.proficiency = proficiency
        session.add(existing)
        session.flush()
        return existing
    crew_skill = CrewSkill(crew_id=crew_id, skill_id=skill_id, proficiency=proficiency)
    session.add(crew_skill)
    session.flush()
    return crew_skill
