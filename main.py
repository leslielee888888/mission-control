"""FastAPI app entrypoint.

Run with: ``uvicorn main:app --reload``
"""

from __future__ import annotations

from fastapi import FastAPI

from api.errors import register_exception_handlers
from api.routes.auth import router as auth_router
from api.routes.crew import router as crew_router
from api.routes.health import router as health_router
from api.routes.skills import router as skills_router
from api.routes.users import router as users_router


def create_app() -> FastAPI:
    app = FastAPI(title="Mission Control API")

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(skills_router)
    app.include_router(crew_router)

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
