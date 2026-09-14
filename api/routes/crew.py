"""``/crew/{user_id}/...`` — profile self-service, skill proficiency, and
availability windows (FR-4/FR-6/FR-7).

Every route below is org-scoped through ``services.crew.get_crew_member``
(FR-1: cross-org id -> 404). On top of that, each carries its own identity
rule beyond plain ``require_role`` RBAC:

* profile view  — self, or a Director/Lead viewing another crew member (FR-4)
* profile edit  — self only, and only a crew member (FR-4)
* skill set     — self, or a Director acting on the crew member's behalf (FR-6)
* availability  — self only, always (FR-7 names no "on behalf of" case)
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session

from api.deps import get_current_user
from models.availability_window import AvailabilityWindow
from models.database import get_session
from models.enums import Role
from models.user import User
from services.crew import (
    CrewMemberNotFoundError,
    CrewProfileView,
    OverlappingWindowError,
    SkillNotFoundError,
    WindowNotFoundError,
    add_availability_window,
    list_crew_availability_windows,
    remove_availability_window,
    set_crew_skill_proficiency,
    update_crew_profile,
    view_crew_profile,
)

router = APIRouter(prefix="/crew", tags=["crew"])


# --- schemas ---------------------------------------------------------------


class CrewSkillOut(BaseModel):
    skill_id: int
    skill_name: str
    proficiency: int


class CrewProfileOut(BaseModel):
    user_id: int
    org_id: int
    name: str
    email: str
    contact: str | None
    bio: str | None
    skills: list[CrewSkillOut]


class CrewProfileUpdateRequest(BaseModel):
    name: str | None = None
    contact: str | None = None
    bio: str | None = None


class CrewSkillSetRequest(BaseModel):
    skill_name: str
    proficiency: int = Field(ge=1, le=5)


class AvailabilityWindowCreateRequest(BaseModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _end_not_before_start(self) -> AvailabilityWindowCreateRequest:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class AvailabilityWindowOut(BaseModel):
    id: int
    crew_id: int
    start_date: date
    end_date: date


# --- helpers -----------------------------------------------------------


def _to_profile_out(view: CrewProfileView) -> CrewProfileOut:
    return CrewProfileOut(
        user_id=view.user.id,  # type: ignore[arg-type]
        org_id=view.user.org_id,
        name=view.user.name,
        email=view.user.email,
        contact=view.profile.contact,
        bio=view.profile.bio,
        skills=[
            CrewSkillOut(skill_id=skill.id, skill_name=skill.name, proficiency=cs.proficiency)  # type: ignore[arg-type]
            for cs, skill in view.skills
        ],
    )


def _to_window_out(window: AvailabilityWindow) -> AvailabilityWindowOut:
    return AvailabilityWindowOut.model_validate(window, from_attributes=True)


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Crew member not found")


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _require_view_access(caller: User, target_user_id: int) -> None:
    if caller.id == target_user_id:
        return
    if caller.role in (Role.DIRECTOR, Role.MISSION_LEAD):
        return
    raise _forbidden("Requires role: director, mission_lead (or viewing your own profile)")


def _require_self_edit(caller: User, target_user_id: int) -> None:
    if caller.id != target_user_id or caller.role != Role.CREW_MEMBER:
        raise _forbidden("Requires role: crew_member, editing your own profile")


def _require_skill_set_access(caller: User, target_user_id: int) -> None:
    if caller.role == Role.DIRECTOR:
        return
    if caller.role == Role.CREW_MEMBER and caller.id == target_user_id:
        return
    raise _forbidden("Requires role: director, or crew_member setting your own proficiency")


def _require_self_crew(caller: User, target_user_id: int) -> None:
    if caller.id != target_user_id or caller.role != Role.CREW_MEMBER:
        raise _forbidden("Requires role: crew_member, managing your own availability")


# --- profile -----------------------------------------------------------


@router.get("/{user_id}/profile", response_model=CrewProfileOut)
def get_crew_profile_route(
    user_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> CrewProfileOut:
    _require_view_access(caller, user_id)
    try:
        view = view_crew_profile(session, caller.org_id, user_id)
    except CrewMemberNotFoundError as exc:
        raise _not_found() from exc
    return _to_profile_out(view)


@router.patch("/{user_id}/profile", response_model=CrewProfileOut)
def update_crew_profile_route(
    user_id: int,
    payload: CrewProfileUpdateRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> CrewProfileOut:
    _require_self_edit(caller, user_id)
    try:
        view = update_crew_profile(
            session,
            caller.org_id,
            user_id,
            name=payload.name,
            contact=payload.contact,
            bio=payload.bio,
        )
    except CrewMemberNotFoundError as exc:
        raise _not_found() from exc
    return _to_profile_out(view)


# --- skill proficiency ---------------------------------------------------


@router.put("/{user_id}/skills", response_model=CrewSkillOut)
def set_crew_skill_route(
    user_id: int,
    payload: CrewSkillSetRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> CrewSkillOut:
    _require_skill_set_access(caller, user_id)
    try:
        crew_skill, skill = set_crew_skill_proficiency(
            session, caller.org_id, user_id, payload.skill_name, payload.proficiency
        )
    except CrewMemberNotFoundError as exc:
        raise _not_found() from exc
    except SkillNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{payload.skill_name}' not found in this org",
        ) from exc
    return CrewSkillOut(
        skill_id=skill.id,  # type: ignore[arg-type]
        skill_name=skill.name,
        proficiency=crew_skill.proficiency,
    )


# --- availability --------------------------------------------------------


@router.post(
    "/{user_id}/availability",
    response_model=AvailabilityWindowOut,
    status_code=status.HTTP_201_CREATED,
)
def add_availability_window_route(
    user_id: int,
    payload: AvailabilityWindowCreateRequest,
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> AvailabilityWindowOut:
    _require_self_crew(caller, user_id)
    try:
        window = add_availability_window(
            session, caller.org_id, user_id, payload.start_date, payload.end_date
        )
    except CrewMemberNotFoundError as exc:
        raise _not_found() from exc
    except OverlappingWindowError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Availability window overlaps an existing window "
                f"({exc.conflicting.start_date} to {exc.conflicting.end_date})"
            ),
        ) from exc
    return _to_window_out(window)


@router.get("/{user_id}/availability", response_model=list[AvailabilityWindowOut])
def list_availability_windows_route(
    user_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> list[AvailabilityWindowOut]:
    _require_self_crew(caller, user_id)
    try:
        windows = list_crew_availability_windows(session, caller.org_id, user_id)
    except CrewMemberNotFoundError as exc:
        raise _not_found() from exc
    return [_to_window_out(window) for window in windows]


@router.delete("/{user_id}/availability/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_availability_window_route(
    user_id: int,
    window_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(get_current_user),
) -> None:
    _require_self_crew(caller, user_id)
    try:
        remove_availability_window(session, caller.org_id, user_id, window_id)
    except CrewMemberNotFoundError as exc:
        raise _not_found() from exc
    except WindowNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Availability window not found"
        ) from exc
