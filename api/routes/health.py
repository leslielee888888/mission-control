"""A trivial health-check endpoint — also doubles as proof the DB engine is
reachable, since it runs a real query through the session dependency."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel import Session

from models.database import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(session: Session = Depends(get_session)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}
