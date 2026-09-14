# Mission Control

A staffing coordination tool for disaster-response and relief organisations: crew
profiles with skills and availability, missions that move through an approval-gated
lifecycle, an auto-matching engine that ranks eligible crew per requirement, and
propose/accept assignment workflows — multi-tenant throughout (every org's data is
isolated from every other org's).

- **Design doc:** [`docs/prd/mission-control.md`](docs/prd/mission-control.md) — the
  full requirements, architecture decisions, and open-question log.
- **Fast architecture read:** [`docs/design/architecture-explainer.html`](docs/design/architecture-explainer.html)
  — open it in a browser for the stack choices and the layered request flow in a few
  minutes, instead of the PRD's full detail.

## Stack

FastAPI + SQLModel (SQLAlchemy) + SQLite, synchronous throughout. `missionctl`
(Typer + `httpx`) is the primary interface — a thin HTTP client that talks to the API
exactly like any other caller would (no direct database access). See the PRD §8 for
the full rationale.

## Setup (clean checkout)

Requires Python 3.11+. No external services — SQLite is a local file, no Postgres,
Redis, or Docker needed.

```bash
pip install -r requirements.txt
python -m scripts.seed          # creates mission_control.db with demo data (see below)
uvicorn main:app --reload       # starts the API on http://127.0.0.1:8000
```

Leave `uvicorn` running in one terminal; run `missionctl` commands from another.

## Seed data

`python -m scripts.seed` (re-run any time) builds two demo organisations end to end —
each with a Director, two Mission Leads, a varied crew roster, its own skill
taxonomy, and missions spanning several points in the lifecycle — so there's
something real to explore immediately, with no manual setup:

- **Northwind Disaster Response** — 6 skills (Wilderness First Aid, Swift-Water
  Rescue, Chainsaw Operation, Incident Command, Drone Piloting, Logistics
  Coordination), 7 crew members with deliberately varied proficiencies and
  availability, and 3 missions: one `draft`, one `pending_approval`, one `active`
  (partially staffed on purpose, to show FR-17's fulfillment visibility).
- **Beacon Relief Network** — a completely different 6-skill taxonomy (Community
  Outreach, Bilingual Translation, Warehouse Management, Mental Health First Aid,
  Water Purification, Supply Chain Logistics), 6 crew members, and 3 missions: one
  `draft`, one `approved`, one `completed` (the full happy-path lifecycle, fully
  staffed).

That's 5 of the 6 lifecycle states represented out of the box (the 6th, `cancelled`,
is one `missionctl mission cancel <id>` away from any pre-completed mission).

**Every run starts from a fresh database file.** The script deletes any existing
`mission_control.db` before creating tables, so it isn't incremental/idempotent —
it's "fresh file, full rebuild," which is simpler and sufficient here. Don't run it
against a database you want to keep.

### Demo credentials

The seed script generates a real, random password for every user (never blank) and:

- prints an `email -> password` table to stdout at the end of the run, and
- writes the same table to `seed_credentials.txt` at the repo root (gitignored —
  never committed).

Run `python -m scripts.seed` and read either of those for login credentials. A few
of the emails, for reference: `director.dana@northwind.demo`,
`lead.marcus@northwind.demo`, `sam.rivera@northwind.demo` (Northwind);
`director.elena@beacon.demo`, `lead.omar@beacon.demo`, `liam.oconnor@beacon.demo`
(Beacon) — passwords are only ever in the generated output, not in this file or in
source control.

## Using the CLI

`missionctl` talks to the API over HTTP (`MISSIONCTL_API_BASE_URL`, default
`http://127.0.0.1:8000`) and caches your bearer token at `~/.missionctl/session.json`
after login, so you don't need to pass it on every command.

```bash
python -m cli.main login director.dana@northwind.demo <password-from-seed-output>
python -m cli.main whoami

python -m cli.main mission list
python -m cli.main mission show <mission-id>
python -m cli.main match run <mission-id>

python -m cli.main --help          # every command group
python -m cli.main mission --help  # every subcommand in a group
```

Every command prints pretty-printed JSON and exits non-zero with a clear `error`
message on a validation failure, a permission error, or a not-found — see PRD §7 for
the full command list grouped by workflow (auth, org & skills, crew self-service,
missions, matching & assignment, listing).

## Tests

```bash
pytest -v
```

Runs against real temporary SQLite databases (not mocks) — see PRD §8. 137 tests
cover tenant isolation, RBAC, the mission lifecycle state machine, the matcher's
filtering/scoring, and assignment propose/respond/double-booking.

```bash
ruff check .
ruff format --check .
```
