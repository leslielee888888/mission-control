"""SQLModel entities + persistence helpers (the bottom of the api -> services
-> models layering, PRD §6 NFR "Code structure for a team").

Every entity module is imported here so ``SQLModel.metadata`` has all ten
tables registered as soon as ``models`` (or any submodule, e.g.
``models.database``) is imported — required before ``create_all()`` runs.

Query helpers live alongside their entities as the services layer grows past
the T1 scaffold (T2+); there are none yet.
"""

from __future__ import annotations

from models.assignment import Assignment
from models.auth_token import AuthToken
from models.availability_window import AvailabilityWindow
from models.crew_profile import CrewProfile
from models.crew_skill import CrewSkill
from models.enums import AssignmentStatus, MissionStatus, Role
from models.mission import Mission
from models.organization import Organization
from models.requirement import Requirement
from models.skill import Skill
from models.user import User

__all__ = [
    "Assignment",
    "AssignmentStatus",
    "AuthToken",
    "AvailabilityWindow",
    "CrewProfile",
    "CrewSkill",
    "Mission",
    "MissionStatus",
    "Organization",
    "Requirement",
    "Role",
    "Skill",
    "User",
]
