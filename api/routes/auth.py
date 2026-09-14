"""``POST /auth/login`` and ``GET /auth/whoami`` (FR-2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import get_current_user
from models.database import get_session
from models.enums import Role
from models.user import User
from services.auth import InvalidCredentialsError, login

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class UserOut(BaseModel):
    id: int
    org_id: int
    email: str
    name: str
    role: Role


class LoginResponse(BaseModel):
    token: str
    user: UserOut


@router.post("/login", response_model=LoginResponse)
def login_route(payload: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    try:
        user, token = login(session, payload.email, payload.password)
    except InvalidCredentialsError as exc:
        # Deliberately generic: never reveal whether the email or the
        # password was wrong (FR-2).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect",
        ) from exc
    return LoginResponse(token=token, user=UserOut.model_validate(user, from_attributes=True))


@router.get("/whoami", response_model=UserOut)
def whoami_route(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)
