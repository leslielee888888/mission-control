"""Authentication domain logic (FR-2): password verification and opaque
bearer-token issuance/resolution.

RBAC and the ``get_current_user``/``require_role`` FastAPI dependencies live
in ``api/deps.py`` — this module is the domain layer they call into; it
knows nothing about HTTP.
"""

from __future__ import annotations

import hashlib
import secrets

import bcrypt
from sqlmodel import Session

from models.auth_token import create_auth_token, get_auth_token_by_hash
from models.user import User, get_user_by_email, get_user_by_id_unscoped

_TOKEN_BYTES = 32


class InvalidCredentialsError(Exception):
    """Email/password didn't match a user.

    Raised for both an unknown email and a wrong password — the two must be
    indistinguishable to the caller (FR-2), so this carries no detail about
    which one it was.
    """


def hash_password(password: str) -> str:
    """Bcrypt-hash a plaintext password for storage (FR-2)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _hash_token(raw_token: str) -> str:
    """SHA-256 of the raw token, for at-rest storage/lookup.

    Bcrypt (used for passwords, above) is deliberately slow and re-salts on
    every call, which rules out an indexed direct lookup by hash — exactly
    the operation every authenticated request needs. The raw token is a
    32-byte ``secrets.token_urlsafe`` value: unlike a password, it's never
    chosen or reused by a human, so it already carries enough entropy that a
    fast, deterministic hash is the right choice here, not a weaker one.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def login(session: Session, email: str, password: str) -> tuple[User, str]:
    """Verify credentials and issue a new opaque bearer token.

    Returns the user and the *raw* token (shown to the caller exactly once);
    only its hash is persisted. Raises ``InvalidCredentialsError`` on any
    mismatch.
    """
    user = get_user_by_email(session, email)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    assert user.id is not None  # fetched from the DB: always has a pk

    raw_token = secrets.token_urlsafe(_TOKEN_BYTES)
    create_auth_token(session, user_id=user.id, token_hash=_hash_token(raw_token))
    session.commit()
    return user, raw_token


def authenticate(session: Session, raw_token: str) -> User | None:
    """Resolve a bearer token to its ``User``, or ``None`` if the token is
    absent, malformed, or doesn't match a live ``auth_tokens`` row."""
    auth_token = get_auth_token_by_hash(session, _hash_token(raw_token))
    if auth_token is None:
        return None
    return get_user_by_id_unscoped(session, auth_token.user_id)
