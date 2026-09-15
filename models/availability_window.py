"""``availability_windows`` — dates a crew member is *unavailable* (FR-7).

No row for a given date range means available by default; this table only
ever records the exception. Non-overlap between a crew member's own windows
is a service-layer rule (T3), not a DB constraint.
"""

from __future__ import annotations

from datetime import date

from pydantic import model_validator
from sqlmodel import Field, Session, SQLModel, select


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


def list_availability_windows(session: Session, crew_id: int) -> list[AvailabilityWindow]:
    statement = (
        select(AvailabilityWindow)
        .where(AvailabilityWindow.crew_id == crew_id)
        .order_by(AvailabilityWindow.start_date)
    )
    return list(session.exec(statement).all())


def get_availability_window(
    session: Session, crew_id: int, window_id: int
) -> AvailabilityWindow | None:
    """Fetch a window by id, scoped to ``crew_id`` (a crew member can only
    ever see/remove their own windows — FR-7)."""
    window = session.get(AvailabilityWindow, window_id)
    if window is None or window.crew_id != crew_id:
        return None
    return window


def create_availability_window(
    session: Session, *, crew_id: int, start_date: date, end_date: date
) -> AvailabilityWindow:
    window = AvailabilityWindow(crew_id=crew_id, start_date=start_date, end_date=end_date)
    session.add(window)
    session.flush()
    return window


def delete_availability_window(session: Session, window: AvailabilityWindow) -> None:
    session.delete(window)
    session.flush()
