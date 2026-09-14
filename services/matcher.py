"""The matching engine: retrieval + ranking (T5, FR-13).

Given a mission requirement, find and rank eligible crew. Scope: the matcher
only — no assignment creation, no propose/accept/decline (that's T6).

Two independent stages, per the architecture explainer's "The matcher's
actual shape" card and ``docs/review/2026-09-14-mission-control-pattern-
review.md``'s Pipe and Filter recommendation:

* **Retrieval** (Pipe and Filter) — narrow an org's crew pool to those
  eligible for one requirement via three independent, unit-testable
  predicates (``HARD_FILTERS``), not one compound condition. Eligibility is
  ``all(check(...) for check in HARD_FILTERS)``.
* **Ranking** (Strategy) — score survivors via three independent, *pure*
  scoring functions (no DB access — each takes already-gathered values),
  combined at PRD §10 #9's fixed 50/30/20 weights. Every eligible candidate
  is returned, sorted by score descending — no top-N cap (FR-13c). Keeping
  the three component scores on each result (rather than discarding them
  after combining) is what makes the one-line factor breakdown fall out for
  free.

Availability-margin formula and cap (PRD leaves the exact shape open, §10
#9 only fixes the weights):

    nearest_constraint_gap_days = the fewest free days between the
    requirement's mission window and the closest edge of the crew's nearest
    constraint interval (an unavailability window, or another mission they
    hold a confirmed assignment on) -- 0 when the mission's window sits
    immediately adjacent to a constraint with no gap day between them, and
    the eligible candidate's constraints are known not to overlap the
    mission (retrieval already filtered those out).

    availability_margin = min(nearest_constraint_gap_days, CAP_DAYS) / CAP_DAYS

    -- 1.0 when the crew member has no constraints at all (maximum margin).
    CAP_DAYS = 30: past a month of slack, more slack doesn't meaningfully
    change how "safe" the assignment is, so the score saturates at 1.0
    rather than rewarding an arbitrarily distant constraint over a merely
    comfortable one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, select

from models.assignment import Assignment
from models.availability_window import list_availability_windows
from models.crew_skill import CrewSkill
from models.enums import AssignmentStatus
from models.mission import Mission, get_mission
from models.requirement import Requirement, get_requirement, list_requirements
from models.user import User, list_crew_members
from services.dates import windows_overlap

# --- weights + normalization constants (FR-13b, PRD §10 #9) ----------------

PROFICIENCY_WEIGHT = 0.5
WORKLOAD_WEIGHT = 0.3
AVAILABILITY_MARGIN_WEIGHT = 0.2

#: Proficiency is a 1-5 scale (PRD §10 Q1), so surplus (crew - minimum)
#: ranges 0-4 -- this is what normalizes it to 0-1.
PROFICIENCY_SURPLUS_RANGE = 4

#: See module docstring for the rationale behind this cap.
AVAILABILITY_MARGIN_CAP_DAYS = 30


class MissionNotFoundError(Exception):
    """No mission with this id exists in the caller's org (-> 404, FR-1)."""


class RequirementNotFoundError(Exception):
    """No requirement with this id exists on this mission (-> 404)."""


# --- retrieval stage: three independent hard-filter predicates (FR-13a) ----
#
# Pipe and Filter: each takes (session, crew, mission, requirement) and
# returns bool. None depends on another's result, so each is independently
# unit-testable with a minimal one-crew fixture.


def has_skill_at_proficiency(
    session: Session, crew: User, mission: Mission, requirement: Requirement
) -> bool:
    """Crew holds the requirement's skill at >= its min_proficiency."""
    assert crew.id is not None
    crew_skill = session.get(CrewSkill, (crew.id, requirement.skill_id))
    return crew_skill is not None and crew_skill.proficiency >= requirement.min_proficiency


def is_available_for_window(
    session: Session, crew: User, mission: Mission, requirement: Requirement
) -> bool:
    """No availability_window overlapping the mission's [start_date, end_date]."""
    assert crew.id is not None
    windows = list_availability_windows(session, crew.id)
    return not any(
        windows_overlap(mission.start_date, mission.end_date, window.start_date, window.end_date)
        for window in windows
    )


def has_no_conflicting_confirmed_assignment(
    session: Session, crew: User, mission: Mission, requirement: Requirement
) -> bool:
    """No *confirmed* assignment (on any other mission) with an overlapping
    date range.

    Assignments/confirmation don't exist yet (T6) — this is a real query
    against the real ``assignments``/``missions`` tables (mirrors T4's
    ``count_confirmed_assignments``), genuinely always ``True`` today because
    the table is empty, not a hardcoded placeholder. It starts enforcing the
    moment T6 creates confirmed assignments, with no change needed here.
    """
    assert crew.id is not None
    other_windows = _confirmed_assignment_windows(session, crew.id, exclude_mission_id=mission.id)
    return not any(
        windows_overlap(mission.start_date, mission.end_date, other_start, other_end)
        for other_start, other_end in other_windows
    )


HARD_FILTERS = (
    has_skill_at_proficiency,
    is_available_for_window,
    has_no_conflicting_confirmed_assignment,
)


def is_eligible(session: Session, crew: User, mission: Mission, requirement: Requirement) -> bool:
    """Eligibility = every hard filter passes (FR-13a)."""
    return all(check(session, crew, mission, requirement) for check in HARD_FILTERS)


def _confirmed_assignment_windows(
    session: Session, crew_id: int, *, exclude_mission_id: int | None = None
) -> list[tuple[date, date]]:
    """Every mission's [start_date, end_date] this crew member holds a
    *confirmed* assignment on, excluding ``exclude_mission_id`` (the mission
    currently being matched -- a crew member's own confirmed assignment on
    the requirement's own mission is not a "conflict")."""
    statement = (
        select(Mission.id, Mission.start_date, Mission.end_date)
        .select_from(Assignment)
        .join(Requirement, Requirement.id == Assignment.requirement_id)
        .join(Mission, Mission.id == Requirement.mission_id)
        .where(Assignment.crew_id == crew_id, Assignment.status == AssignmentStatus.CONFIRMED)
    )
    rows = session.exec(statement).all()
    return [(start, end) for mission_id, start, end in rows if mission_id != exclude_mission_id]


def _confirmed_assignment_count(session: Session, crew_id: int) -> int:
    """How many confirmed assignments (on any mission) this crew member
    currently holds -- the workload scoring factor's raw input."""
    statement = select(Assignment).where(
        Assignment.crew_id == crew_id, Assignment.status == AssignmentStatus.CONFIRMED
    )
    return len(session.exec(statement).all())


# --- ranking stage: three independent, pure scoring functions (FR-13b) -----
#
# Strategy: each factor is its own small pure function over already-gathered
# values (no session, no query) -- easy to unit-test with hand-picked
# numbers, and independently swappable if the formula ever needs to change.


def score_proficiency_surplus(crew_proficiency: int, min_proficiency: int) -> float:
    """(crew_proficiency - min_proficiency) / 4 -- surplus ranges 0-4 on the
    1-5 scale (FR-13b, PRD §10 #9)."""
    return (crew_proficiency - min_proficiency) / PROFICIENCY_SURPLUS_RANGE


def score_workload(confirmed_assignment_count: int) -> float:
    """1 / (1 + confirmed_assignment_count) -- fewer active confirmed
    assignments scores higher (FR-13b)."""
    return 1 / (1 + confirmed_assignment_count)


def score_availability_margin(
    nearest_constraint_gap_days: int | None,
    *,
    cap_days: int = AVAILABILITY_MARGIN_CAP_DAYS,
) -> float:
    """Slack between the crew's nearest constraint and the mission's window,
    normalized against ``cap_days`` (see module docstring for the exact
    formula and the cap chosen). ``None`` means the crew has no constraints
    at all -- maximum margin, score 1.0."""
    if nearest_constraint_gap_days is None:
        return 1.0
    clamped = max(0, min(nearest_constraint_gap_days, cap_days))
    return clamped / cap_days


def combined_score(
    proficiency_surplus: float, workload: float, availability_margin: float
) -> float:
    """The fixed 50/30/20 weighted combination (PRD §10 #9)."""
    return (
        PROFICIENCY_WEIGHT * proficiency_surplus
        + WORKLOAD_WEIGHT * workload
        + AVAILABILITY_MARGIN_WEIGHT * availability_margin
    )


def _gap_days(mission: Mission, other_start: date, other_end: date) -> int:
    """Free days between the mission's window and a non-overlapping
    constraint interval -- 0 when they're immediately adjacent (no free day
    between them). Assumes non-overlap (true for any eligible candidate,
    since retrieval already filtered overlapping constraints out); the
    overlapping branch below is a defensive fallback, not an expected path."""
    if other_start > mission.end_date:
        return (other_start - mission.end_date).days - 1
    if other_end < mission.start_date:
        return (mission.start_date - other_end).days - 1
    return 0


def _nearest_constraint_gap_days(session: Session, crew: User, mission: Mission) -> int | None:
    """The smallest gap (in days) between the mission's window and any of
    this crew member's constraint intervals (unavailability windows, plus
    other missions they hold a confirmed assignment on) -- ``None`` if they
    have no constraints at all."""
    assert crew.id is not None
    intervals = [(w.start_date, w.end_date) for w in list_availability_windows(session, crew.id)]
    intervals += _confirmed_assignment_windows(session, crew.id, exclude_mission_id=mission.id)
    if not intervals:
        return None
    return min(_gap_days(mission, start, end) for start, end in intervals)


@dataclass(frozen=True)
class MatchCandidate:
    """One eligible crew member for a requirement, ranked (FR-13c). The
    three component scores are kept alongside the combined ``score`` (not
    discarded after combining) so the breakdown falls out for free."""

    crew: User
    score: float
    proficiency_surplus_score: float
    workload_score: float
    availability_margin_score: float

    @property
    def breakdown(self) -> str:
        """One-line breakdown of which factors contributed (FR-13c) -- not
        just the combined number."""
        return (
            f"proficiency_surplus={self.proficiency_surplus_score:.2f}, "
            f"workload={self.workload_score:.2f}, "
            f"availability_margin={self.availability_margin_score:.2f}"
        )


@dataclass(frozen=True)
class RequirementMatch:
    requirement: Requirement
    candidates: list[MatchCandidate]


def match_requirement(
    session: Session, org_id: int, mission: Mission, requirement: Requirement
) -> list[MatchCandidate]:
    """Retrieve + rank every eligible crew member in the mission's org for
    one requirement. Every eligible candidate is returned, sorted by score
    descending -- no top-N cap (FR-13c)."""
    candidates: list[MatchCandidate] = []
    for crew in list_crew_members(session, org_id):
        if not is_eligible(session, crew, mission, requirement):
            continue
        assert crew.id is not None
        crew_skill = session.get(CrewSkill, (crew.id, requirement.skill_id))
        assert crew_skill is not None  # is_eligible already confirmed this holds

        proficiency_score = score_proficiency_surplus(
            crew_skill.proficiency, requirement.min_proficiency
        )
        workload_score = score_workload(_confirmed_assignment_count(session, crew.id))
        margin_score = score_availability_margin(
            _nearest_constraint_gap_days(session, crew, mission)
        )
        total = combined_score(proficiency_score, workload_score, margin_score)
        candidates.append(
            MatchCandidate(
                crew=crew,
                score=total,
                proficiency_surplus_score=proficiency_score,
                workload_score=workload_score,
                availability_margin_score=margin_score,
            )
        )
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return candidates


def _get_mission_or_raise(session: Session, org_id: int, mission_id: int) -> Mission:
    mission = get_mission(session, org_id, mission_id)
    if mission is None:
        raise MissionNotFoundError
    return mission


def match_mission(session: Session, org_id: int, mission_id: int) -> list[RequirementMatch]:
    """Run the matcher for every requirement on a mission -- the ``missionctl
    match run <mission>`` default (see ``cli/main.py``'s ``match run`` for
    the CLI-level choice this backs)."""
    mission = _get_mission_or_raise(session, org_id, mission_id)
    assert mission.id is not None
    return [
        RequirementMatch(
            requirement=requirement,
            candidates=match_requirement(session, org_id, mission, requirement),
        )
        for requirement in list_requirements(session, mission.id)
    ]


def match_single_requirement(
    session: Session, org_id: int, mission_id: int, requirement_id: int
) -> RequirementMatch:
    """Run the matcher for exactly one requirement on a mission (``missionctl
    match run <mission> --requirement <id>``)."""
    mission = _get_mission_or_raise(session, org_id, mission_id)
    assert mission.id is not None
    requirement = get_requirement(session, mission.id, requirement_id)
    if requirement is None:
        raise RequirementNotFoundError
    return RequirementMatch(
        requirement=requirement,
        candidates=match_requirement(session, org_id, mission, requirement),
    )
