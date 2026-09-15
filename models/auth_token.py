"""``auth_tokens`` — the hashed bearer token issued at login (FR-2, PRD §10 #24).

``token_hash`` is the primary key: the raw token is never stored, only its
hash, and a lookup by hash is exactly the operation auth needs (T2).
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, Session, SQLModel

from models.timestamps import utc_now


class AuthToken(SQLModel, table=True):
    __tablename__ = "auth_tokens"

    token_hash: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=utc_now)


def create_auth_token(session: Session, *, user_id: int, token_hash: str) -> AuthToken:
    """Persist a newly issued token's hash. The raw token is never passed
    in or stored — only the caller (``services.auth.login``) ever sees it."""
    auth_token = AuthToken(user_id=user_id, token_hash=token_hash)
    session.add(auth_token)
    session.flush()
    return auth_token


def get_auth_token_by_hash(session: Session, token_hash: str) -> AuthToken | None:
    """Look up a token by its hash. Deliberately global, not org-scoped —
    this *is* the operation that resolves who the caller's org even is."""
    return session.get(AuthToken, token_hash)
