"""FastAPI app entrypoint.

Run with: ``uvicorn main:app --reload``
"""

from __future__ import annotations

from fastapi import FastAPI

from api.errors import register_exception_handlers
from api.routes.health import router as health_router
from models.database import create_db_and_tables


def create_app() -> FastAPI:
    app = FastAPI(title="Mission Control API")

    register_exception_handlers(app)
    app.include_router(health_router)

    # Scaffold only (T1): create tables on startup against the dev SQLite
    # file so the app is runnable out of the box. T9 replaces ad-hoc startup
    # table creation with the documented seed command.
    create_db_and_tables()

    return app


app = create_app()
