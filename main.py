"""FastAPI app entrypoint.

Run with: ``uvicorn main:app --reload``
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.errors import register_exception_handlers
from api.routes.assignment import router as assignment_router
from api.routes.auth import router as auth_router
from api.routes.crew import router as crew_router
from api.routes.health import router as health_router
from api.routes.match import router as match_router
from api.routes.mission import router as mission_router
from api.routes.skills import router as skills_router
from api.routes.users import router as users_router


def create_app() -> FastAPI:
    app = FastAPI(title="Mission Control API")

    # T8: the showcase SPA (web/) calls this API directly from the browser
    # (Vite dev server on its own port, e.g. 5173, against uvicorn on
    # 8000) -- a different origin, so without CORS the browser's preflight
    # never gets past OPTIONS and every request 405s before auth even runs.
    # Auth is a bearer token in the Authorization header, not a cookie, so
    # there's nothing ambient to protect by restricting origins here; kept
    # wide open (`*`) rather than hardcoding a dev port that'll just drift.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(skills_router)
    app.include_router(crew_router)
    app.include_router(mission_router)
    app.include_router(match_router)
    app.include_router(assignment_router)

    # No table creation here, deliberately: creating tables is the seed
    # script's job (`scripts/seed.py`), not a side effect of importing or
    # constructing the app. An eager `create_db_and_tables()` call here
    # used to run against the real dev-database engine on every import —
    # including every test run, since `tests/conftest.py` imports `app` —
    # which wrote a real mission_control.db file regardless of the
    # dependency override tests set up for `get_session`. Run
    # `python scripts/seed.py` before starting the server locally.

    return app


app = create_app()
