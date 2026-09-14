"""``skills`` — an org's own flat skill taxonomy (FR-5)."""

from __future__ import annotations

from sqlmodel import Field, SQLModel, UniqueConstraint


class Skill(SQLModel, table=True):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_skills_org_id_name"),)

    id: int | None = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organizations.id", index=True)
    name: str
    category: str | None = None
