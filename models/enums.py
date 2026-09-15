"""Enumerations shared by the SQLModel entities.

Plain ``str, Enum`` subclasses so they serialize as their string value in both
SQLite (stored as TEXT) and JSON responses, and compare equal to a plain string.
"""

from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    """A user's role within their organisation (§4)."""

    DIRECTOR = "director"
    MISSION_LEAD = "mission_lead"
    CREW_MEMBER = "crew_member"


class MissionStatus(str, Enum):
    """The six-state mission lifecycle (FR-9)."""

    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class AssignmentStatus(str, Enum):
    """The status of a crew member's assignment to a requirement (FR-14/FR-15)."""

    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    DECLINED = "declined"
