"""Demo seed data (T9, FR-19).

Builds two tenant organisations end to end — each with a Director, two
Mission Leads, a varied crew roster, its own skill taxonomy, and missions
spanning several points in the FR-9 lifecycle — so the API/CLI/matcher can be
exercised immediately after a fresh checkout with no manual setup.

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
on every rerun.
"""

from __future__ import annotations

import secrets
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


def _new_user(
    session: Session,
    *,
    org: Organization,
    role: Role,
    name: str,
    email: str,
    credentials: list[SeededCredential],
) -> User:
    """Create one login with a freshly generated demo password, recording it
    in ``credentials`` for the end-of-run report (§10 #24 — real, usable
    passwords, not blank ones)."""
    assert org.id is not None
    password = secrets.token_urlsafe(9)
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


# --- Org A: Northwind Disaster Response -------------------------------------


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

    _build_skill_taxonomy(
        session,
        org,
        [
            ("Wilderness First Aid", "medical"),
            ("Swift-Water Rescue", "rescue"),
            ("Chainsaw Operation", "rescue"),
            ("Incident Command", "leadership"),
            ("Drone Piloting", "recon"),
            ("Logistics Coordination", "logistics"),
        ],
    )

    crew = {
        "sam": _build_crew_member(
            session,
            org=org,
            name="Sam Rivera",
            email="sam.rivera@northwind.demo",
            skills={"Wilderness First Aid": 5, "Swift-Water Rescue": 3, "Incident Command": 2},
            unavailability=[],
            credentials=credentials,
        ),
        # Meets Highland Wildfire Support's proficiency bar but is unavailable
        # across its exact dates -- demonstrates the matcher's availability
        # hard-filter excluding an otherwise-qualified candidate (FR-13a).
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
        # Below every requirement's minimum proficiency it could apply to --
        # demonstrates the matcher's proficiency hard-filter excluding a
        # crew member who holds the skill but not at the bar (FR-13a).
        "jamie": _build_crew_member(
            session,
            org=org,
            name="Jamie Fox",
            email="jamie.fox@northwind.demo",
            skills={"Wilderness First Aid": 1, "Chainsaw Operation": 2},
            unavailability=[],
            credentials=credentials,
        ),
    }

    skills_by_name = {skill.name: skill for skill in list_skills(session, org.id)}

    # Mission 1: draft -- a requirement attached, never submitted.
    flood = create_mission(
        session,
        org.id,
        marcus,
        name="Riverside Flood Response",
        description="Swift-water rescue support for rising river levels near the county line.",
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 12),
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

    # Mission 2: pending_approval -- submitted, awaiting the Director.
    wildfire = create_mission(
        session,
        org.id,
        priya,
        name="Highland Wildfire Support",
        description="Evacuation and containment support for the Highland Ridge wildfire.",
        start_date=date(2026, 10, 20),
        end_date=date(2026, 10, 28),
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

    # Mission 3: active, one requirement filled and one deliberately left
    # short-staffed -- FR-17 ("under-staffing doesn't block activation").
    coastal = create_mission(
        session,
        org.id,
        marcus,
        name="Coastal Storm Recovery",
        description="Debris clearance and incident command for the coastal storm aftermath.",
        start_date=date(2026, 11, 1),
        end_date=date(2026, 11, 10),
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
    assert crew["jordan"].id is not None
    assert ic_requirement.requirement.id is not None
    proposal = propose_assignment(
        session,
        org.id,
        marcus,
        mission_id=coastal.id,
        requirement_id=ic_requirement.requirement.id,
        crew_id=crew["jordan"].id,
    )
    assert proposal.assignment.id is not None
    respond_to_assignment(session, org.id, crew["jordan"], proposal.assignment.id, "accept")
    # Logistics Coordination is left unfilled on purpose (see above).


# --- Org B: Beacon Relief Network --------------------------------------------


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
        "Seeded 2 organisations (Northwind Disaster Response, Beacon Relief "
        "Network), each with a Director, 2 Mission Leads, a crew roster, an "
        "org-specific skill taxonomy, and missions spanning draft / "
        "pending_approval / approved / active / completed (FR-19)."
    )
    print()
    _report(credentials)


if __name__ == "__main__":
    seed()
