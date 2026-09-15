"""Cross-cutting FastAPI dependencies: bearer-token auth and RBAC (FR-2, FR-3).

Routes declare these via ``Depends(...)``; FastAPI resolves and enforces
them before the route handler body runs, so a disallowed role never causes
a side effect (FR-3).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from models.database import get_session
from models.enums import Role
from models.user import User
from services.auth import authenticate

# auto_error=False: a missing header must 401 (our own message), not the
# scheme's default 403.
_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication token",
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    """Resolve the ``Authorization: Bearer <token>`` header to a ``User``.

    401 whenever the header is absent, malformed, or the token doesn't
    match a live ``auth_tokens`` row — deliberately indistinguishable to
    the caller.
    """
    if credentials is None or not credentials.credentials:
        raise _unauthenticated()
    user = authenticate(session, credentials.credentials)
    if user is None:
        raise _unauthenticated()
    return user


def require_role(*roles: Role) -> Callable[..., User]:
    """Dependency factory: the wrapped route only admits one of ``roles``.

    A disallowed role gets 403 naming the required role(s). Usage:
    ``caller: User = Depends(require_role(Role.DIRECTOR))``.
    """
    if not roles:
        raise ValueError("require_role() needs at least one role")

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            required = ", ".join(sorted(role.value for role in roles))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role: {required}",
            )
        return user

    return checker
