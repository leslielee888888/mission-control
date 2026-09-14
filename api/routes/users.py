"""``GET /users/{user_id}`` — a Director-only, org-scoped user lookup.

Not a general user-management API (out of scope for T2) — this exists to
give the org_id-required repository pattern (FR-1) and ``require_role``
(FR-3) a real HTTP surface, the same shape every later task's own entities
will follow.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from api.deps import require_role
from api.routes.auth import UserOut
from models.database import get_session
from models.enums import Role
from models.user import User, get_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}", response_model=UserOut)
def get_user_route(
    user_id: int,
    session: Session = Depends(get_session),
    caller: User = Depends(require_role(Role.DIRECTOR)),
) -> UserOut:
    user = get_user(session, caller.org_id, user_id)
    if user is None:
        # Covers both "no such user" and "exists, but in another org" —
        # identical response either way (FR-1).
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserOut.model_validate(user, from_attributes=True)
