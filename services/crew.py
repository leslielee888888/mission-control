"""Crew management domain logic (T3, FR-4/FR-5/FR-6/FR-7).

Routes stay thin: they translate HTTP <-> these functions. This is where the
real domain rules live — tenant-scoped lookups, uniqueness, overlap
checking, and the "is this the right crew member" identity check that FR-4/
FR-6/FR-7 need on top of plain role-based access control (that part stays in
``api/deps.require_role``; the routes call both).

Every function here starts from ``models.user.get_user(session, org_id,
...)`` (or ``models.skill.get_skill`` for the org-scoped skill table) —
the one place FR-1 tenant scoping happens for crew data, since
``crew_profiles``/``crew_skills``/``availability_windows`` carry no
``org_id`` column of their own (see ``models/crew_profile.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session

from models.availability_window import (
    AvailabilityWindow,
    create_availability_window,
    delete_availability_window,
    get_availability_window,
    list_availability_windows,
)
from models.crew_profile import CrewProfile, get_crew_profile, get_or_create_crew_profile
from models.crew_skill import CrewSkill, list_crew_skills, upsert_crew_skill
from models.enums import Role
from models.skill import Skill, create_skill, get_skill_by_name, list_skills
from models.user import User, get_user


class CrewMemberNotFoundError(Exception):
    """No crew member with this id exists in the caller's org (-> 404)."""


class DuplicateSkillError(Exception):
    """A skill with this name already exists in the org (-> 409, FR-5)."""


class SkillNotFoundError(Exception):
    """No skill with this id/name exists in the caller's org (-> 404)."""


class OverlappingWindowError(Exception):
    """The requested window overlaps an existing one for this crew member
    (-> 409, FR-7)."""

    def __init__(self, conflicting: AvailabilityWindow) -> None:
        self.conflicting = conflicting
        super().__init__("Availability window overlaps an existing window")


class WindowNotFoundError(Exception):
    """No availability window with this id exists for this crew member
    (-> 404)."""


@dataclass(frozen=True)
class CrewProfileView:
    user: User
    profile: CrewProfile
    skills: list[tuple[CrewSkill, Skill]]


def get_crew_member(session: Session, org_id: int, crew_user_id: int) -> User:
    """Resolve and validate a crew member id within an org.

    The single entry point every crew-scoped function below starts from:
    enforces FR-1 tenant scoping (wrong org -> indistinguishable from
    "doesn't exist") and the "only crew_member users have a crew profile"
    invariant (PRD §10 #11) in one place.
    """
    user = get_user(session, org_id, crew_user_id)
    if user is None or user.role != Role.CREW_MEMBER:
        raise CrewMemberNotFoundError
    return user


def view_crew_profile(session: Session, org_id: int, crew_user_id: int) -> CrewProfileView:
    """Read-only profile view (FR-4 Director/Lead view, or a crew member's
    own ``profile show``). Never creates rows — an unset profile/skill list
    just reads back as defaults."""
    user = get_crew_member(session, org_id, crew_user_id)
    profile = get_crew_profile(session, user.id) or CrewProfile(user_id=user.id)  # type: ignore[arg-type]
    crew_skills = list_crew_skills(session, user.id)  # type: ignore[arg-type]
    skills = [(cs, _skill_or_raise(session, cs.skill_id)) for cs in crew_skills]
    return CrewProfileView(user=user, profile=profile, skills=skills)


def _skill_or_raise(session: Session, skill_id: int) -> Skill:
    skill = session.get(Skill, skill_id)
    assert skill is not None  # crew_skills.skill_id is an FK: always resolves
    return skill


def update_crew_profile(
    session: Session,
    org_id: int,
    crew_user_id: int,
    *,
    name: str | None,
    contact: str | None,
    bio: str | None,
) -> CrewProfileView:
    """PATCH-style self-update: only the fields given change (FR-4)."""
    user = get_crew_member(session, org_id, crew_user_id)
    assert user.id is not None
    profile = get_or_create_crew_profile(session, user.id)
    if name is not None:
        user.name = name
        session.add(user)
    if contact is not None:
        profile.contact = contact
    if bio is not None:
        profile.bio = bio
    session.add(profile)
    session.commit()
    session.refresh(user)
    session.refresh(profile)
    crew_skills = list_crew_skills(session, user.id)
    skills = [(cs, _skill_or_raise(session, cs.skill_id)) for cs in crew_skills]
    return CrewProfileView(user=user, profile=profile, skills=skills)


def create_org_skill(session: Session, org_id: int, name: str, category: str | None) -> Skill:
    """Director creates an org-scoped skill, unique by name within the org
    (FR-5)."""
    if get_skill_by_name(session, org_id, name) is not None:
        raise DuplicateSkillError
    skill = create_skill(session, org_id=org_id, name=name, category=category)
    session.commit()
    session.refresh(skill)
    return skill


def list_org_skills(session: Session, org_id: int) -> list[Skill]:
    return list_skills(session, org_id)


def set_crew_skill_proficiency(
    session: Session,
    org_id: int,
    crew_user_id: int,
    skill_name: str,
    proficiency: int,
) -> tuple[CrewSkill, Skill]:
    """Set a crew member's proficiency (1-5) on an org skill — called by the
    crew member themselves, or a Director on their behalf (FR-6)."""
    user = get_crew_member(session, org_id, crew_user_id)
    assert user.id is not None
    skill = get_skill_by_name(session, org_id, skill_name)
    if skill is None:
        raise SkillNotFoundError
    assert skill.id is not None
    get_or_create_crew_profile(session, user.id)
    crew_skill = upsert_crew_skill(
        session, crew_id=user.id, skill_id=skill.id, proficiency=proficiency
    )
    session.commit()
    session.refresh(crew_skill)
    return crew_skill, skill


def _windows_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """Date-range overlap, inclusive of shared boundary days: two windows
    that each include the same day count as overlapping (FR-7)."""
    return a_start <= b_end and b_start <= a_end


def add_availability_window(
    session: Session,
    org_id: int,
    crew_user_id: int,
    start_date: date,
    end_date: date,
) -> AvailabilityWindow:
    """Add an unavailability window; rejects it if it overlaps any of this
    crew member's existing windows (FR-7)."""
    user = get_crew_member(session, org_id, crew_user_id)
    assert user.id is not None
    get_or_create_crew_profile(session, user.id)
    for existing in list_availability_windows(session, user.id):
        if _windows_overlap(start_date, end_date, existing.start_date, existing.end_date):
            raise OverlappingWindowError(existing)
    window = create_availability_window(
        session, crew_id=user.id, start_date=start_date, end_date=end_date
    )
    session.commit()
    session.refresh(window)
    return window


def list_crew_availability_windows(
    session: Session, org_id: int, crew_user_id: int
) -> list[AvailabilityWindow]:
    user = get_crew_member(session, org_id, crew_user_id)
    assert user.id is not None
    return list_availability_windows(session, user.id)


def remove_availability_window(
    session: Session, org_id: int, crew_user_id: int, window_id: int
) -> None:
    """Delete an unavailability window — delete-only, no in-place edit
    (FR-7, PRD §10 #2)."""
    user = get_crew_member(session, org_id, crew_user_id)
    assert user.id is not None
    window = get_availability_window(session, user.id, window_id)
    if window is None:
        raise WindowNotFoundError
    delete_availability_window(session, window)
    session.commit()
