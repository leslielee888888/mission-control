"""Small shared helper for default timestamp columns."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return the current UTC time.

    Used as a SQLModel ``default_factory`` — a plain function reference (not a
    call) so each row gets its own timestamp at insert time, not one shared
    value computed at import time.
    """
    return datetime.now(UTC)
