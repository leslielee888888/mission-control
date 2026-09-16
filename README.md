# Mission Control

A staffing coordination tool for disaster-response and relief organisations: crew
profiles with skills and availability, missions that move through an approval-gated
lifecycle, an auto-matching engine that ranks eligible crew per requirement, and
propose/accept assignment workflows — multi-tenant throughout (every org's data is
isolated from every other org's).

- **Design doc:** [`docs/prd/mission-control.md`](docs/prd/mission-control.md) — the
  full requirements, architecture decisions, and open-question log.
- **Fast architecture read:** [live artifact](https://claude.ai/code/artifact/e14d23aa-0235-4a6d-9bee-1be3edaa7895)
  (source: [`docs/design/architecture-explainer.html`](docs/design/architecture-explainer.html))
  — opens straight in a browser, no clone needed, for the stack choices, the data
  model, the design patterns, and the layered request flow in a few minutes, instead
  of the PRD's full detail.
- **SPA mockups:** [live artifact](https://claude.ai/code/artifact/de0b0bf5-d39d-4a2b-8392-1ac4339bd93a)
  (source: [`docs/design/spa-mockups/`](docs/design/spa-mockups/)) — the 4 screens
  (login, mission list, mission detail w/ matcher + approval, my assignments) as
  designed before `web/` was built.

## For reviewers

Everything the brief asks for lives in this repo:

- **Design document** — `docs/prd/mission-control.md`, written before implementation
  (§0 explains the framing), with the full grilling log (§14) and Refinement log (§13)
  showing the real back-and-forth, not a document written after the fact.
- **Source code** — this repo, meaningful commit history (each task merged through its
  own PR — see the closed PRs and `## 12. Tasks` in the PRD for the task→PR mapping).
- **AI transcripts, unedited** — `transcripts/` (see `transcripts/README.md` for an
  index): every subagent's own conversation, plus the full main session, exactly as
  Claude Code recorded them — including the dead ends and corrections, per the brief's
  own instruction not to clean these up.

The fastest way to explore: run the [Docker quick start](#quick-start-docker) below,
which needs nothing but Docker and gives you a populated instance in under a minute —
or open the [architecture explainer artifact](https://claude.ai/code/artifact/e14d23aa-0235-4a6d-9bee-1be3edaa7895)
first for the five-minute version of the whole system before touching any code.

## Stack

FastAPI + SQLModel (SQLAlchemy) + SQLite, synchronous throughout, on the backend.
`missionctl` (Typer + `httpx`) is the primary interface — a thin HTTP client that
talks to the API exactly like any other caller would (no direct database access). A
React + Vite + Tailwind SPA (`web/`) is a showcase on top of the same API — see PRD §8
for the full stack rationale, and §10 #16-18 for why the SPA is scoped the way it is
(not full CLI parity).

## Quick start (Docker)

The fastest path — no local Python/Node setup needed, and the container seeds itself
with demo data on first start (only if the database doesn't already exist, so
restarting never wipes anything you've done):

```bash
docker compose up -d
```

- API: `http://localhost:8100`
- SPA: `http://localhost:8101`
- Demo credentials: printed by the seed step on first start —
  `docker compose logs api | grep -A 999 "demo credentials"` (or see `seed_credentials.txt`
  inside the container: `docker compose exec api cat seed_credentials.txt`)

Ports are configurable via `.env` (copy `.env.example`) if `8100`/`8101` collide with
something else on your machine.

## Setup (clean checkout, no Docker)

Requires Python 3.11+.

```bash
pip install -r requirements.txt
python -m scripts.seed          # creates mission_control.db with demo data (see below)
uvicorn main:app --reload       # starts the API on http://127.0.0.1:8000
```

Leave `uvicorn` running in one terminal; run `missionctl` commands from another.

### The showcase SPA (optional)

```bash
cd web
npm install
npm run dev                     # http://localhost:5173, talks to the API above
```

## Seed data

`python -m scripts.seed` (re-run any time — every run starts from a fresh database
file, so it's "fresh file, full rebuild," not incremental) builds two demo
organisations end to end — deliberately very different in scale, to show tenant
isolation holds regardless of org size:

- **Northwind Disaster Response** — a large roster and a full spread of missions
  across every lifecycle state, with real proficiency/availability variation so the
  matcher's hard filters have genuine exclusions to show, not just a uniform pool.
- **Beacon Relief Network** — a smaller org with its own, completely independent
  6-skill taxonomy, for contrast.

(Exact counts are in `scripts/seed.py`'s own docstring and printed summary — kept
here deliberately brief so this doesn't drift out of sync with the script.)

### Demo credentials

The seed script generates a real, random password for every user (never blank) and:

- prints an `email -> password` table to stdout at the end of the run, and
- writes the same table to `seed_credentials.txt` at the repo root (gitignored —
  never committed).

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

Runs against real temporary SQLite databases (not mocks) — see PRD §8. Covers tenant
isolation, RBAC, the mission lifecycle state machine, the matcher's filtering/scoring,
and assignment propose/respond/double-booking.

```bash
ruff check .
ruff format --check .
```

## CI / Docker images

Every PR and push to `main` or a `feature/**` branch runs the same checks above
(`.github/workflows/ci.yml`) plus builds and publishes the API and SPA images to GHCR
(`.github/workflows/docker-publish.yml`) — see PRD §8/§13 (R-4) for why.

`.github/workflows/pr-review-trigger.yml` is a Leslie-side operational detail, not
part of the submission: an optional fast-path notifier to his personal PR-review
tooling on a self-hosted runner he controls (needs `curl` and `jq`). It needs the
`PR_REVIEW_TRIGGER_URL` repository **variable**, the `PR_REVIEW_TRIGGER_TOKEN`
repository **secret** (different tabs under Settings > Secrets and variables >
Actions — mixing them up leaves the trigger silently non-functional), and that
runner online to do anything; absent any of those, the job just fails harmlessly
(`continue-on-error: true`, never a required check). Since this repo is public,
its "Fork pull request workflows" setting is `all_external_contributors` — every
non-owner PR holds for manual approval before any workflow (this one included)
runs — see the file's own header comment for the full reasoning.
