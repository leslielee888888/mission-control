"""``crew_skills`` — a crew member's proficiency (1-5) at one org skill (FR-6).

Composite primary key on ``(crew_id, skill_id)``: it both identifies the row
and enforces "one proficiency per crew/skill pair" without a separate
surrogate id or unique constraint.
"""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class CrewSkill(SQLModel, table=True):
    __tablename__ = "crew_skills"

    crew_id: int = Field(foreign_key="crew_profiles.user_id", primary_key=True)
    skill_id: int = Field(foreign_key="skills.id", primary_key=True)
    proficiency: int
