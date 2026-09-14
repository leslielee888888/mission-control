"""``requirements`` — one staffing need on a mission: a skill, a minimum
proficiency, a headcount (FR-8). The unit the matcher runs against (FR-13)."""

from __future__ import annotations

from sqlmodel import Field, SQLModel


class Requirement(SQLModel, table=True):
    __tablename__ = "requirements"

    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    skill_id: int = Field(foreign_key="skills.id")
    min_proficiency: int
    headcount: int
