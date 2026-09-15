"""Global FastAPI exception handling (FR-20).

Two rules, enforced everywhere, not per-route:
  * invalid input -> 422 with field-level messages
  * any unhandled server error -> generic 500 to the client, full detail
    logged server-side, never a stack trace or internal message leaked out
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("mission_control")


def _format_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Turn FastAPI/Pydantic's raw error list into field-level messages.

    Pydantic's ``loc`` tuple looks like ``("body", "start_date")`` or
    ``("query", "org_id")``; we drop the location-kind prefix (``body`` /
    ``query`` / ``path``) since callers care about the field, not which part
    of the request it came from.
    """
    skip = ("body", "query", "path")
    formatted: list[dict[str, Any]] = []
    for error in exc.errors():
        location = [str(part) for part in error.get("loc", ()) if part not in skip]
        field = ".".join(location) if location else "__root__"
        formatted.append({"field": field, "message": error.get("msg", "Invalid value")})
    return formatted


def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": _format_validation_errors(exc)},
    )


def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full detail (with traceback) goes to the server log only; the client
    # gets a generic message with no internal detail, per FR-20.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    # Registered last / broadest: FastAPI/Starlette still dispatch HTTPException
    # (401/403/404/409 etc., added by later tasks) to its own default handler
    # first, since that's a more specific match than the base Exception type.
    app.add_exception_handler(Exception, unhandled_exception_handler)
