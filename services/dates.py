"""Shared date-range overlap helper.

Originally lived only in ``services/crew.py`` (FR-7, availability windows).
Moved here so it has exactly one implementation shared by every caller that
needs it: T3's availability-window overlap check, T5's matcher retrieval
stage (FR-13a: unavailability overlap + conflicting-confirmed-assignment
overlap), and T6's double-booking guard (FR-16) — none of which should carry
its own copy of the same boundary logic.
"""

from __future__ import annotations

from datetime import date


def windows_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """Date-range overlap, inclusive of shared boundary days: two windows
    that each include the same day count as overlapping."""
    return a_start <= b_end and b_start <= a_end
