"""``users`` — every person who can log in, across all three roles (§4)."""

from __future__ import annotations

from sqlmodel import Field, SQLModel

from models.enums import Role


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    org_id: int = Field(foreign_key="organizations.id", index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    role: Role
    name: str
