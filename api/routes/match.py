"""``/missions/{mission_id}/match`` — run the matching engine (T5, FR-13).

Read-only: retrieval + ranking only, no assignment creation or propose/
accept/decline (that's T6). Role-gated the same as every other route that
inspects a mission's requirements in a Lead/Director capacity
(``require_role(DIRECTOR, MISSION_LEAD)``) -- crew members are the ones
being matched, not the ones running the match.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import require_role
from models.database import get_session
from models.enums import Role
from models.user import User
from services.matcher import (
    MatchCandidate,
    MissionNotFoundError,
    RequirementMatch,
    RequirementNotFoundError,
    match_mission,
    match_single_requirement,
)

router = APIRouter(prefix="/missions", tags=["match"])


# --- schemas -----------------------------------------------------------


class MatchCandidateOut(BaseModel):
    crew_id: int
    crew_name: str
    score: float
    proficiency_surplus_score: float
    workload_score: float
    availability_margin_score: float
    breakdown: str


class RequirementMatchOut(BaseModel):
    requirement_id: int
    skill_id: int
    min_proficiency: int
    headcount: int
    candidates: list[MatchCandidateOut]


# --- helpers -----------------------------------------------------------


def _to_candidate_out(candidate: MatchCandidate) -> MatchCandidateOut:
    assert candidate.crew.id is not None
    return MatchCandidateOut(
        crew_id=candidate.crew.id,
        crew_name=candidate.crew.name,
        score=candidate.score,
        proficiency_surplus_score=candidate.proficiency_surplus_score,
        workload_score=candidate.workload_score,
        availability_margin_score=candidate.availability_margin_score,
        breakdown=candidate.breakdown,
    )


def _to_requirement_match_out(match: RequirementMatch) -> RequirementMatchOut:
    assert match.requirement.id is not None
    return RequirementMatchOut(
        requirement_id=match.requirement.id,
        skill_id=match.requirement.skill_id,
        min_proficiency=match.requirement.min_proficiency,
        headcount=match.requirement.headcount,
        candidates=[_to_candidate_out(candidate) for candidate in match.candidates],
    )


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


# --- route ---------------------------------------------------------------


@router.get("/{mission_id}/match", response_model=list[RequirementMatchOut])
def match_mission_route(
    mission_id: int,
    requirement_id: int | None = Query(
        None,
        description=(
            "Match only this requirement id; omit to match every requirement on the mission."
        ),
    ),
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR, Role.MISSION_LEAD)),
) -> list[RequirementMatchOut]:
    try:
        if requirement_id is not None:
            matches = [match_single_requirement(session, caller.org_id, mission_id, requirement_id)]
        else:
            matches = match_mission(session, caller.org_id, mission_id)
    except MissionNotFoundError as exc:
        raise _not_found("Mission not found") from exc
    except RequirementNotFoundError as exc:
        raise _not_found("Requirement not found on this mission") from exc
    return [_to_requirement_match_out(match) for match in matches]
