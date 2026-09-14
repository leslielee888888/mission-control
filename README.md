# Mission Control

A multi-tenant B2B API and CLI for space organisations to manage missions and
crew. See [`docs/prd/mission-control.md`](docs/prd/mission-control.md) for the
full design document, and
[`docs/design/architecture-explainer.html`](docs/design/architecture-explainer.html)
for a faster visual read of the stack and data model.

## Setup (scaffold)

This is a minimal setup note for the current project scaffold (T1). Full
setup docs, seed data, and a run-through of every workflow land in T9.

```bash
python -m venv .venv
.venv/Scripts/activate    # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
```

Run the API:

```bash
uvicorn main:app --reload
```

Run the tests:

```bash
pytest
```

Lint / format (`ruff` — one tool for both):

```bash
ruff check .
ruff format .
```

## Project layout

```
api/         thin route handlers
services/    domain logic (empty in T1 — filled in T2+)
models/      SQLModel entities + persistence helpers
cli/         missionctl — a Typer CLI that only talks HTTP to the API (T7)
scripts/     seed.py — seed script skeleton (built out in T9)
tests/       pytest suite, incl. a real temporary-SQLite fixture
```
