"""Assignments: propose, respond, double-booking guard (T6, FR-14/FR-15/
FR-16).

The matcher (T5, ``services/matcher.py``) only finds and ranks eligible
crew — it never writes an ``assignments`` row. This module is what happens
after: a Lead proposes one of the matcher's candidates (or any other
eligible crew member found some other way — nothing here requires having
run the matcher first) and the named crew member accepts or declines it.

Same split of responsibility as ``services.mission``/``services.crew``:
role gating that doesn't depend on a loaded row (propose: Mission Lead or
Director) is a ``Depends(require_role(...))`` at the route; everything that
*does* depend on the loaded assignment — the "only the named crew member"
identity check behind ``respond`` (FR-15, same shape as T4's self-approval
gate), the headcount ceiling behind ``propose`` (FR-14), the double-booking
guard behind ``respond``'s accept path (FR-16) — lives here.

FR-16's guard reuses ``models.assignment.confirmed_assignment_missions`` —
the same "confirmed assignment windows for this crew, excluding one
mission" query T5's own conflict filter uses — so this task doesn't carry a
second copy of that query or of ``services.dates.windows_overlap``. It has
to run here independently of the matcher's own filtering: an assignment can
be proposed manually, with no matcher run behind it at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from models.assignment import (
    Assignment,
    confirmed_assignment_missions,
    count_active_assignments,
    create_assignment,
    get_assignment,
    list_assignments_for_crew,
    list_assignments_for_org,
)
from models.enums import AssignmentStatus, Role
from models.mission import Mission, get_mission
from models.requirement import Requirement, get_requirement
from models.timestamps import utc_now
from models.user import User, get_user
from services.dates import windows_overlap


class MissionNotFoundError(Exception):
    """No mission with this id exists in the caller's org (-> 404, FR-1)."""


class RequirementNotFoundError(Exception):
    """No requirement with this id exists on this mission (-> 404)."""


class CrewMemberNotFoundError(Exception):
    """No ``crew_member``-role user with this id exists in the caller's org
    (-> 404, mirrors ``services.crew.get_crew_member``)."""


class HeadcountExceededError(Exception):
    """The requirement's headcount is already met by existing ``proposed``
    + ``confirmed`` assignments (-> 409, FR-14)."""

    def __init__(self, headcount: int) -> None:
        self.headcount = headcount
        super().__init__(f"Requirement headcount ({headcount}) is already filled")


class AssignmentNotFoundError(Exception):
    """No assignment with this id exists in the caller's org (-> 404, FR-1)."""


class NotAssignmentCrewMemberError(Exception):
    """Only the assignment's own named crew member may respond to it
    (-> 403, FR-15) — not their Director, not their Mission Lead."""


class InvalidAssignmentActionError(Exception):
    """``respond`` was called on an assignment that isn't ``proposed``
    anymore (-> 409) — it was already accepted or declined."""

    def __init__(self, current_status: AssignmentStatus) -> None:
        self.current_status = current_status
        super().__init__(f"Cannot respond to an assignment in {current_status.value!r} status")


class UnknownAssignmentActionError(Exception):
    """``action`` isn't ``accept``/``decline``. Only reachable by calling
    ``respond_to_assignment`` directly with a bad value — the route's own
    ``Literal["accept", "decline"]`` schema rejects anything else with a 422
    before this function ever runs."""

    def __init__(self, action: str) -> None:
        self.action = action
        super().__init__(f"Unknown assignment action: {action!r}")


class DoubleBookingError(Exception):
    """The crew member already holds a ``confirmed`` assignment on a
    different mission whose date range overlaps this one (-> 409, FR-16)."""

    def __init__(self, conflicting_mission: Mission) -> None:
        self.conflicting_mission = conflicting_mission
        super().__init__(
            f"Crew member already holds a confirmed assignment on mission "
            f"{conflicting_mission.id} ({conflicting_mission.name!r}) with overlapping dates"
        )


@dataclass(frozen=True)
class AssignmentView:
    """An assignment plus its mission id — the assignment row alone doesn't
    carry one (only ``requirement_id`` does), but callers (routes, the CLI)
    want it for display without a second round trip."""

    assignment: Assignment
    mission_id: int


def _to_view(session: Session, assignment: Assignment) -> AssignmentView:
    requirement = session.get(Requirement, assignment.requirement_id)
    assert requirement is not None  # assignments.requirement_id is an FK: always resolves
    return AssignmentView(assignment=assignment, mission_id=requirement.mission_id)


def propose_assignment(
    session: Session,
    org_id: int,
    proposer: User,
    *,
    mission_id: int,
    requirement_id: int,
    crew_id: int,
) -> AssignmentView:
    """A Mission Lead or Director proposes a crew member for a requirement
    (FR-14). Up to the requirement's headcount, counting existing
    ``proposed`` + ``confirmed`` assignments against it — proposing beyond
    that is rejected, not silently queued.

    Role gating (Mission Lead/Director only) happens at the route, mirroring
    ``services.mission.add_requirement``; this function only checks things
    that depend on the loaded mission/requirement/crew member.
    """
    mission = get_mission(session, org_id, mission_id)
    if mission is None:
        raise MissionNotFoundError
    assert mission.id is not None
    requirement = get_requirement(session, mission.id, requirement_id)
    if requirement is None:
        raise RequirementNotFoundError
    crew = get_user(session, org_id, crew_id)
    if crew is None or crew.role != Role.CREW_MEMBER:
        raise CrewMemberNotFoundError
    assert requirement.id is not None
    assert crew.id is not None
    assert proposer.id is not None
    if count_active_assignments(session, requirement.id) >= requirement.headcount:
        raise HeadcountExceededError(requirement.headcount)
    assignment = create_assignment(
        session, requirement_id=requirement.id, crew_id=crew.id, proposed_by=proposer.id
    )
    session.commit()
    session.refresh(assignment)
    return AssignmentView(assignment=assignment, mission_id=mission.id)


def _guard_against_double_booking(
    session: Session, assignment: Assignment, mission: Mission
) -> None:
    """FR-16: reject confirmation if the crew member already holds a
    ``confirmed`` assignment on a *different* mission with an overlapping
    date range. Independent of the matcher's own filtering (FR-13a) so it
    still fires for an assignment proposed manually, bypassing the matcher
    entirely."""
    assert mission.id is not None
    conflicts = confirmed_assignment_missions(
        session, assignment.crew_id, exclude_mission_id=mission.id
    )
    for conflicting_mission in conflicts:
        if windows_overlap(
            mission.start_date,
            mission.end_date,
            conflicting_mission.start_date,
            conflicting_mission.end_date,
        ):
            raise DoubleBookingError(conflicting_mission)


def respond_to_assignment(
    session: Session,
    org_id: int,
    actor: User,
    assignment_id: int,
    action: str,
) -> AssignmentView:
    """The named crew member accepts (-> ``confirmed``) or declines
    (-> ``declined``) a ``proposed`` assignment (FR-15).

    On decline, nothing else changes server-side beyond the status — the
    requirement's remaining headcount is recalculated by reading
    ``count_active_assignments`` fresh, never stored, so a subsequent
    ``propose`` immediately sees the reopened slot.

    On accept, the double-booking guard (FR-16) runs first; a conflict
    leaves the assignment's status untouched.
    """
    assignment = get_assignment(session, org_id, assignment_id)
    if assignment is None:
        raise AssignmentNotFoundError
    if actor.id != assignment.crew_id:
        raise NotAssignmentCrewMemberError
    if assignment.status != AssignmentStatus.PROPOSED:
        raise InvalidAssignmentActionError(assignment.status)

    requirement = session.get(Requirement, assignment.requirement_id)
    assert requirement is not None  # assignments.requirement_id is an FK: always resolves
    mission = session.get(Mission, requirement.mission_id)
    assert mission is not None  # requirements.mission_id is an FK: always resolves

    if action == "accept":
        _guard_against_double_booking(session, assignment, mission)
        assignment.status = AssignmentStatus.CONFIRMED
    elif action == "decline":
        assignment.status = AssignmentStatus.DECLINED
    else:
        raise UnknownAssignmentActionError(action)

    assignment.responded_at = utc_now()
    session.add(assignment)
    session.commit()
    session.refresh(assignment)
    assert mission.id is not None
    return AssignmentView(assignment=assignment, mission_id=mission.id)


def list_assignments(session: Session, org_id: int, caller: User) -> list[AssignmentView]:
    """Scoped to the caller's role (CLI ``assignment list``): a crew member
    sees only their own; Director/Lead see the whole org's (FR-14/FR-15)."""
    if caller.role == Role.CREW_MEMBER:
        assert caller.id is not None
        assignments = list_assignments_for_crew(session, org_id, caller.id)
    else:
        assignments = list_assignments_for_org(session, org_id)
    return [_to_view(session, assignment) for assignment in assignments]
