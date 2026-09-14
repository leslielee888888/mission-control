"""``missionctl`` — a thin HTTP client over the Mission Control API.

Talks to the API over ``httpx`` only; never touches the database or the
``services``/``models`` layers directly (FR-18).
"""
