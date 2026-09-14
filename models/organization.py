"""``organizations`` — the tenant boundary every other table traces back to."""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from models.timestamps import utc_now


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=utc_now)
