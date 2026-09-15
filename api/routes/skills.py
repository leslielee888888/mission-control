"""``/skills`` — an org's own flat skill taxonomy (FR-5).

Creation is Director-only; listing is open to any authenticated user in the
org, since every role (crew setting their own proficiency, a Director
creating one, a Lead browsing) needs to see the taxonomy's names.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import get_current_user, require_role
from models.database import get_session
from models.enums import Role
from models.skill import Skill
from models.user import User
from services.crew import DuplicateSkillError, create_org_skill, list_org_skills

router = APIRouter(prefix="/skills", tags=["skills"])


class SkillCreateRequest(BaseModel):
    name: str
    category: str | None = None


class SkillOut(BaseModel):
    id: int
    org_id: int
    name: str
    category: str | None


def _to_skill_out(skill: Skill) -> SkillOut:
    return SkillOut.model_validate(skill, from_attributes=True)


@router.post("", response_model=SkillOut, status_code=status.HTTP_201_CREATED)
def create_skill_route(
    payload: SkillCreateRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR)),
) -> SkillOut:
    try:
        skill = create_org_skill(session, caller.org_id, payload.name, payload.category)
    except DuplicateSkillError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Skill '{payload.name}' already exists in this org",
        ) from exc
    return _to_skill_out(skill)


@router.get("", response_model=list[SkillOut])
def list_skills_route(
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> list[SkillOut]:
    skills = list_org_skills(session, caller.org_id)
    return [_to_skill_out(skill) for skill in skills]
