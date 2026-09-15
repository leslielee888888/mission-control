"""Demo seed data (T9, FR-19; scaled up T11).

Builds two tenant organisations end to end so the API/CLI/matcher can be
exercised immediately after a fresh checkout with no manual setup:

* **Northwind Disaster Response** — scaled way up (T11): 50 crew members, a
  Director + 3 Mission Leads, the original 6-skill taxonomy, and 10 missions
  spread across all 6 FR-9 lifecycle states with real confirmed assignments
  behind the active/completed ones.
* **Beacon Relief Network** — left at T9's original, smaller scale (Director
  + 2 Mission Leads, 6 crew, 3 missions) on purpose: a 50-crew org next to a
  ~6-crew org is a more convincing demonstration that tenant isolation (FR-1)
  holds regardless of org size than two similarly-sized orgs would be. FR-19
  only requires >=2 orgs; this keeps that contrast rather than scaling both.

Goes straight through the ``services`` layer (not HTTP), the same domain
functions ``api/routes`` call, rather than duplicating their rules (skill
uniqueness, overlap checking, the lifecycle Command executor, the headcount
ceiling, ...). That's a deliberate exception to FR-18 ("no command reads the
database directly") — FR-18 is about ``missionctl``, a separate HTTP client;
this script is what puts data behind the API in the first place, same as a
migration or fixture loader would.

Run with ``python -m scripts.seed`` (see README.md). Re-running starts from a
truly empty database: the default SQLite file is deleted first (documented in
README), so this is "fresh file per run," not incremental/idempotent upsert —
sufficient per FR-19 and simpler than reconciling unique-constraint collisions
on every rerun. (The Docker entrypoint, ``docker/entrypoint.sh``, guards the
*container's* db file against that reset by only ever running this script
once, on first start — see that file.)
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlmodel import Session

from models.database import create_db_and_tables, engine, get_database_url
from models.enums import Role
from models.organization import Organization
from models.skill import Skill, list_skills
from models.user import User
from services.assignment import propose_assignment, respond_to_assignment
from services.auth import hash_password
from services.crew import add_availability_window, create_org_skill, set_crew_skill_proficiency
from services.mission import add_requirement, create_mission, execute_mission_transition

#: Where demo credentials are written (gitignored — see README.md). Also
#: printed to stdout on every run.
CREDENTIALS_FILE = Path(__file__).resolve().parent.parent / "seed_credentials.txt"


@dataclass(frozen=True)
class SeededCredential:
    """One demo user's login, plus the plaintext password used to create
    them (never otherwise recoverable once ``User.password_hash`` is set)."""

    org: str
    role: str
    name: str
    email: str
    password: str


def _reset_database_file() -> None:
    """Delete any existing default SQLite file before seeding.

    Re-running this script against a leftover file would collide on unique
    constraints (``users.email``, org-scoped skill names) partway through —
    a fresh file per run (documented in README.md) sidesteps that instead of
    reconciling it.  A non-default ``MISSION_CONTROL_DATABASE_URL`` (e.g. a
    non-SQLite URL) is left untouched.
    """
    url = get_database_url()
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        return
    db_path = Path(url[len(prefix) :])
    if db_path.exists():
        db_path.unlink()


#: Every seeded demo user gets this same password. Deliberately static, not
#: per-user or randomly generated — the seed script runs independently on
#: every machine (local checkout, CI, the NAS), and a randomly generated
#: password was different every time, which was a real source of login
#: confusion (a NAS user's password never matched what a local checkout's
#: ``seed_credentials.txt`` showed, or the reverse). One fixed password for
#: every demo user means no lookup is ever needed, on any environment, for
#: any user — reasonable for pure demo/test data (§8's threat model doesn't
#: cover it) where interchangeability matters more than per-user secrecy.
DEMO_PASSWORD = "MissionControl2026!"


def _demo_password(email: str) -> str:
    """Return the shared demo password (see ``DEMO_PASSWORD``).

    Still takes ``email`` — kept as the extension point if a future need
    (e.g. per-user secrecy again) brings back a derived password; every
    call site already passes the email so that wouldn't ripple out.
    """
    del email  # unused: every demo user shares DEMO_PASSWORD
    return DEMO_PASSWORD


def _new_user(
    session: Session,
    *,
    org: Organization,
    role: Role,
    name: str,
    email: str,
    credentials: list[SeededCredential],
) -> User:
    """Create one login with the shared demo password (see
    ``DEMO_PASSWORD``), recording it in ``credentials`` for the end-of-run
    report (§10 #24 — real, usable passwords, not blank ones)."""
    assert org.id is not None
    password = _demo_password(email)
    user = User(
        org_id=org.id,
        email=email,
        password_hash=hash_password(password),
        role=role,
        name=name,
    )
    session.add(user)
    session.flush()
    assert user.id is not None
    credentials.append(
        SeededCredential(org=org.name, role=role.value, name=name, email=email, password=password)
    )
    return user


def _build_skill_taxonomy(
    session: Session, org: Organization, taxonomy: list[tuple[str, str]]
) -> dict[str, Skill]:
    """Create an org-scoped skill taxonomy (FR-5); returns name -> Skill."""
    assert org.id is not None
    return {name: create_org_skill(session, org.id, name, category) for name, category in taxonomy}


def _build_crew_member(
    session: Session,
    *,
    org: Organization,
    name: str,
    email: str,
    skills: dict[str, int],
    unavailability: list[tuple[date, date]],
    credentials: list[SeededCredential],
) -> User:
    """Create one crew member plus their skill proficiencies (FR-6) and
    unavailability windows (FR-7) — varied per person, not identical clones."""
    assert org.id is not None
    crew = _new_user(
        session, org=org, role=Role.CREW_MEMBER, name=name, email=email, credentials=credentials
    )
    assert crew.id is not None
    for skill_name, proficiency in skills.items():
        set_crew_skill_proficiency(session, org.id, crew.id, skill_name, proficiency)
    for start, end in unavailability:
        add_availability_window(session, org.id, crew.id, start, end)
    return crew


def _confirm_assignment(
    session: Session,
    org_id: int,
    proposer: User,
    *,
    mission_id: int,
    requirement_id: int,
    crew: User,
) -> None:
    """Propose then immediately accept — every confirmed demo assignment
    goes through the real ``services.assignment`` propose/accept pair (T6),
    never a direct row insert, so workload scoring (FR-13b) has genuine
    ``confirmed`` rows behind it."""
    assert crew.id is not None
    proposal = propose_assignment(
        session,
        org_id,
        proposer,
        mission_id=mission_id,
        requirement_id=requirement_id,
        crew_id=crew.id,
    )
    assert proposal.assignment.id is not None
    respond_to_assignment(session, org_id, crew, proposal.assignment.id, "accept")


# --- Org A: Northwind Disaster Response --------------------------------------
#
# T11 scale: 50 crew, a Director + 3 Mission Leads, the original 6-skill
# taxonomy (still plenty of variety at this headcount), and 10 missions
# spread across all 6 FR-9 lifecycle states.
#
# Crew are built in two groups:
#
# * A ~10-person "storyline" roster (explicit, named, commented) that carries
#   every specific demo purpose below — the matcher's proficiency and
#   availability hard filters (FR-13a), and the crew actually proposed and
#   confirmed onto the active/completed missions.
# * A ~40-person "filler" roster, generated from two small name-part lists so
#   the org reads as genuinely 50-strong without 40 more hand-typed literals.
#   Skills/proficiencies cycle deterministically by index (not random) so a
#   rerun is reproducible byte-for-byte; a spaced-out slice of them also gets
#   an availability window, so the ~15-20% minority the matcher's hard filter
#   has real exclusions to show isn't limited to the two storyline examples.

NORTHWIND_SKILL_TAXONOMY = [
    ("Wilderness First Aid", "medical"),
    ("Swift-Water Rescue", "rescue"),
    ("Chainsaw Operation", "rescue"),
    ("Incident Command", "leadership"),
    ("Drone Piloting", "recon"),
    ("Logistics Coordination", "logistics"),
]

#: Every mission's (start, end) date, keyed by the short name used below for
#: both mission creation and (for the still-open missions) the pool of
#: windows handed to a slice of the filler crew's unavailability — one
#: source of truth instead of the same literal dates typed twice.
NORTHWIND_MISSION_WINDOWS: dict[str, tuple[date, date]] = {
    # Past-dated: already wrapped up before "today" (2026-09-15).
    "summer_wildfire": (date(2026, 8, 1), date(2026, 8, 10)),
    "debris": (date(2026, 8, 20), date(2026, 8, 25)),
    # Spanning "today": in progress right now.
    "coastal": (date(2026, 9, 10), date(2026, 9, 20)),
    "avalanche": (date(2026, 9, 12), date(2026, 9, 22)),
    # Future-dated: still being planned/approved, or called off before they
    # got there.
    "evacuation": (date(2026, 9, 25), date(2026, 10, 2)),
    "flood": (date(2026, 10, 5), date(2026, 10, 12)),
    "ridgeline": (date(2026, 10, 8), date(2026, 10, 14)),
    "wildfire": (date(2026, 10, 20), date(2026, 10, 28)),
    "rockslide": (date(2026, 11, 2), date(2026, 11, 6)),
    "blackout": (date(2026, 11, 10), date(2026, 11, 16)),
}

#: The still-open (non-active, non-completed) missions' windows, cycled
#: across the filler crew who get an availability window — so the matcher's
#: availability hard filter has exclusions to show on more than just the two
#: storyline examples (Jordan, Taylor) below.
_FILLER_WINDOW_POOL = [
    NORTHWIND_MISSION_WINDOWS[key]
    for key in ("flood", "ridgeline", "wildfire", "rockslide", "blackout", "evacuation")
]

_FILLER_FIRST_NAMES = [
    "Harper",
    "Rowan",
    "Skyler",
    "Emerson",
    "Dakota",
    "Finley",
    "Reese",
    "Marlowe",
]
_FILLER_LAST_NAMES = ["Whitaker", "Delgado", "Kowalski", "Iverson", "Mbeki"]


def _build_northwind_storyline_crew(
    session: Session, org: Organization, credentials: list[SeededCredential]
) -> dict[str, User]:
    """The ~10 named crew every demo below reads by key — carried over from
    T9 where it still applies, extended for T11's larger active/completed
    missions."""
    return {
        "sam": _build_crew_member(
            session,
            org=org,
            name="Sam Rivera",
            email="sam.rivera@northwind.demo",
            skills={"Wilderness First Aid": 5, "Swift-Water Rescue": 3, "Incident Command": 2},
            unavailability=[],
            credentials=credentials,
        ),
        # Meets Highland Wildfire Support's proficiency bar (Wilderness First
        # Aid >= 3) but is unavailable across its exact dates -- demonstrates
        # the matcher's availability hard-filter excluding an otherwise-
        # qualified candidate (FR-13a). Separately, also the crew member
        # confirmed onto Coastal Storm Recovery's Incident Command slot --
        # two independent demo purposes on one person, same as T9.
        "jordan": _build_crew_member(
            session,
            org=org,
            name="Jordan Blake",
            email="jordan.blake@northwind.demo",
            skills={"Wilderness First Aid": 3, "Incident Command": 4, "Drone Piloting": 5},
            unavailability=[(date(2026, 10, 22), date(2026, 10, 25))],
            credentials=credentials,
        ),
        "casey": _build_crew_member(
            session,
            org=org,
            name="Casey Nguyen",
            email="casey.nguyen@northwind.demo",
            skills={"Swift-Water Rescue": 5, "Wilderness First Aid": 4, "Chainsaw Operation": 2},
            unavailability=[],
            credentials=credentials,
        ),
        # Chainsaw Operation and Logistics Coordination both meet real
        # requirement bars this time (Summer Wildfire Containment, Metro
        # Blackout Support) -- the Nov 15-30 window now genuinely overlaps
        # Metro Blackout Support's Nov 10-16 dates, so Taylor shows up
        # skill-eligible for that requirement yet excluded by availability
        # (FR-13a), the same shape as Jordan's demo above.
        "taylor": _build_crew_member(
            session,
            org=org,
            name="Taylor Morgan",
            email="taylor.morgan@northwind.demo",
            skills={"Chainsaw Operation": 5, "Logistics Coordination": 3},
            unavailability=[(date(2026, 11, 15), date(2026, 11, 30))],
            credentials=credentials,
        ),
        "riley": _build_crew_member(
            session,
            org=org,
            name="Riley Ortiz",
            email="riley.ortiz@northwind.demo",
            skills={"Incident Command": 3, "Drone Piloting": 2, "Wilderness First Aid": 2},
            unavailability=[],
            credentials=credentials,
        ),
        "avery": _build_crew_member(
            session,
            org=org,
            name="Avery Kim",
            email="avery.kim@northwind.demo",
            skills={"Logistics Coordination": 5, "Swift-Water Rescue": 2},
            unavailability=[],
            credentials=credentials,
        ),
        # Below every requirement's minimum proficiency it could apply to
        # across all 10 missions (every Wilderness First Aid bar is >= 2,
        # every Chainsaw Operation bar is >= 2) -- demonstrates the
        # matcher's proficiency hard-filter excluding a crew member who
        # holds the skill but not at the bar (FR-13a).
        "jamie": _build_crew_member(
            session,
            org=org,
            name="Jamie Fox",
            email="jamie.fox@northwind.demo",
            skills={"Wilderness First Aid": 1, "Chainsaw Operation": 1},
            unavailability=[],
            credentials=credentials,
        ),
        # Confirmed onto Mountain Pass Avalanche Response's second
        # Wilderness First Aid slot, alongside Sam.
        "quinn": _build_crew_member(
            session,
            org=org,
            name="Quinn Ellis",
            email="quinn.ellis@northwind.demo",
            skills={"Wilderness First Aid": 4, "Drone Piloting": 2},
            unavailability=[],
            credentials=credentials,
        ),
        # Confirmed onto Late-Summer Debris Clearance's Chainsaw Operation
        # requirement, alongside Elliot.
        "nadia": _build_crew_member(
            session,
            org=org,
            name="Nadia Osei",
            email="nadia.osei@northwind.demo",
            skills={"Chainsaw Operation": 3, "Incident Command": 2},
            unavailability=[],
            credentials=credentials,
        ),
        "elliot": _build_crew_member(
            session,
            org=org,
            name="Elliot Park",
            email="elliot.park@northwind.demo",
            skills={"Chainsaw Operation": 4, "Logistics Coordination": 2},
            unavailability=[],
            credentials=credentials,
        ),
    }


def _build_northwind_filler_crew(
    session: Session, org: Organization, credentials: list[SeededCredential]
) -> int:
    """40 more crew members generated from two short name-part lists (8 x 5
    = 40 unique pairs, deterministic order via ``itertools.product`` -- no
    two collide, and nothing here depends on a random seed).

    Skills and proficiencies cycle by index so every person's mix is
    genuinely different from their neighbours' without needing 40 more
    hand-typed literals; a spaced-out slice (every 6th) also gets an
    unavailability window pulled from ``_FILLER_WINDOW_POOL`` so the
    minority-with-a-window (~15-20% of the full 50, combined with Jordan and
    Taylor above) isn't only the two storyline examples.

    Returns the count built, for the run-summary print.
    """
    skill_names = [name for name, _category in NORTHWIND_SKILL_TAXONOMY]
    name_pairs = list(itertools.product(_FILLER_FIRST_NAMES, _FILLER_LAST_NAMES))
    assert len(name_pairs) == 40

    for index, (first, last) in enumerate(name_pairs):
        skill_count = 1 + (index % 3)  # 1, 2, or 3 skills -- cycles every 3 people
        start = index % len(skill_names)
        chosen = [skill_names[(start + offset) % len(skill_names)] for offset in range(skill_count)]
        skills = {name: 1 + ((index * 2 + offset * 3) % 5) for offset, name in enumerate(chosen)}

        unavailability: list[tuple[date, date]] = []
        if index % 6 == 0:
            pool_index = (index // 6) % len(_FILLER_WINDOW_POOL)
            unavailability = [_FILLER_WINDOW_POOL[pool_index]]

        _build_crew_member(
            session,
            org=org,
            name=f"{first} {last}",
            email=f"{first.lower()}.{last.lower()}@northwind.demo",
            skills=skills,
            unavailability=unavailability,
            credentials=credentials,
        )
    return len(name_pairs)


def _seed_northwind(session: Session, credentials: list[SeededCredential]) -> None:
    org = Organization(name="Northwind Disaster Response")
    session.add(org)
    session.flush()
    assert org.id is not None

    director = _new_user(
        session,
        org=org,
        role=Role.DIRECTOR,
        name="Dana Whitfield",
        email="director.dana@northwind.demo",
        credentials=credentials,
    )
    marcus = _new_user(
        session,
        org=org,
        role=Role.MISSION_LEAD,
        name="Marcus Chen",
        email="lead.marcus@northwind.demo",
        credentials=credentials,
    )
    priya = _new_user(
        session,
        org=org,
        role=Role.MISSION_LEAD,
        name="Priya Anand",
        email="lead.priya@northwind.demo",
        credentials=credentials,
    )
    # A 3rd Mission Lead -- at 50 crew and 10 concurrent-ish missions, two
    # leads carrying every mission reads thin; a third spreads ownership the
    # way an org actually this size would.
    devon = _new_user(
        session,
        org=org,
        role=Role.MISSION_LEAD,
        name="Devon Okafor",
        email="lead.devon@northwind.demo",
        credentials=credentials,
    )

    _build_skill_taxonomy(session, org, NORTHWIND_SKILL_TAXONOMY)

    crew = _build_northwind_storyline_crew(session, org, credentials)
    filler_count = _build_northwind_filler_crew(session, org, credentials)
    assert len(crew) + filler_count == 50

    skills_by_name = {skill.name: skill for skill in list_skills(session, org.id)}
    windows = NORTHWIND_MISSION_WINDOWS

    # --- Mission 1: draft -- a requirement attached, never submitted. ------
    flood = create_mission(
        session,
        org.id,
        marcus,
        name="Riverside Flood Response",
        description="Swift-water rescue support for rising river levels near the county line.",
        start_date=windows["flood"][0],
        end_date=windows["flood"][1],
    )
    assert flood.id is not None
    add_requirement(
        session,
        org.id,
        flood.id,
        skill_id=_skill_id(skills_by_name, "Swift-Water Rescue"),
        min_proficiency=3,
        headcount=2,
    )

    # --- Mission 2: draft -- a second draft, different skill mix. ----------
    ridgeline = create_mission(
        session,
        org.id,
        devon,
        name="Ridgeline Search and Rescue",
        description="Locate and recover hikers stranded above the tree line after an early storm.",
        start_date=windows["ridgeline"][0],
        end_date=windows["ridgeline"][1],
    )
    assert ridgeline.id is not None
    add_requirement(
        session,
        org.id,
        ridgeline.id,
        skill_id=_skill_id(skills_by_name, "Wilderness First Aid"),
        min_proficiency=2,
        headcount=1,
    )
    add_requirement(
        session,
        org.id,
        ridgeline.id,
        skill_id=_skill_id(skills_by_name, "Drone Piloting"),
        min_proficiency=3,
        headcount=1,
    )

    # --- Mission 3: pending_approval -- submitted, awaiting the Director. --
    wildfire = create_mission(
        session,
        org.id,
        priya,
        name="Highland Wildfire Support",
        description="Evacuation and containment support for the Highland Ridge wildfire.",
        start_date=windows["wildfire"][0],
        end_date=windows["wildfire"][1],
    )
    assert wildfire.id is not None
    add_requirement(
        session,
        org.id,
        wildfire.id,
        skill_id=_skill_id(skills_by_name, "Wilderness First Aid"),
        min_proficiency=3,
        headcount=2,
    )
    add_requirement(
        session,
        org.id,
        wildfire.id,
        skill_id=_skill_id(skills_by_name, "Chainsaw Operation"),
        min_proficiency=3,
        headcount=1,
    )
    execute_mission_transition(session, org.id, wildfire.id, priya, "submit")

    # --- Mission 4: approved -- through the gate, not yet activated. -------
    rockslide = create_mission(
        session,
        org.id,
        marcus,
        name="Canyon Rockslide Response",
        description="Clear a rockslide blocking the only access road into Canyon Pines.",
        start_date=windows["rockslide"][0],
        end_date=windows["rockslide"][1],
    )
    assert rockslide.id is not None
    add_requirement(
        session,
        org.id,
        rockslide.id,
        skill_id=_skill_id(skills_by_name, "Chainsaw Operation"),
        min_proficiency=2,
        headcount=1,
    )
    add_requirement(
        session,
        org.id,
        rockslide.id,
        skill_id=_skill_id(skills_by_name, "Incident Command"),
        min_proficiency=2,
        headcount=1,
    )
    execute_mission_transition(session, org.id, rockslide.id, marcus, "submit")
    execute_mission_transition(session, org.id, rockslide.id, director, "approve")

    # --- Mission 5: approved -- a second one, different skill mix. ---------
    blackout = create_mission(
        session,
        org.id,
        priya,
        name="Metro Blackout Support",
        description="Logistics and aerial assessment support during the multi-day metro blackout.",
        start_date=windows["blackout"][0],
        end_date=windows["blackout"][1],
    )
    assert blackout.id is not None
    add_requirement(
        session,
        org.id,
        blackout.id,
        skill_id=_skill_id(skills_by_name, "Logistics Coordination"),
        min_proficiency=3,
        headcount=2,
    )
    add_requirement(
        session,
        org.id,
        blackout.id,
        skill_id=_skill_id(skills_by_name, "Drone Piloting"),
        min_proficiency=2,
        headcount=1,
    )
    execute_mission_transition(session, org.id, blackout.id, priya, "submit")
    execute_mission_transition(session, org.id, blackout.id, director, "approve")

    # --- Mission 6: active, deliberately short-staffed on one requirement --
    # -- FR-17 ("under-staffing doesn't block activation"), same shape T9
    # demonstrated on Coastal Storm Recovery.
    coastal = create_mission(
        session,
        org.id,
        marcus,
        name="Coastal Storm Recovery",
        description="Debris clearance and incident command for the coastal storm aftermath.",
        start_date=windows["coastal"][0],
        end_date=windows["coastal"][1],
    )
    assert coastal.id is not None
    ic_requirement = add_requirement(
        session,
        org.id,
        coastal.id,
        skill_id=_skill_id(skills_by_name, "Incident Command"),
        min_proficiency=2,
        headcount=1,
    )
    add_requirement(
        session,
        org.id,
        coastal.id,
        skill_id=_skill_id(skills_by_name, "Logistics Coordination"),
        min_proficiency=2,
        headcount=1,
    )
    execute_mission_transition(session, org.id, coastal.id, marcus, "submit")
    execute_mission_transition(session, org.id, coastal.id, director, "approve")
    execute_mission_transition(session, org.id, coastal.id, marcus, "activate")
    assert ic_requirement.requirement.id is not None
    _confirm_assignment(
        session,
        org.id,
        marcus,
        mission_id=coastal.id,
        requirement_id=ic_requirement.requirement.id,
        crew=crew["jordan"],
    )
    # Logistics Coordination is left unfilled on purpose (see above).

    # --- Mission 7: active, fully staffed -- workload scoring (FR-13b) has
    # real confirmed assignments behind it, not just Mission 6's one.
    avalanche = create_mission(
        session,
        org.id,
        priya,
        name="Mountain Pass Avalanche Response",
        description="Search, medical, and swift-water support after the mountain pass avalanche.",
        start_date=windows["avalanche"][0],
        end_date=windows["avalanche"][1],
    )
    assert avalanche.id is not None
    wfa_requirement = add_requirement(
        session,
        org.id,
        avalanche.id,
        skill_id=_skill_id(skills_by_name, "Wilderness First Aid"),
        min_proficiency=3,
        headcount=2,
    )
    swr_requirement = add_requirement(
        session,
        org.id,
        avalanche.id,
        skill_id=_skill_id(skills_by_name, "Swift-Water Rescue"),
        min_proficiency=2,
        headcount=1,
    )
    execute_mission_transition(session, org.id, avalanche.id, priya, "submit")
    execute_mission_transition(session, org.id, avalanche.id, director, "approve")
    execute_mission_transition(session, org.id, avalanche.id, priya, "activate")
    assert wfa_requirement.requirement.id is not None
    assert swr_requirement.requirement.id is not None
    _confirm_assignment(
        session,
        org.id,
        priya,
        mission_id=avalanche.id,
        requirement_id=wfa_requirement.requirement.id,
        crew=crew["sam"],
    )
    _confirm_assignment(
        session,
        org.id,
        priya,
        mission_id=avalanche.id,
        requirement_id=wfa_requirement.requirement.id,
        crew=crew["quinn"],
    )
    _confirm_assignment(
        session,
        org.id,
        priya,
        mission_id=avalanche.id,
        requirement_id=swr_requirement.requirement.id,
        crew=crew["casey"],
    )

    # --- Mission 8: completed -- the full happy-path lifecycle, fully
    # staffed, dated before "today" so it genuinely reads as wrapped up.
    summer_wildfire = create_mission(
        session,
        org.id,
        marcus,
        name="Summer Wildfire Containment",
        description="Containment line support and incident command for the early-season wildfire.",
        start_date=windows["summer_wildfire"][0],
        end_date=windows["summer_wildfire"][1],
    )
    assert summer_wildfire.id is not None
    swf_ic_requirement = add_requirement(
        session,
        org.id,
        summer_wildfire.id,
        skill_id=_skill_id(skills_by_name, "Incident Command"),
        min_proficiency=3,
        headcount=1,
    )
    swf_chainsaw_requirement = add_requirement(
        session,
        org.id,
        summer_wildfire.id,
        skill_id=_skill_id(skills_by_name, "Chainsaw Operation"),
        min_proficiency=3,
        headcount=1,
    )
    execute_mission_transition(session, org.id, summer_wildfire.id, marcus, "submit")
    execute_mission_transition(session, org.id, summer_wildfire.id, director, "approve")
    execute_mission_transition(session, org.id, summer_wildfire.id, marcus, "activate")
    assert swf_ic_requirement.requirement.id is not None
    assert swf_chainsaw_requirement.requirement.id is not None
    _confirm_assignment(
        session,
        org.id,
        marcus,
        mission_id=summer_wildfire.id,
        requirement_id=swf_ic_requirement.requirement.id,
        crew=crew["riley"],
    )
    _confirm_assignment(
        session,
        org.id,
        marcus,
        mission_id=summer_wildfire.id,
        requirement_id=swf_chainsaw_requirement.requirement.id,
        crew=crew["taylor"],
    )
    execute_mission_transition(session, org.id, summer_wildfire.id, marcus, "complete")

    # --- Mission 9: completed -- a second one, single two-headcount
    # requirement (variety in requirement shape, not just skill/threshold).
    debris = create_mission(
        session,
        org.id,
        priya,
        name="Late-Summer Debris Clearance",
        description="Clear fallen timber from the regional access roads before the fall season.",
        start_date=windows["debris"][0],
        end_date=windows["debris"][1],
    )
    assert debris.id is not None
    debris_requirement = add_requirement(
        session,
        org.id,
        debris.id,
        skill_id=_skill_id(skills_by_name, "Chainsaw Operation"),
        min_proficiency=2,
        headcount=2,
    )
    execute_mission_transition(session, org.id, debris.id, priya, "submit")
    execute_mission_transition(session, org.id, debris.id, director, "approve")
    execute_mission_transition(session, org.id, debris.id, priya, "activate")
    assert debris_requirement.requirement.id is not None
    _confirm_assignment(
        session,
        org.id,
        priya,
        mission_id=debris.id,
        requirement_id=debris_requirement.requirement.id,
        crew=crew["nadia"],
    )
    _confirm_assignment(
        session,
        org.id,
        priya,
        mission_id=debris.id,
        requirement_id=debris_requirement.requirement.id,
        crew=crew["elliot"],
    )
    execute_mission_transition(session, org.id, debris.id, priya, "complete")

    # --- Mission 10: cancelled -- approved, then called off (FR-9's 6th
    # state, not otherwise reachable from the other 9 missions above).
    evacuation = create_mission(
        session,
        org.id,
        devon,
        name="River Valley Wildfire Evacuation",
        description="Pre-emptive evacuation support for the river valley ahead of the fire line.",
        start_date=windows["evacuation"][0],
        end_date=windows["evacuation"][1],
    )
    assert evacuation.id is not None
    add_requirement(
        session,
        org.id,
        evacuation.id,
        skill_id=_skill_id(skills_by_name, "Wilderness First Aid"),
        min_proficiency=2,
        headcount=2,
    )
    add_requirement(
        session,
        org.id,
        evacuation.id,
        skill_id=_skill_id(skills_by_name, "Incident Command"),
        min_proficiency=2,
        headcount=1,
    )
    execute_mission_transition(session, org.id, evacuation.id, devon, "submit")
    execute_mission_transition(session, org.id, evacuation.id, director, "approve")
    execute_mission_transition(session, org.id, evacuation.id, devon, "cancel")


# --- Org B: Beacon Relief Network --------------------------------------------
#
# T11 leaves this at T9's original scale on purpose -- see the module
# docstring. Not touched below.


def _seed_beacon(session: Session, credentials: list[SeededCredential]) -> None:
    org = Organization(name="Beacon Relief Network")
    session.add(org)
    session.flush()
    assert org.id is not None

    director = _new_user(
        session,
        org=org,
        role=Role.DIRECTOR,
        name="Elena Vasquez",
        email="director.elena@beacon.demo",
        credentials=credentials,
    )
    omar = _new_user(
        session,
        org=org,
        role=Role.MISSION_LEAD,
        name="Omar Farouk",
        email="lead.omar@beacon.demo",
        credentials=credentials,
    )
    grace = _new_user(
        session,
        org=org,
        role=Role.MISSION_LEAD,
        name="Grace Liu",
        email="lead.grace@beacon.demo",
        credentials=credentials,
    )

    # Deliberately a different taxonomy from Northwind's -- same org-scoped
    # skill *names* would be free to collide (FR-5) but these don't even
    # overlap, underscoring that skill sets are genuinely per-org.
    _build_skill_taxonomy(
        session,
        org,
        [
            ("Community Outreach", "community"),
            ("Bilingual Translation", "communication"),
            ("Warehouse Management", "logistics"),
            ("Mental Health First Aid", "medical"),
            ("Water Purification", "field"),
            ("Supply Chain Logistics", "logistics"),
        ],
    )

    crew = {
        "noah": _build_crew_member(
            session,
            org=org,
            name="Noah Bennett",
            email="noah.bennett@beacon.demo",
            skills={"Community Outreach": 4, "Warehouse Management": 3},
            unavailability=[],
            credentials=credentials,
        ),
        "maya": _build_crew_member(
            session,
            org=org,
            name="Maya Patel",
            email="maya.patel@beacon.demo",
            skills={"Bilingual Translation": 5, "Mental Health First Aid": 4},
            unavailability=[(date(2026, 12, 1), date(2026, 12, 5))],
            credentials=credentials,
        ),
        "liam": _build_crew_member(
            session,
            org=org,
            name="Liam O'Connor",
            email="liam.oconnor@beacon.demo",
            skills={"Water Purification": 5, "Supply Chain Logistics": 3},
            unavailability=[],
            credentials=credentials,
        ),
        "sofia": _build_crew_member(
            session,
            org=org,
            name="Sofia Rossi",
            email="sofia.rossi@beacon.demo",
            skills={"Community Outreach": 3, "Mental Health First Aid": 5},
            unavailability=[],
            credentials=credentials,
        ),
        "ethan": _build_crew_member(
            session,
            org=org,
            name="Ethan Park",
            email="ethan.park@beacon.demo",
            skills={"Warehouse Management": 5, "Supply Chain Logistics": 4},
            unavailability=[(date(2026, 11, 20), date(2026, 11, 25))],
            credentials=credentials,
        ),
        "zara": _build_crew_member(
            session,
            org=org,
            name="Zara Ahmed",
            email="zara.ahmed@beacon.demo",
            skills={"Bilingual Translation": 4, "Water Purification": 2},
            unavailability=[],
            credentials=credentials,
        ),
    }

    skills_by_name = {skill.name: skill for skill in list_skills(session, org.id)}

    # Mission 4: draft -- a requirement attached, never submitted.
    shelter = create_mission(
        session,
        org.id,
        omar,
        name="Downtown Shelter Setup",
        description="Stand up and stock an overflow shelter ahead of the winter cold snap.",
        start_date=date(2026, 10, 15),
        end_date=date(2026, 10, 20),
    )
    assert shelter.id is not None
    add_requirement(
        session,
        org.id,
        shelter.id,
        skill_id=_skill_id(skills_by_name, "Warehouse Management"),
        min_proficiency=3,
        headcount=1,
    )

    # Mission 5: approved -- through the approval gate, not yet activated.
    intake = create_mission(
        session,
        org.id,
        grace,
        name="Refugee Intake Center",
        description="Multilingual intake and outreach for the new regional intake center.",
        start_date=date(2026, 11, 5),
        end_date=date(2026, 11, 12),
    )
    assert intake.id is not None
    add_requirement(
        session,
        org.id,
        intake.id,
        skill_id=_skill_id(skills_by_name, "Bilingual Translation"),
        min_proficiency=3,
        headcount=2,
    )
    add_requirement(
        session,
        org.id,
        intake.id,
        skill_id=_skill_id(skills_by_name, "Community Outreach"),
        min_proficiency=2,
        headcount=1,
    )
    execute_mission_transition(session, org.id, intake.id, grace, "submit")
    execute_mission_transition(session, org.id, intake.id, director, "approve")

    # Mission 6: completed -- the full happy-path lifecycle, fully staffed.
    winter = create_mission(
        session,
        org.id,
        omar,
        name="Winter Storm Relief",
        description="Clean water and supply distribution through the peak winter storm window.",
        start_date=date(2026, 12, 10),
        end_date=date(2026, 12, 20),
    )
    assert winter.id is not None
    water_requirement = add_requirement(
        session,
        org.id,
        winter.id,
        skill_id=_skill_id(skills_by_name, "Water Purification"),
        min_proficiency=3,
        headcount=1,
    )
    supply_requirement = add_requirement(
        session,
        org.id,
        winter.id,
        skill_id=_skill_id(skills_by_name, "Supply Chain Logistics"),
        min_proficiency=2,
        headcount=1,
    )
    execute_mission_transition(session, org.id, winter.id, omar, "submit")
    execute_mission_transition(session, org.id, winter.id, director, "approve")
    execute_mission_transition(session, org.id, winter.id, omar, "activate")

    assert crew["liam"].id is not None
    assert water_requirement.requirement.id is not None
    water_proposal = propose_assignment(
        session,
        org.id,
        omar,
        mission_id=winter.id,
        requirement_id=water_requirement.requirement.id,
        crew_id=crew["liam"].id,
    )
    assert water_proposal.assignment.id is not None
    respond_to_assignment(session, org.id, crew["liam"], water_proposal.assignment.id, "accept")

    assert crew["ethan"].id is not None
    assert supply_requirement.requirement.id is not None
    supply_proposal = propose_assignment(
        session,
        org.id,
        omar,
        mission_id=winter.id,
        requirement_id=supply_requirement.requirement.id,
        crew_id=crew["ethan"].id,
    )
    assert supply_proposal.assignment.id is not None
    respond_to_assignment(session, org.id, crew["ethan"], supply_proposal.assignment.id, "accept")

    execute_mission_transition(session, org.id, winter.id, omar, "complete")


# --- shared helpers -----------------------------------------------------


def _skill_id(skills_by_name: dict[str, Skill], name: str) -> int:
    skill_id = skills_by_name[name].id
    assert skill_id is not None
    return skill_id


def _report(credentials: list[SeededCredential]) -> None:
    lines = [
        "Mission Control demo credentials (generated fresh this run):",
        "",
        f"{'ORG':<28} {'ROLE':<13} {'NAME':<16} {'EMAIL':<32} PASSWORD",
    ]
    for cred in credentials:
        lines.append(
            f"{cred.org:<28} {cred.role:<13} {cred.name:<16} {cred.email:<32} {cred.password}"
        )
    report = "\n".join(lines)
    print(report)
    print()
    print(f"Also written to: {CREDENTIALS_FILE}")
    CREDENTIALS_FILE.write_text(report + "\n", encoding="utf-8")


def seed() -> None:
    _reset_database_file()
    create_db_and_tables()

    credentials: list[SeededCredential] = []
    with Session(engine) as session:
        _seed_northwind(session, credentials)
        _seed_beacon(session, credentials)

    print(
        "Seeded 2 organisations: Northwind Disaster Response (Director + 3 "
        "Mission Leads, 50 crew, 10 missions spanning all 6 FR-9 lifecycle "
        "states) and Beacon Relief Network (Director + 2 Mission Leads, 6 "
        "crew, 3 missions) -- a large org next to a small one, demonstrating "
        "tenant isolation (FR-1) holds regardless of org size (FR-19)."
    )
    print()
    _report(credentials)


if __name__ == "__main__":
    seed()
