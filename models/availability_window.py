"""``availability_windows`` — dates a crew member is *unavailable* (FR-7).

No row for a given date range means available by default; this table only
ever records the exception. Non-overlap between a crew member's own windows
is a service-layer rule (T3), not a DB constraint.
"""

from __future__ import annotations

from datetime import date

from pydantic import model_validator
from sqlmodel import Field, SQLModel


class AvailabilityWindow(SQLModel, table=True):
    __tablename__ = "availability_windows"

    id: int | None = Field(default=None, primary_key=True)
    crew_id: int = Field(foreign_key="crew_profiles.user_id", index=True)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _end_not_before_start(self) -> AvailabilityWindow:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self
