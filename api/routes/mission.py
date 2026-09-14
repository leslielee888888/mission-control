"""``/missions`` — mission CRUD, requirements, and the 6-state lifecycle
(FR-8/FR-9/FR-10/FR-11/FR-12/FR-17).

Every route is org-scoped through ``services.mission``'s
``models.mission.get_mission`` lookups (FR-1: cross-org id -> 404). Role
gating that doesn't depend on a loaded mission (create/add-requirement:
Mission Lead or Director; approve/reject: Director only) is a
``Depends(require_role(...))`` on the route, matching T2/T3's dependency-
injection pattern. Everything that *does* depend on the loaded mission —
the creator-only check behind ``submit``, the self-approval gate behind
``approve``/``reject`` — lives in ``services.mission.execute_mission_transition``,
the one Command executor for all six lifecycle actions; the six routes below
are thin translators into and out of it, not six separate implementations.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session

from api.deps import get_current_user, require_role
from models.database import get_session
from models.enums import MissionStatus, Role
from models.mission import Mission
from models.user import User
from services.mission import (
    InvalidMissionTransitionError,
    MissingReasonError,
    MissionHasNoRequirementsError,
    MissionNotEditableError,
    MissionNotFoundError,
    NotMissionCreatorError,
    RequirementFulfillment,
    RequirementSkillNotFoundError,
    SelfApprovalError,
    add_requirement,
    create_mission,
    execute_mission_transition,
    get_mission_detail,
    list_org_missions,
)

router = APIRouter(prefix="/missions", tags=["missions"])


# --- schemas -----------------------------------------------------------


class MissionCreateRequest(BaseModel):
    name: str
    description: str
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _end_not_before_start(self) -> MissionCreateRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class RequirementCreateRequest(BaseModel):
    skill_id: int
    min_proficiency: int = Field(ge=1, le=5)
    headcount: int = Field(ge=1)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class MissionOut(BaseModel):
    id: int
    org_id: int
    created_by: int
    name: str
    description: str
    start_date: date
    end_date: date
    status: MissionStatus


class RequirementOut(BaseModel):
    id: int
    mission_id: int
    skill_id: int
    skill_name: str
    min_proficiency: int
    headcount: int
    confirmed: int


class MissionDetailOut(MissionOut):
    requirements: list[RequirementOut]


# --- helpers -----------------------------------------------------------


def _to_mission_out(mission: Mission) -> MissionOut:
    return MissionOut.model_validate(mission, from_attributes=True)


def _to_requirement_out(fulfillment: RequirementFulfillment) -> RequirementOut:
    requirement = fulfillment.requirement
    return RequirementOut(
        id=requirement.id,  # type: ignore[arg-type]
        mission_id=requirement.mission_id,
        skill_id=requirement.skill_id,
        skill_name=fulfillment.skill_name,
        min_proficiency=requirement.min_proficiency,
        headcount=requirement.headcount,
        confirmed=fulfillment.confirmed,
    )


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _apply_transition(
    session: Session,
    caller: User,
    mission_id: int,
    action: str,
    **payload: object,
) -> Mission:
    """Shared try/except around ``execute_mission_transition`` so the six
    action routes below stay a one-line call each."""
    try:
        return execute_mission_transition(
            session, caller.org_id, mission_id, caller, action, **payload
        )
    except MissionNotFoundError as exc:
        raise _not_found() from exc
    except InvalidMissionTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except MissionHasNoRequirementsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot submit a mission with no requirements",
        ) from exc
    except NotMissionCreatorError as exc:
        raise _forbidden("Only the mission's creator may submit it") from exc
    except SelfApprovalError as exc:
        raise _forbidden(
            "The mission's creator may not approve or reject their own mission"
        ) from exc
    except MissingReasonError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[{"field": "reason", "message": "reason is required to reject a mission"}],
        ) from exc


# --- mission CRUD + requirements (FR-8) ---------------------------------


@router.post("", response_model=MissionOut, status_code=status.HTTP_201_CREATED)
def create_mission_route(
    payload: MissionCreateRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR, Role.MISSION_LEAD)),
) -> MissionOut:
    mission = create_mission(
        session,
        caller.org_id,
        caller,
        name=payload.name,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    return _to_mission_out(mission)


@router.get("", response_model=list[MissionOut])
def list_missions_route(
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> list[MissionOut]:
    missions = list_org_missions(session, caller.org_id)
    return [_to_mission_out(mission) for mission in missions]


@router.get("/{mission_id}", response_model=MissionDetailOut)
def get_mission_route(
    mission_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> MissionDetailOut:
    try:
        detail = get_mission_detail(session, caller.org_id, mission_id)
    except MissionNotFoundError as exc:
        raise _not_found() from exc
    return MissionDetailOut(
        **_to_mission_out(detail.mission).model_dump(),
        requirements=[_to_requirement_out(fulfillment) for fulfillment in detail.requirements],
    )


@router.post(
    "/{mission_id}/requirements",
    response_model=RequirementOut,
    status_code=status.HTTP_201_CREATED,
)
def add_requirement_route(
    mission_id: int,
    payload: RequirementCreateRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR, Role.MISSION_LEAD)),
) -> RequirementOut:
    try:
        fulfillment = add_requirement(
            session,
            caller.org_id,
            mission_id,
            skill_id=payload.skill_id,
            min_proficiency=payload.min_proficiency,
            headcount=payload.headcount,
        )
    except MissionNotFoundError as exc:
        raise _not_found() from exc
    except MissionNotEditableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Requirements can only be added while the mission is in draft",
        ) from exc
    except RequirementSkillNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill {payload.skill_id} not found in this org",
        ) from exc
    return _to_requirement_out(fulfillment)


# --- lifecycle actions (FR-9/FR-10/FR-11/FR-12) -------------------------
#
# Each route only differs in its `action` string, its role gate, and (for
# `reject`) its payload -- everything else routes into the one executor.


@router.post("/{mission_id}/submit", response_model=MissionOut)
def submit_mission_route(
    mission_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR, Role.MISSION_LEAD)),
) -> MissionOut:
    mission = _apply_transition(session, caller, mission_id, "submit")
    return _to_mission_out(mission)


@router.post("/{mission_id}/approve", response_model=MissionOut)
def approve_mission_route(
    mission_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR)),
) -> MissionOut:
    mission = _apply_transition(session, caller, mission_id, "approve")
    return _to_mission_out(mission)


@router.post("/{mission_id}/reject", response_model=MissionOut)
def reject_mission_route(
    mission_id: int,
    payload: RejectRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR)),
) -> MissionOut:
    mission = _apply_transition(session, caller, mission_id, "reject", reason=payload.reason)
    return _to_mission_out(mission)


@router.post("/{mission_id}/activate", response_model=MissionOut)
def activate_mission_route(
    mission_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR, Role.MISSION_LEAD)),
) -> MissionOut:
    mission = _apply_transition(session, caller, mission_id, "activate")
    return _to_mission_out(mission)


@router.post("/{mission_id}/complete", response_model=MissionOut)
def complete_mission_route(
    mission_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR, Role.MISSION_LEAD)),
) -> MissionOut:
    mission = _apply_transition(session, caller, mission_id, "complete")
    return _to_mission_out(mission)


@router.post("/{mission_id}/cancel", response_model=MissionOut)
def cancel_mission_route(
    mission_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR, Role.MISSION_LEAD)),
) -> MissionOut:
    mission = _apply_transition(session, caller, mission_id, "cancel")
    return _to_mission_out(mission)
