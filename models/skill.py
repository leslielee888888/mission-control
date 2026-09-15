"""``skills`` — an org's own flat skill taxonomy (FR-5)."""

from __future__ import annotations

from sqlmodel import Field, Session, SQLModel, UniqueConstraint, select


class Skill(SQLModel, table=True):
    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("org_id", "name", name="uq_skills_org_id_name"),)

    id: int | None = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organizations.id", index=True)
    name: str
    category: str | None = None


def get_skill(session: Session, org_id: int, skill_id: int) -> Skill | None:
    """Fetch a skill by id, scoped to ``org_id`` (FR-1 tenant-scoping pattern)."""
    skill = session.get(Skill, skill_id)
    if skill is None or skill.org_id != org_id:
        return None
    return skill


def get_skill_by_name(session: Session, org_id: int, name: str) -> Skill | None:
    """Look up a skill by its (org-scoped) name — backs the FR-5 uniqueness
    check before insert."""
    statement = select(Skill).where(Skill.org_id == org_id, Skill.name == name)
    return session.exec(statement).first()


def list_skills(session: Session, org_id: int) -> list[Skill]:
    statement = select(Skill).where(Skill.org_id == org_id).order_by(Skill.name)
    return list(session.exec(statement).all())


def create_skill(session: Session, *, org_id: int, name: str, category: str | None) -> Skill:
    skill = Skill(org_id=org_id, name=name, category=category)
    session.add(skill)
    session.flush()
    return skill
