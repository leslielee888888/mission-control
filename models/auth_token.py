"""``auth_tokens`` — the hashed bearer token issued at login (FR-2, PRD §10 #24).

``token_hash`` is the primary key: the raw token is never stored, only its
hash, and a lookup by hash is exactly the operation auth needs (T2).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from models.timestamps import utc_now


class AuthToken(SQLModel, table=True):
    __tablename__ = "auth_tokens"

    token_hash: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)
