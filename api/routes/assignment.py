"""``/assignments`` — propose, respond, double-booking guard (T6, FR-14/
FR-15/FR-16).

``propose`` is role-gated the same way as ``mission.add_requirement``
(Mission Lead or Director; ``Depends(require_role(...))``) since it doesn't
depend on a loaded row. ``respond`` admits any authenticated user and
enforces its "named crew member only" rule inside
``services.assignment.respond_to_assignment`` instead — the same shape as
T4's self-approval gate, since the rule is about *identity*, not role (a
crew member's own Director/Lead must also be refused, and role gating alone
can't express that).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import get_current_user, require_role
from models.database import get_session
from models.enums import AssignmentStatus, Role
from models.user import User
from services.assignment import (
    AssignmentNotFoundError,
    AssignmentView,
    CrewMemberNotFoundError,
    DoubleBookingError,
    HeadcountExceededError,
    InvalidAssignmentActionError,
    MissionNotFoundError,
    NotAssignmentCrewMemberError,
    RequirementNotFoundError,
    list_assignments,
    propose_assignment,
    respond_to_assignment,
)

router = APIRouter(prefix="/assignments", tags=["assignments"])


# --- schemas -----------------------------------------------------------


class AssignmentProposeRequest(BaseModel):
    mission_id: int
    requirement_id: int
    crew_id: int


class AssignmentRespondRequest(BaseModel):
    action: Literal["accept", "decline"]


class AssignmentOut(BaseModel):
    id: int
    mission_id: int
    requirement_id: int
    crew_id: int
    proposed_by: int
    status: AssignmentStatus
    proposed_at: datetime
    responded_at: datetime | None


# --- helpers -----------------------------------------------------------


def _to_assignment_out(view: AssignmentView) -> AssignmentOut:
    assignment = view.assignment
    return AssignmentOut(
        id=assignment.id,  # type: ignore[arg-type]
        mission_id=view.mission_id,
        requirement_id=assignment.requirement_id,
        crew_id=assignment.crew_id,
        proposed_by=assignment.proposed_by,
        status=assignment.status,
        proposed_at=assignment.proposed_at,
        responded_at=assignment.responded_at,
    )


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


# --- routes --------------------------------------------------------------


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def propose_assignment_route(
    payload: AssignmentProposeRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR, Role.MISSION_LEAD)),
) -> AssignmentOut:
    try:
        view = propose_assignment(
            session,
            caller.org_id,
            caller,
            mission_id=payload.mission_id,
            requirement_id=payload.requirement_id,
            crew_id=payload.crew_id,
        )
    except MissionNotFoundError as exc:
        raise _not_found("Mission not found") from exc
    except RequirementNotFoundError as exc:
        raise _not_found("Requirement not found on this mission") from exc
    except CrewMemberNotFoundError as exc:
        raise _not_found("Crew member not found") from exc
    except HeadcountExceededError as exc:
        raise _conflict(str(exc)) from exc
    return _to_assignment_out(view)


@router.post("/{assignment_id}/respond", response_model=AssignmentOut)
def respond_to_assignment_route(
    assignment_id: int,
    payload: AssignmentRespondRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> AssignmentOut:
    try:
        view = respond_to_assignment(session, caller.org_id, caller, assignment_id, payload.action)
    except AssignmentNotFoundError as exc:
        raise _not_found("Assignment not found") from exc
    except NotAssignmentCrewMemberError as exc:
        raise _forbidden("Only the assignment's named crew member may respond to it") from exc
    except InvalidAssignmentActionError as exc:
        raise _conflict(str(exc)) from exc
    except DoubleBookingError as exc:
        raise _conflict(str(exc)) from exc
    return _to_assignment_out(view)


@router.get("", response_model=list[AssignmentOut])
def list_assignments_route(
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> list[AssignmentOut]:
    views = list_assignments(session, caller.org_id, caller)
    return [_to_assignment_out(view) for view in views]
