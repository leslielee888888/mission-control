"""Mission lifecycle domain logic (T4, FR-8/FR-9/FR-10/FR-11/FR-12/FR-17).

The centerpiece is ``execute_mission_transition`` — one table-driven Command
executor for all six lifecycle actions (submit/approve/reject/activate/
complete/cancel), per the explicit recommendation in
``docs/review/2026-09-14-mission-control-pattern-review.md`` ("Command —
mission lifecycle actions"): six near-duplicate handler functions would let
a transition nobody remembered to guard slip through; one executor keyed off
a single ``ALLOWED_TRANSITIONS`` table can't drift out of sync with itself.

Split of responsibility with ``api/routes/mission.py`` (mirrors T3's
``services.crew`` / ``api/routes/crew.py`` split):

* Pure role gating ("must be a Director") is a static fact about the caller
  alone, expressed as ``Depends(require_role(...))`` at the route — no need
  to load a mission to know it.
* Anything that depends on the *loaded mission* — the creator-identity check
  behind FR-10's "only the creator" and FR-11's self-approval gate, the
  "requirement count" precondition, the "requirements are frozen outside
  draft" rule (PRD §10 Q12) — lives here, since only this layer has the row.

Every function starts from ``models.mission.get_mission(session, org_id,
...)`` for the same FR-1 reason ``services.crew`` starts from
``models.user.get_user``: a cross-org mission id must read back as "doesn't
exist," not "exists, but not yours."
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, select

from models.assignment import Assignment, AssignmentStatus
from models.enums import MissionStatus
from models.mission import Mission, get_mission, list_missions
from models.mission import create_mission as _create_mission
from models.requirement import (
    Requirement,
    list_requirements,
)
from models.requirement import (
    create_requirement as _create_requirement,
)
from models.skill import Skill, get_skill
from models.user import User


class MissionNotFoundError(Exception):
    """No mission with this id exists in the caller's org (-> 404, FR-1)."""


class RequirementSkillNotFoundError(Exception):
    """The requirement's skill id doesn't exist in the caller's org (-> 404)."""


class MissionNotEditableError(Exception):
    """Requirements can only be added while the mission is still ``draft`` —
    frozen once it leaves draft (-> 409, PRD §10 Q12)."""


class UnknownMissionActionError(Exception):
    """``action`` isn't one of the six lifecycle actions. Only reachable by
    calling ``execute_mission_transition`` directly with a bad value — every
    route passes one of its own literal, valid action strings."""

    def __init__(self, action: str) -> None:
        self.action = action
        super().__init__(f"Unknown mission action: {action!r}")


class InvalidMissionTransitionError(Exception):
    """``action`` isn't a legal transition from the mission's current status
    (-> 409, FR-9). The mission's status is left unchanged."""

    def __init__(self, current_status: MissionStatus, action: str) -> None:
        self.current_status = current_status
        self.action = action
        super().__init__(f"Cannot {action!r} a mission in {current_status.value!r} status")


class MissionHasNoRequirementsError(Exception):
    """``submit`` requires at least one requirement (-> 409, FR-10)."""


class NotMissionCreatorError(Exception):
    """Only the mission's creator may submit it (-> 403, FR-10)."""


class SelfApprovalError(Exception):
    """The mission's own creator may not approve or reject it, regardless of
    their role (-> 403, FR-11)."""


class MissingReasonError(Exception):
    """``reject`` requires a non-empty ``reason`` (-> 422, FR-11)."""


@dataclass(frozen=True)
class RequirementFulfillment:
    """One requirement plus its confirmed-vs-needed headcount (FR-17).

    ``confirmed`` counts real ``assignments`` rows with status
    ``confirmed`` — genuinely 0 today since T6 (assignments) doesn't exist
    yet, not a hardcoded placeholder, so the count starts working the moment
    T6 lands without this shape needing to change.
    """

    requirement: Requirement
    skill_name: str
    confirmed: int


@dataclass(frozen=True)
class MissionDetail:
    mission: Mission
    requirements: list[RequirementFulfillment]


def _get_mission_or_raise(session: Session, org_id: int, mission_id: int) -> Mission:
    mission = get_mission(session, org_id, mission_id)
    if mission is None:
        raise MissionNotFoundError
    return mission


def create_mission(
    session: Session,
    org_id: int,
    creator: User,
    *,
    name: str,
    description: str,
    start_date: date,
    end_date: date,
) -> Mission:
    """Mission Lead or Director creates a mission; starts in ``draft`` (FR-8).
    Role gating (Mission Lead/Director only) happens at the route via
    ``require_role`` — nothing here depends on a loaded mission yet."""
    assert creator.id is not None
    mission = _create_mission(
        session,
        org_id=org_id,
        created_by=creator.id,
        name=name,
        description=description,
        start_date=start_date,
        end_date=end_date,
    )
    session.commit()
    session.refresh(mission)
    return mission


def list_org_missions(session: Session, org_id: int) -> list[Mission]:
    return list_missions(session, org_id)


def count_confirmed_assignments(session: Session, requirement_id: int) -> int:
    """Confirmed-headcount half of FR-17. Always 0 until T6 creates
    ``assignments`` rows — a real (empty) query, not a stand-in constant."""
    statement = select(Assignment).where(
        Assignment.requirement_id == requirement_id,
        Assignment.status == AssignmentStatus.CONFIRMED,
    )
    return len(session.exec(statement).all())


def _to_fulfillment(session: Session, requirement: Requirement) -> RequirementFulfillment:
    skill = session.get(Skill, requirement.skill_id)
    assert skill is not None  # requirements.skill_id is an FK: always resolves
    assert requirement.id is not None
    confirmed = count_confirmed_assignments(session, requirement.id)
    return RequirementFulfillment(
        requirement=requirement, skill_name=skill.name, confirmed=confirmed
    )


def add_requirement(
    session: Session,
    org_id: int,
    mission_id: int,
    *,
    skill_id: int,
    min_proficiency: int,
    headcount: int,
) -> RequirementFulfillment:
    """Attach a requirement (skill, min proficiency, headcount) to a mission
    (FR-8) — only while it's still ``draft``; requirements are frozen once a
    mission leaves draft (PRD §10 Q12: reject back to draft first to edit)."""
    mission = _get_mission_or_raise(session, org_id, mission_id)
    if mission.status != MissionStatus.DRAFT:
        raise MissionNotEditableError
    skill = get_skill(session, org_id, skill_id)
    if skill is None:
        raise RequirementSkillNotFoundError
    assert mission.id is not None
    assert skill.id is not None
    requirement = _create_requirement(
        session,
        mission_id=mission.id,
        skill_id=skill.id,
        min_proficiency=min_proficiency,
        headcount=headcount,
    )
    session.commit()
    session.refresh(requirement)
    return _to_fulfillment(session, requirement)


def get_mission_detail(session: Session, org_id: int, mission_id: int) -> MissionDetail:
    """Mission plus every requirement's confirmed-vs-needed headcount (FR-17)."""
    mission = _get_mission_or_raise(session, org_id, mission_id)
    assert mission.id is not None
    requirements = list_requirements(session, mission.id)
    fulfillments = [_to_fulfillment(session, requirement) for requirement in requirements]
    return MissionDetail(mission=mission, requirements=fulfillments)


# --- the lifecycle Command executor (FR-9/FR-10/FR-11/FR-12) ---------------

#: FR-9's six states and seven transitions, as one literal table — the
#: single source of truth ``execute_mission_transition`` checks every action
#: against, per the explainer's "Table-driven state machine" card.
ALLOWED_TRANSITIONS: dict[MissionStatus, set[MissionStatus]] = {
    MissionStatus.DRAFT: {MissionStatus.PENDING_APPROVAL, MissionStatus.CANCELLED},
    MissionStatus.PENDING_APPROVAL: {
        MissionStatus.APPROVED,
        MissionStatus.DRAFT,
        MissionStatus.CANCELLED,
    },
    MissionStatus.APPROVED: {MissionStatus.ACTIVE, MissionStatus.CANCELLED},
    MissionStatus.ACTIVE: {MissionStatus.COMPLETED, MissionStatus.CANCELLED},
    MissionStatus.COMPLETED: set(),
    MissionStatus.CANCELLED: set(),
}

_Precondition = Callable[[Session, Mission, User, dict[str, object]], None]


def _check_submit(
    session: Session, mission: Mission, actor: User, payload: dict[str, object]
) -> None:
    if actor.id != mission.created_by:
        raise NotMissionCreatorError
    assert mission.id is not None
    if not list_requirements(session, mission.id):
        raise MissionHasNoRequirementsError


def _check_approve(
    session: Session, mission: Mission, actor: User, payload: dict[str, object]
) -> None:
    if actor.id == mission.created_by:
        raise SelfApprovalError


def _check_reject(
    session: Session, mission: Mission, actor: User, payload: dict[str, object]
) -> None:
    if actor.id == mission.created_by:
        raise SelfApprovalError
    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise MissingReasonError


def _no_precondition(
    session: Session, mission: Mission, actor: User, payload: dict[str, object]
) -> None:
    """activate/complete/cancel: role gating (Mission Lead/Director) already
    happened at the route; nothing about the loaded mission adds a further
    precondition."""


@dataclass(frozen=True)
class _ActionSpec:
    target_status: MissionStatus
    precondition: _Precondition


_ACTIONS: dict[str, _ActionSpec] = {
    "submit": _ActionSpec(MissionStatus.PENDING_APPROVAL, _check_submit),
    "approve": _ActionSpec(MissionStatus.APPROVED, _check_approve),
    "reject": _ActionSpec(MissionStatus.DRAFT, _check_reject),
    "activate": _ActionSpec(MissionStatus.ACTIVE, _no_precondition),
    "complete": _ActionSpec(MissionStatus.COMPLETED, _no_precondition),
    "cancel": _ActionSpec(MissionStatus.CANCELLED, _no_precondition),
}


def execute_mission_transition(
    session: Session,
    org_id: int,
    mission_id: int,
    actor: User,
    action: str,
    **payload: object,
) -> Mission:
    """The single Command executor for every lifecycle transition (FR-9,
    FR-10, FR-11, FR-12) — one function, not six near-duplicate handlers.

    1. Resolve the mission (org-scoped; -> ``MissionNotFoundError``/404).
    2. Look up ``action``'s target status and check it against
       ``ALLOWED_TRANSITIONS[mission.status]`` -> ``InvalidMissionTransitionError``
       /409, status left unchanged, if the transition isn't legal from here.
    3. Run the action's own precondition (creator-only for submit,
       self-approval gate for approve/reject, a required ``reason`` for
       reject) -> the matching typed exception on failure.
    4. Persist the new status.
    """
    mission = _get_mission_or_raise(session, org_id, mission_id)
    spec = _ACTIONS.get(action)
    if spec is None:
        raise UnknownMissionActionError(action)
    if spec.target_status not in ALLOWED_TRANSITIONS.get(mission.status, set()):
        raise InvalidMissionTransitionError(mission.status, action)
    spec.precondition(session, mission, actor, payload)
    mission.status = spec.target_status
    session.add(mission)
    session.commit()
    session.refresh(mission)
    return mission
