"""``assignments`` — a crew member proposed (and possibly confirmed or
declined) against one requirement (FR-14/FR-15/FR-16).

Like ``crew_profiles``/``crew_skills`` (see ``models/crew_profile.py``),
this table carries no ``org_id`` column of its own — an assignment's org is
whatever org its requirement's mission belongs to. So every org-scoped query
here joins ``requirements`` -> ``missions`` to reach ``Mission.org_id``,
rather than duplicating that column redundantly on this table.

``confirmed_assignment_missions`` is shared by two callers that both need
"every mission this crew member holds a *confirmed* assignment on, excluding
one mission": T5's matcher retrieval stage (``services/matcher.py``,
FR-13a — both the hard conflict filter and the availability-margin gap
calculation) and T6's double-booking guard (``services/assignment.py``,
FR-16). It lives here rather than in either service module so neither one
carries its own copy of the same query.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, Session, SQLModel, select

from models.enums import AssignmentStatus
from models.mission import Mission
from models.requirement import Requirement
from models.timestamps import utc_now


class Assignment(SQLModel, table=True):
    __tablename__ = "assignments"

    id: int | None = Field(default=None, primary_key=True)
    requirement_id: int = Field(foreign_key="requirements.id", index=True)
    crew_id: int = Field(foreign_key="crew_profiles.user_id", index=True)
    proposed_by: int = Field(foreign_key="users.id")
    status: AssignmentStatus = Field(default=AssignmentStatus.PROPOSED)
    proposed_at: datetime = Field(default_factory=utc_now)
    responded_at: datetime | None = None


def get_assignment(session: Session, org_id: int, assignment_id: int) -> Assignment | None:
    """Fetch an assignment scoped to ``org_id``, joining through its
    requirement's mission (FR-1 tenant-scoping pattern — a cross-org id reads
    back as ``None``, same as ``models.mission.get_mission``)."""
    statement = (
        select(Assignment)
        .join(Requirement, Requirement.id == Assignment.requirement_id)
        .join(Mission, Mission.id == Requirement.mission_id)
        .where(Assignment.id == assignment_id, Mission.org_id == org_id)
    )
    return session.exec(statement).first()


def list_assignments_for_org(session: Session, org_id: int) -> list[Assignment]:
    """Every assignment in an org, across every mission (Director/Lead
    ``assignment list``)."""
    statement = (
        select(Assignment)
        .join(Requirement, Requirement.id == Assignment.requirement_id)
        .join(Mission, Mission.id == Requirement.mission_id)
        .where(Mission.org_id == org_id)
        .order_by(Assignment.id)
    )
    return list(session.exec(statement).all())


def list_assignments_for_crew(session: Session, org_id: int, crew_id: int) -> list[Assignment]:
    """One crew member's own assignments, org-scoped (Crew Member
    ``assignment list``)."""
    statement = (
        select(Assignment)
        .join(Requirement, Requirement.id == Assignment.requirement_id)
        .join(Mission, Mission.id == Requirement.mission_id)
        .where(Mission.org_id == org_id, Assignment.crew_id == crew_id)
        .order_by(Assignment.id)
    )
    return list(session.exec(statement).all())


def count_active_assignments(session: Session, requirement_id: int) -> int:
    """``proposed`` + ``confirmed`` assignments on a requirement — what
    counts against its headcount (FR-14). Recalculated by reading, never
    stored, so a decline immediately reopens the slot it held (FR-15)."""
    statement = select(Assignment).where(
        Assignment.requirement_id == requirement_id,
        Assignment.status.in_((AssignmentStatus.PROPOSED, AssignmentStatus.CONFIRMED)),
    )
    return len(session.exec(statement).all())


def create_assignment(
    session: Session, *, requirement_id: int, crew_id: int, proposed_by: int
) -> Assignment:
    """Insert a new assignment row, starting in ``proposed`` (the field
    default) — FR-14. Caller commits."""
    assignment = Assignment(requirement_id=requirement_id, crew_id=crew_id, proposed_by=proposed_by)
    session.add(assignment)
    session.flush()
    return assignment


def confirmed_assignment_missions(
    session: Session, crew_id: int, *, exclude_mission_id: int | None = None
) -> list[Mission]:
    """Every mission (full row, not just its date range) this crew member
    holds a *confirmed* assignment on, excluding ``exclude_mission_id``.

    Shared by the matcher's hard-filter/availability-margin calculations
    (T5, FR-13a) and the double-booking guard (T6, FR-16) — the guard needs
    the whole ``Mission`` row (not just its dates) so it can name the
    conflicting mission in its error.
    """
    statement = (
        select(Mission)
        .select_from(Assignment)
        .join(Requirement, Requirement.id == Assignment.requirement_id)
        .join(Mission, Mission.id == Requirement.mission_id)
        .where(Assignment.crew_id == crew_id, Assignment.status == AssignmentStatus.CONFIRMED)
    )
    missions = session.exec(statement).all()
    return [mission for mission in missions if mission.id != exclude_mission_id]
