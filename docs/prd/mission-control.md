# PRD: Mission Control

- **Status:** `Draft` → `Discovery` → `In development` → `Refinement` → `Finalize` → **`Shipped`**
  ([v1.0.0](https://github.com/leslielee888888/mission-control/releases/tag/v1.0.0),
  merged via [PR #22](https://github.com/leslielee888888/mission-control/pull/22))
- **Author:** Leslie
- **Repo:** [`leslielee888888/mission-control`](https://github.com/leslielee888888/mission-control) — new
  standalone repo, created for this challenge. This doc, the source code, and the full
  unedited AI transcripts all live here, since the whole repo is what gets shared with
  Mutinex (not split across Leslie's private `ai-docs`).
- **Last updated:** 2026-09-16
- **Reviewers:** Leslie (self-owned). This document is also the **design document**
  Mutinex's brief asks for — the artifact "you would use to communicate the intended
  solution to an engineering team and guide an AI coding agent" — submitted alongside
  the code and transcripts.
- **Explainer artifact:** [Mission Control Architecture](https://claude.ai/code/artifact/e14d23aa-0235-4a6d-9bee-1be3edaa7895)
  — the FE/BE stack and why, the layered request flow, and the vertical-slice/
  scaffolding boundary from grilling, as a fast visual read alongside this PRD's full
  detail (source: `docs/design/architecture-explainer.html`).
- **Design:** Primary workflows are exercised through a CLI (§7); the brief states "a
  web interface is not required," and the CLI remains the system of record for that
  coverage. A deliberately minimal React SPA (FR-21, §7) is also included — not
  required, added as a state-management showcase — see §10 #16/#18 for its scope.
  Mockups: [Mission Control SPA Mockups](https://claude.ai/code/artifact/de0b0bf5-d39d-4a2b-8392-1ac4339bd93a)
  (4 screens: login, mission list, mission detail w/ matcher + approval, my
  assignments — source in `docs/design/spa-mockups/`).

## 0. What this actually is

This PRD is written **against the brief as a real product brief** — Mission Control is
described as if it will be used by real space organisations, and the requirements below
are written that way. But the actual deliverable is Mutinex's **Senior Software
Engineer take-home challenge**: a 3–5 hour timeboxed build, evaluated on the design
document, the code, and Leslie's unedited AI-tool transcripts, not on breadth or
production polish. Two things follow from that, called out here once rather than
re-litigated in every section:

- **Scope discipline matters more than usual.** The brief explicitly says "prioritise a
  coherent design, a working vertical slice, and evidence of verification over breadth
  or polish." Several requirements below are deliberately the simplest version that
  still demonstrates real judgment (e.g. a real login endpoint instead of a full OAuth
  flow), not
  because a production system wouldn't need more, but because building more here would
  trade signal (a working, well-reasoned vertical slice) for volume.
- **The transcripts are a submission artifact, not incidental.** Every conversation with
  the AI coding tool during the build must be captured unedited and included in this
  repo (§8, §11). That is tracked as an explicit task, not an afterthought at the end.

## 1. Summary

Mission Control's core: a multi-tenant B2B API and CLI that lets space organisations
manage missions and crew — skill profiles, availability, a mission lifecycle with an
approval gate, and an auto-matching engine that ranks crew against a mission's
requirements. Each organisation is a tenant with its own users, crew roster, skill
taxonomy, and missions; data never crosses tenant boundaries. Three roles — Director,
Mission Lead, Crew Member — get different slices of the same API. A CLI (`missionctl`)
is a thin HTTP client over that API, so every primary workflow (plan a mission, run the
matcher, approve, respond to an assignment) can be exercised end to end from a terminal
with seeded data, no web UI required. A minimal React SPA (FR-21) also sits on top of
the same API as a state-management showcase, not a substitute for the CLI.

## 2. Problem & context

Crew assignment today is manual and error-prone: a mission lead cross-references skill
profiles, availability calendars, and existing commitments by hand, for every mission,
every time. That doesn't scale past a handful of people, and it's exactly the kind of
constraint-satisfaction problem software is good at — matching a mission's skill/
proficiency/headcount requirements against a roster's skills, availability, and current
workload. The platform is multi-tenant because "space organisations" here means
agencies, research labs, and private companies of very different sizes, each with their
own skill taxonomy and approval process — so tenant isolation and per-org configurability
(skills, roles) are load-bearing, not incidental.

If this were a real product and nothing were built: leads keep doing the
cross-referencing by hand, mistakes (double-booked crew, under-skilled assignments) keep
costing incident response time, and nothing captures *why* a crew member was assigned,
which matters when a mission is questioned after the fact.

## 3. Goals / Non-goals

**Goals**

- A multi-tenant API where every record is scoped to an organisation and access is
  governed by one of three roles, enforced server-side.
- A mission lifecycle with a real approval gate: a Mission Lead cannot approve their own
  mission; only a Director who didn't create it can.
- Crew management with org-defined skills, per-crew proficiency, and availability
  windows.
- An auto-matching engine that filters on hard constraints (skill/proficiency met,
  available for the mission window, no double-booking) and ranks survivors on soft
  factors (proficiency surplus, workload balance), with each suggestion's reasoning
  visible — not a black box.
- A CLI covering every primary workflow end to end against the real API, with seed data
  that makes multi-tenancy and matching demonstrable out of the box.
- Code structured in layers (API → service → data) a team could actually divide and
  extend, not a single script.

**Non-goals (this build)**

- A **full-featured** web UI — the brief doesn't require one. What's built (FR-21, §7)
  is a deliberately minimal 2–3 screen showcase of the same API, not a product-grade
  frontend (no routing depth, no settings/admin screens, no CLI parity) — see §10 #16.
- Production-grade auth (OAuth/SSO, password reset, email verification, session
  refresh, MFA). A real username+password login endpoint issuing hashed, opaque bearer
  tokens (FR-2) is enough to demonstrate the RBAC and tenant-isolation boundaries,
  which are what's being evaluated — see §10 #24.
- Globally optimal assignment solving (e.g. Hungarian algorithm across all requirements
  at once). The matcher does per-requirement ranked scoring with hard-constraint
  filtering — real judgment about the problem, without importing an optimisation
  library to solve a scale this system doesn't have yet (see §6 non-functional).
- Notifications (email/push) when a mission is approved or an assignment proposed — the
  CLI/API state is the source of truth; a crew member checks it, they aren't paged.
- Multi-role users, org-to-org collaboration, or missions spanning multiple
  organisations.
- **Public** deployment — a take-home challenge doesn't need one, and this system was
  never built with internet-facing auth/hardening in mind. A LAN-only demo instance
  does exist (R-5, Refinement — see §8: Leslie's own Synology NAS, containerized via
  R-4), reachable only from inside his own network, purely for convenience while
  testing — it isn't what "easy to run locally" or the evaluation criteria are about,
  and it isn't part of the submission.

## 4. Users & use cases

Three roles, scoped to one organisation each (a user belongs to exactly one org and
holds exactly one role in it):

- **Director** — runs the org. Defines the org's skill taxonomy, has broad read
  visibility across missions/crew/assignments, and is the only role that can approve or
  reject a mission — except one they created themselves.
  - *"A mission just came in for approval — is it staffed sensibly and do I trust the
    plan?"* → view the mission, its requirements, and proposed/confirmed assignments,
    then approve or reject with a reason.
- **Mission Lead** — plans and runs missions. Defines a mission's requirements, runs the
  matcher, proposes assignments from its suggestions, and submits the mission for
  approval. Cannot approve their own mission even if they also happen to hold Director
  permissions in some other context (the rule is identity-based, not just role-based —
  see FR-11).
  - *"I need three crew with EVA certification for a 12-day window — who's actually
    free and qualified?"* → create the mission, add a requirement, run the matcher, and
    propose assignments to the top suggestions.
- **Crew Member** — manages their own profile: skills, proficiency, and availability.
  Sees only missions they're proposed or confirmed on, not the org's full mission list
  or roster.
  - *"I've been proposed for a mission — can I actually do this window?"* → view the
    proposed assignment and accept or decline it.

## 5. Done when

Solo, one-shot submission — there's no ongoing usage to measure, so "success" is a
checklist tying directly to the brief's stated evaluation criteria and the minimum
scope it names. Grilling (§14) drew an explicit line between a **real, tested vertical
slice** and a **lighter scaffolding** layer around it (§10 #17) — both need to exist,
but only the former needs test evidence.

**Real, tested vertical slice:**

- [x] A multi-tenant API enforces org scoping on every record and role-based access on
      every endpoint (FR-1–FR-3), with a test proving org A cannot read or write org B's
      data even with a valid token.
- [x] Username+password login (FR-2) verifies against a hashed password and issues a
      hashed, opaque bearer token; a missing/invalid token or wrong credentials return
      401.
- [x] The mission lifecycle (draft → pending approval → approved → active → completed,
      plus reject/cancel) is enforced server-side, and a Director cannot approve a
      mission they created (FR-9–FR-11).
- [x] The auto-matching engine filters on hard constraints and ranks on soft factors at
      the defined weights, with visible reasoning per suggestion (FR-13).
- [x] Assignment propose/respond and the double-booking guard work end to end
      (FR-14–FR-16).
- [x] Test evidence for everything above is a handful of representative cases per area
      (tenant isolation, self-approval gate, matcher scoring, lifecycle transitions) —
      not exhaustive coverage (§10 #17).

**Lighter / scaffolding (real seed data; minimal-effort or mocked where time is short):**

- [x] Crew management — skill profiles (org-scoped taxonomy, per-crew proficiency) and
      availability (FR-4–FR-7) — functions well enough to feed the vertical slice
      above; not a testing priority.
- [x] A CLI exercises every primary workflow — login, crew/skill/availability
      management, mission planning through approval, running the matcher, assignment
      response — entirely by calling the real API (FR-18); the CLI is the system of
      record for this coverage, not the SPA (§10 #19).
- [x] A minimal React SPA (FR-21) shows mission list/detail, a matcher run, and
      propose/approve/accept actions for all three roles, with real or mocked data as
      the vertical-slice boundary allows (§10 #16–#18, #23).

**Always required:**

- [x] The repo runs locally from a clean checkout with documented setup steps and seed
      data demonstrating ≥2 tenants (FR-19).
- [x] The design document (this file) was written before implementation and is the
      artifact that guided the agent — checked by the grilling log (§14) and the
      refinement log (§13) actually reflecting real back-and-forth.
- [x] Every AI-tool conversation from the build (main session + every subagent) is
      captured unedited in `transcripts/` in this repo (§8) — refreshed at Finalize
      to also cover Refinement (R-1–R-9) and Finalize itself, not just Development;
      see `transcripts/README.md` for the full index.
- [x] Commit history on the repo is meaningful (not one squashed blob) and public.

## 6. Requirements

### Functional

| ID | Requirement | Priority | Acceptance criteria (Given/When/Then) |
|----|-------------|----------|----------------------------------------|
| FR-1 | Tenant scoping | Must | **Given** any domain record (user, crew, skill, mission, assignment), **When** it is created, **Then** it carries an `org_id` derived from the authenticated caller, never from client input; **Given** a request for a specific record, **When** its `org_id` doesn't match the caller's, **Then** the API returns 404 (not 403) so a caller can't distinguish "not mine" from "doesn't exist." |
| FR-2 | Authentication | Must | **Given** a seeded user with an email/password, **When** the CLI runs `missionctl login <email> <password>` or the SPA's login form submits the same pair to `POST /auth/login`, **Then** the API verifies the password against its hash and issues an opaque bearer token, stored locally (CLI) or in `localStorage` (SPA) and attached to subsequent requests; **Given** a missing/invalid token or wrong credentials, **Then** the API returns 401. Tokens are opaque random strings, hashed at rest; passwords are hashed (bcrypt/argon2) at rest, never logged. The seed script generates and documents each demo user's password (§10 #24). |
| FR-3 | Role-based access control | Must | **Given** an endpoint declares its allowed role(s), **When** a request arrives from an authenticated user whose role isn't allowed, **Then** the API returns 403 with a message naming the required role, and no side effect occurs. |
| FR-4 | Crew profile management | Must | **Given** a crew member, **When** they call `missionctl profile update`, **Then** they can change their own name/contact/bio; **Given** a Director or Mission Lead, **Then** they can view (not edit) any crew member's profile in their org. |
| FR-5 | Org-scoped skill taxonomy | Must | **Given** a Director, **When** they create a skill (`missionctl skills add <name>`), **Then** it's scoped to their org and unique by name within it; **Given** two different orgs, **Then** each can define a skill with the same name independently (no cross-org collision). |
| FR-6 | Crew skill profiles | Must | **Given** a crew member and an org-defined skill, **When** the crew member (or a Director on their behalf) sets a proficiency level (1–5 integer scale), **Then** it's stored on their profile and visible to Mission Leads/Directors in the org; a crew member can hold any number of skills. |
| FR-7 | Crew availability | Must | **Given** a crew member, **When** they add an unavailability window (start/end date), **Then** it's recorded against their profile; absent any window, a crew member defaults to available. Windows can't overlap for the same crew member. **When** they call `missionctl availability remove <id>`, **Then** that window is deleted — delete-only, no in-place edit; a mistake is corrected by remove + re-add (§10 #2). |
| FR-8 | Mission creation & requirements | Must | **Given** a Mission Lead (or Director), **When** they create a mission (name, description, start date, end date), **Then** it starts in `draft`; **When** they add a requirement (skill, minimum proficiency, headcount needed), **Then** it's attached to the mission; a mission can have multiple requirements across different skills. |
| FR-9 | Mission lifecycle state machine | Must | **Given** a mission, **Then** its status is one of `draft`, `pending_approval`, `approved`, `active`, `completed`, `cancelled`; **Given** a transition not in the allowed set (`draft→pending_approval`, `pending_approval→approved`, `pending_approval→draft` [reject], `approved→active`, `active→completed`, and `cancelled` from any pre-completed state), **When** it's attempted, **Then** the API returns 409 and the status is unchanged. |
| FR-10 | Submit for approval | Must | **Given** a `draft` mission, **When** its creator calls `missionctl mission submit`, **Then** it moves to `pending_approval` **only if** at least one requirement is defined; with zero requirements, submission is rejected with a clear message. |
| FR-11 | Approval gate — no self-approval | Must | **Given** a `pending_approval` mission, **When** a Director who is **not** the mission's creator approves it, **Then** it moves to `approved`; **When** the mission's own creator (regardless of their role) attempts to approve it, **Then** the API returns 403. Rejection (back to `draft`, with a required reason) follows the same identity check. |
| FR-12 | Activation & completion | Must | **Given** an `approved` mission, **When** a Mission Lead or Director calls `missionctl mission activate` / `...complete`, **Then** it transitions to `active` / `completed`. Transitions are explicit actions, not date-triggered — no scheduler in this build (see §10 open questions). |
| FR-13 | Auto-matching engine | Must | **Given** a mission with requirements, **When** `missionctl match run <mission>` is called, **Then** for each requirement the engine: (a) **hard-filters** crew to those in the same org who hold the required skill at ≥ the minimum proficiency, have no unavailability window overlapping the mission's dates, and have no *confirmed* assignment on another mission with an overlapping date range; then (b) **ranks** survivors by a weighted score combining three factors each normalized to 0–1 — proficiency surplus (their level minus the minimum), current workload (fewer active confirmed assignments scores higher), and availability margin (slack between their free window and the mission's) — at fixed weights 50% / 30% / 20% respectively, not user-configurable in this build; and (c) returns **every** eligible candidate (no top-N cap), each with their score and a one-line breakdown of which factors contributed, not just a bare number (§10 #9). **Availability margin, precisely** (R-1, defined during T5 implementation — §10 #9 fixed only the weights, not this formula): `nearest_constraint_gap_days` = fewest free days between the mission's window and the closest edge of the crew member's nearest constraint interval (an unavailability window, or another mission they hold a confirmed assignment on); `margin = min(gap_days, 30) / 30`, and 1.0 if the crew member has no constraints at all. See `services/matcher.py`'s module docstring for the full reasoning. |
| FR-14 | Propose assignment from a match | Must | **Given** matcher output (or any eligible crew member found by other means), **When** a Mission Lead calls `missionctl assign propose <mission> <requirement> <crew>`, **Then** an assignment is created in `proposed` status, up to the requirement's headcount; proposing beyond headcount is rejected. |
| FR-15 | Crew response to assignment | Must | **Given** a `proposed` assignment, **When** the named crew member accepts, **Then** it becomes `confirmed`; **When** they decline, **Then** it becomes `declined` and the requirement's remaining headcount is recalculated so the matcher/lead can fill it from someone else. |
| FR-16 | Double-booking guard | Must | **Given** an assignment is about to become `confirmed`, **When** the same crew member already holds a `confirmed` assignment on a mission with an overlapping date range, **Then** the confirmation is rejected (409) naming the conflicting mission — enforced here as a safety net even though the matcher already filters for it in FR-13, since assignments can also be proposed manually, outside the matcher. |
| FR-17 | Requirement fulfillment visibility | Should | **Given** a mission, **When** its detail is viewed, **Then** each requirement shows confirmed-vs-needed headcount at a glance. Under-staffing does **not** block activation (FR-12) — a lead may knowingly launch short-staffed — it's surfaced, not enforced (see §10 open questions). |
| FR-18 | CLI coverage of primary workflows | Must | **Given** the API is running, **When** any of the workflows in §7 is exercised via `missionctl`, **Then** every command talks to the API over HTTP using the logged-in user's token — no command reads the database directly — so the CLI is genuinely a client proving the API surface, not a shortcut around it. |
| FR-19 | Seed data | Must | **Given** a fresh database, **When** the seed script runs, **Then** it creates ≥2 organisations, each with a Director, ≥2 Mission Leads, a roster of ≥6 crew with varied skills/proficiencies/availability, an org-specific skill taxonomy, and missions in at least three different lifecycle states — enough to demonstrate tenant isolation and a non-trivial matcher run without any manual setup. |
| FR-20 | Validation & error handling | Must | **Given** invalid input at any endpoint (missing field, bad enum, invalid date range, end before start), **Then** the API returns 422 with field-level messages; **Given** an unhandled server error, **Then** the client receives a generic 500 with no stack trace or internal detail, while the full error is logged server-side. |
| FR-21 | Web UI (showcase) | Should | **Given** a logged-in user of any of the three roles, **When** they open the SPA, **Then** they see a mission list → mission detail (requirements, fulfillment, and for Mission Lead/Director a matcher run with ranked candidates and score breakdowns) → propose/approve/reject/accept/decline actions relevant to their role, each applying an optimistic update and showing explicit loading/error states; **Given** a Crew Member, **Then** they see a "my assignments" view scoped to their own proposed/confirmed assignments only. Auth reuses FR-2 (email+password → token in `localStorage`); the API surface is the same action-oriented endpoints the CLI calls, consumed RPC-style via a typed client generated from the API's schema (§10 #21). Scope is 2–3 screens, not CLI parity — mocked data is acceptable outside the real/tested vertical slice (§10 #16–#18, #23). |

### Non-functional

- **Tenant isolation is structural, not just tested.** Every data-access function takes
  the caller's `org_id` as a required parameter (not an optional filter) so it's
  impossible to write a query that accidentally spans tenants; a dedicated test suite
  (§6 FR-1) asserts this at the API boundary, not just the ORM layer.
- **Local runnability.** SQLite file-based storage, no external services (no Postgres,
  no Redis, no Docker *requirement*) — a fresh checkout still runs with just a
  documented `pip install` + one seed command + one run command; Docker (R-4,
  Refinement) is available, not mandatory, since the brief asks for "easy to run
  locally" and a bare-metal checkout is the simpler path to that. SQLite
  (not a habitual database default) fits because the domain is genuinely relational —
  orgs, users, crew, skills, missions, requirements, and assignments with real foreign
  keys and joins — not because a data store was reached for out of convention.
- **Matcher performance.** Correct at the tested scale (tens of crew, single-digit
  requirements per mission) via straightforward filtering + scoring — no external
  solver library. Noted, not built: at real scale, filling many requirements
  simultaneously without one crew member being double-suggested across them would
  benefit from a true assignment-problem solver (e.g. Hungarian algorithm); out of
  scope here (§3 non-goals).
- **Testability.** A `pytest` suite covers the lifecycle state machine, RBAC
  boundaries, tenant isolation, and the matcher's filtering/scoring logic — a handful
  of representative cases per area, not exhaustive coverage (§10 #17) — runnable with
  one command, and referenced as verification evidence in the transcripts.
- **Code structure for a team.** Layered: `api/` (thin route handlers) → `services/`
  (lifecycle transitions, matching algorithm, assignment rules — the actual domain
  logic) → `models/` (SQLModel/SQLAlchemy entities + queries). The CLI and the SPA
  (`web/`) are both separate clients that only speak HTTP/RPC-style calls to the API —
  neither touches business logic or the database directly.
- **Scope fidelity is explicit, not implied.** §10 #17 draws a hard line: auth/RBAC/
  tenant isolation, the mission lifecycle & approval gate, the matcher, and
  assignments are the real, tested vertical slice; crew self-service CRUD and the SPA
  may be lighter-effort or use mocked data where time is short. Recorded here so
  "mocked" never silently expands past what was agreed.
- **Security hygiene.** Tokens and passwords hashed at rest even in this seeded/demo
  auth model; no secret, token, or password ever appears in a log line or an error
  response.

## 7. UX

Explainer artifact: [Mission Control Architecture](https://claude.ai/code/artifact/e14d23aa-0235-4a6d-9bee-1be3edaa7895)
— stack choices and the layered request flow, a faster read than this section's detail.

CLI-only (`missionctl`) is the primary interface, talking to a local FastAPI service
over HTTP and printing pretty-printed JSON (§10 #15). Grouped by workflow, each
command handles success / validation-error / permission-denied / not-found states with
a clear message (never a raw traceback):

- **Auth:** `login <email> <password>` (stores the issued bearer token locally),
  `whoami`.
- **Org & skills (Director):** `skills add <name>`, `skills list`.
- **Crew (Crew Member on self; Director/Lead read-only on others):** `profile show`,
  `profile update`, `skills set <skill> <proficiency>`, `availability add
  <start> <end>`, `availability remove <id>`, `availability list`.
- **Missions (Mission Lead / Director):** `mission create`, `mission add-requirement
  <mission> <skill> <min-proficiency> <headcount>`, `mission submit`, `mission approve
  / reject` (Director only, not-creator only), `mission activate / complete /
  cancel`, `mission show` (status, requirements, fulfillment — FR-17).
- **Matching & assignment:** `match run <mission>` (prints ranked candidates per
  requirement with score breakdown), `assign propose <mission> <requirement>
  <crew>`, `assign respond <assignment> accept|decline` (crew member).
- **Listing:** `mission list`, `crew list` (Director/Lead only — FR visibility rules),
  `assignment list` (scoped to caller's role — a crew member sees only their own).

**Web UI (`web/`, showcase only — FR-21):** a minimal React SPA hitting the same API.
Login reuses FR-2 (email + password → bearer token in `localStorage`). Screens are
role-conditional on the logged-in user (§10 #23), not a full app. Mockups:
[Mission Control SPA Mockups](https://claude.ai/code/artifact/de0b0bf5-d39d-4a2b-8392-1ac4339bd93a)
(source: `docs/design/spa-mockups/`):

- **Mission list → mission detail** (Mission Lead / Director) — requirements,
  fulfillment, a matcher run with ranked candidates and score breakdowns, and
  propose/approve/reject actions with optimistic updates and visible loading/error
  states.
- **My assignments** (Crew Member) — accept/decline a proposed assignment.

Server state via React Query; local UI state via `useState`. No routing depth, no
settings, no screens beyond these two — this is a state-management showcase (§10 #16,
#18), not CLI parity; the CLI remains the system of record for FR-18 (§10 #19).

## 8. Constraints & dependencies

- **Language/stack:** Python for the API — FastAPI, SQLModel (SQLAlchemy + Pydantic)
  for models and validation, SQLite as the store, Typer for the CLI (pairs naturally
  with FastAPI's type-hint style and Pydantic schemas), `httpx` for the CLI's HTTP
  client, `pytest` for tests. React + Vite for the showcase SPA (`web/`, FR-21), with a
  typed client generated from the API's OpenAPI schema for RPC-style DX (§10 #21),
  React Query for server state, and Tailwind CSS for styling (§10 #25) — utility
  classes are fast to build 2-3 screens with and skip hand-rolling a component
  stylesheet nobody will reuse past this showcase. Matches Mutinex's internal stack
  (TypeScript, React, Python, GCP).
- **Coding constraints (backend).** Decided up front so `python-programmer` isn't
  guessing mid-task:
  - **Synchronous, not async.** Plain `def` route handlers and a synchronous
    SQLAlchemy session — at this scale (tens of crew, single-digit requests) async
    buys nothing and an async SQLite driver (`aiosqlite`) is one more thing that can
    go wrong in a 3–5h build. Revisit only if a real concurrency need shows up.
  - **Type hints on every function signature**, checked by the editor/IDE as you
    go — not wired into a separate CI type-check step (`mypy`/`pyright`); one more
    tool to configure that doesn't change what ships, given the timebox.
  - **`ruff`** for both lint and format — one tool, one config file, not a
    lint/format pair to keep in sync.
  - **No bare `except:`.** Every caught exception is either handled meaningfully or
    re-raised — silently swallowing one is how FR-20's "no stack traces leaked, full
    detail logged server-side" quietly stops being true.
  - **Tests run against a real temporary SQLite database, not mocks** — a fresh file
    (or in-memory DB) per test session via a `pytest` fixture. Mocking the DB layer
    would mean the "representative test cases" (§10 #17) prove the mocks behave as
    expected, not that tenant isolation or the state machine actually hold.
- **No external infrastructure.** SQLite file, no queue, no cache, no cloud dependency —
  deliberately, given the timebox and "easy to run locally" requirement.
- **CORS is enabled, wide open** (R-2, added during T8 — not anticipated in the original
  Discovery-stage PRD, since nothing before T8 was a browser client). The SPA calling
  the API cross-origin needs it or every request 405s on preflight. Safe to leave
  wide-open here: auth is a bearer token in a header, not a cookie, so there's no
  ambient credential a stricter origin allowlist would actually protect.
- **A LAN-only demo instance runs on Leslie's NAS** (R-5, Refinement) — API on
  `192.168.1.176:8100`, SPA on `:8101`, both from the images R-4 publishes to GHCR.
  The SPA's image is tagged separately (`nas`, not `latest`) since `VITE_API_BASE_URL`
  bakes into its static JS bundle at build time — the URL that's correct for this
  network isn't the one `:latest`'s local-dev build uses. Not internet-facing, not
  part of the submission, purely a convenience for testing against something real
  instead of a local dev server.
- **Auth is intentionally minimal.** A real `POST /auth/login` (email + password)
  endpoint issues opaque bearer tokens, hashed at rest; passwords hashed too. No
  OAuth/SSO/session-refresh/password-reset/email-verification — see §3 non-goals
  (§10 #24).
- **AI transcripts are a submission deliverable, not incidental.** Mutinex requires
  "every conversation with your AI coding tool during the challenge, unedited." Since
  Leslie's normal build uses subagents in git worktrees (per his standing delivery
  workflow), that means **every** subagent's transcript — not just the main session's —
  needs exporting into `transcripts/` in this repo before submission. This is tracked
  as an explicit task in §11/§12, not assumed to happen automatically. Convention:
  each session gets a dated pair — `transcripts/<date>-<short-desc>.jsonl` (the raw,
  unedited Claude Code session record, copied verbatim from
  `~/.claude/projects/.../<session-id>.jsonl`) and the same name as `.md` (a faithful
  human-readable rendering). See `transcripts/2026-09-14-prd-discovery-grilling.{md,jsonl}`
  for the first instance (the Discovery grilling session itself).
- **This repo is the whole submission package.** Design doc (this file), source, seed
  data, README, and transcripts all live here, since the repo itself (public) is what
  gets shared with Mutinex — nothing about this build is split across Leslie's private
  `ai-docs` repo.
- **Greenfield repo** — no existing code to match; follows Leslie's global `CLAUDE.md`
  backend defaults (validate at the boundary, meaningful status codes, no leaked stack
  traces, layered architecture) adapted to Python since there's no Python-specific
  house style yet.

## 9. Analytics & instrumentation

N/A — a solo, one-shot evaluated challenge with no real users. Structured logging exists
only for local debugging and to demonstrate the "no stack traces leaked, full detail
logged server-side" requirement (FR-20), not for product analytics.

## 10. Open questions

All resolved via `grill-me` (Discovery grilling, 2026-09-14 — round-by-round record in
§14). Kept here as the decision reference the rest of this document links back to.

| # | Question / decision needed | Why it matters | Resolved decision | Owner |
|---|----------------------------|----------------|--------------------|-------|
| Q1 | Proficiency scale representation | Drives FR-6, FR-13 scoring math | Integer 1–5 scale, stored as an int; display labels (e.g. "Novice"..."Expert") are a presentation-layer mapping, not a separate field. | Leslie |
| Q2 | Availability granularity + editability | Drives FR-7 and the matcher's date overlap logic | Date-range unavailability windows (not hourly). Plus: `availability remove <id>` added (delete-only, no edit) — the original CLI surface had no way to fix a mis-entered window. | Leslie |
| Q3 | Per-crew workload cap | Whether the matcher/guard need a hard concurrent-assignment ceiling | No hard cap — workload is a *soft* scoring factor (FR-13), not a hard filter. FR-16's double-booking guard is the actual hard constraint that matters. | Leslie |
| Q4 | Mission activation/completion trigger | Whether transitions are date-driven or explicit actions | Explicit CLI actions only (FR-12) — no scheduler/cron. | Leslie |
| Q5 | Does under-staffing block activation? | FR-17's teeth | No — surfaced, not enforced. | Leslie |
| Q6 | Matcher output granularity | Whole-mission plan vs. per-requirement rankings | Per-requirement ranked suggestions (FR-13); explainability is part of the evaluation, not just algorithmic sophistication. | Leslie |
| Q7 | Skill taxonomy structure | Flat vs. hierarchical/categorized | Flat, org-scoped list (name + optional free-text category tag). | Leslie |
| Q8 | Self-approval rule scope | Exactly what FR-11 blocks | Identity check only: `approver.id != mission.created_by_id`, role-agnostic. | Leslie |
| Q9 | Matcher scoring formula | FR-13 said "weighted score" with no weights, normalization, or result cap defined anywhere | Each factor normalized 0–1, combined at fixed weights 50% proficiency surplus / 30% workload / 20% availability margin (not user-tunable). Returns **all** eligible candidates, no top-N cap. | Leslie |
| Q10 | Token issuance mechanism | §8 floated an optional Director "invite" endpoint alongside seed-time issuance | Superseded by Q24 — a real login endpoint replaces seed-time-only issuance entirely. | Leslie |
| Q11 | Does every user have a crew profile, or only Crew Members? | Never stated explicitly; determines who's matchable | Only the Crew Member role holds a skill/availability profile and can be matched/proposed/assigned. Directors and Leads are administrative-only. | Leslie |
| Q12 | Can mission requirements be edited once submitted? | §7's CLI only ever had `add-requirement`, no edit/remove | Requirements are frozen once a mission leaves `draft`. To change them, reject back to `draft` first, edit there, resubmit. | Leslie |
| Q13 | Mission status when a decline reopens headcount on an approved mission | FR-15's interaction with FR-9/FR-17 was undefined | No automatic status change — the mission stays `approved`/`active`; FR-17 just shows a lower confirmed-vs-needed count and the Lead proposes a replacement. | Leslie |
| Q14 | Timebox cut line | §11's 9-step rollout is a lot for 3–5h; agreed on "build simple for demo" | Cut order if squeezed: (1) FR-17 fulfillment-visibility polish beyond the bare count, (2) seed-data richness beyond FR-19 minimums, (3) CLI formatting/ergonomics, (4) the SPA's Crew Member screen — never tenant isolation, RBAC, the approval gate, or matcher correctness. | Leslie |
| Q15 | CLI output format | Plain text tables vs. JSON | JSON, pretty-printed. | Leslie |
| Q16 | Web UI: how much, and at what cost? | Brief says a web UI isn't required; original §3/§7 explicitly excluded one | A minimal showcase SPA is in scope (FR-21) — not full implementation, mocked endpoints welcome outside the real vertical slice (Q17). Not CLI parity. | Leslie |
| Q17 | Real/mock boundary on the backend, and the testing bar | "Vertical slice over breadth" needed an explicit line once the SPA and lighter-effort areas entered scope | Real & tested: auth/RBAC/tenant isolation (FR-1–3) + lifecycle & approval gate (FR-8–12) + matcher (FR-13) + assignments/double-booking (FR-14–16) — one coherent story: create → match → propose → accept → approve. Lighter/mockable: crew self-service CRUD (FR-4–7). Test bar: a handful of representative cases per critical area, not exhaustive suites. | Leslie |
| Q18 | What the SPA needs to show | "Showcase React state management," not full product coverage | 2–3 screens: mission list → detail (requirements, fulfillment, matcher run with score breakdowns) → propose/approve with optimistic updates and visible loading/error states. | Leslie |
| Q19 | Does the SPA replace or supplement the CLI for FR-18? | FR-18 requires every primary workflow via CLI | CLI stays the system of record for FR-18 coverage; the SPA is additional, narrower. | Leslie |
| Q20 | SPA state-management approach | What to showcase | React Query for server state, plain `useState` for local UI state — no Redux/Zustand. | Leslie |
| Q21 | SPA↔API communication style ("RPC") | Backend is Python/FastAPI, not a natural fit for TS-native RPC (tRPC) | RPC-flavored DX over the existing action-oriented endpoints (`submit`/`approve`/`activate`/`propose`/`respond` — already RPC-shaped, not resource CRUD), via a typed client generated from the API's OpenAPI schema. Same REST wire underneath; no second protocol, no BFF layer; the CLI hits the exact same endpoints. | Leslie |
| Q22 | SPA authorization endpoint | Whether the browser needs a distinct auth surface from the CLI | Superseded by Q24 — the browser uses the same real login endpoint as the CLI, not a separate mechanism. | Leslie |
| Q23 | Which roles does the SPA cover? | The domain has three roles with genuinely different views (§4) | All three, conditionally rendered off the logged-in user's role (mirrors API RBAC). Adds a Crew Member "My Assignments" accept/decline screen; first thing cut if time is short (Q14). | Leslie |
| Q24 | Auth mechanism: tokens vs. real login | Originally scoped as seed-issued static tokens (Q10); reversed after reviewing the shape of the auth flow | Real `POST /auth/login` (email + password), passwords hashed at rest (bcrypt/argon2), returns an opaque bearer token used on subsequent requests — same FR-2 token mechanics, different issuance. One shared model for both CLI (`login <email> <password>`) and SPA. Seed script generates and documents demo passwords. Still fits inside §3's Non-goals boundary — no OAuth/SSO/refresh/reset, just a real login instead of a pre-issued token. | Leslie |
| Q25 | SPA styling approach | Undecided since FR-21 was added — hand-rolled CSS vs. a utility framework | Tailwind CSS. Fast to build 2-3 screens with utility classes; no component stylesheet to maintain past this showcase, no design-token system to build for something this small. | Leslie |
| Q26 | Duplicate propose — same crew member twice on one requirement | Surfaced during T6 (R-3, Refinement) — FR-14 doesn't say whether proposing the same crew member for a requirement they're already `proposed`/`confirmed` on should be blocked; today it silently creates a second row, consuming a second headcount slot for one person | **Open — not yet decided.** No guard built; flagged rather than silently fixed since it's a real gap, not obviously wrong either way for a take-home's scope. Leslie to decide: block it (409, "already proposed/confirmed"), or leave as-is since nothing in FR-14 forbids it and it's an edge case a Lead is unlikely to hit by accident. | Leslie |
| Q27 | Concurrent-request races on the headcount/overlap guards (FR-14, FR-16, FR-7) | Surfaced in Finalize's `/code-review high` on PR #22 — `propose_assignment`, `respond_to_assignment`'s accept path, and `add_availability_window` each do a check (headcount / double-booking / overlap) and the write as two separate, unlocked steps. Two genuinely concurrent requests (two tabs, a client retry) can both pass the check before either commits, silently violating the guard. | **Open — not fixed.** None of FR-7/FR-14/FR-16 ever specified concurrent-request behavior, and closing this needs an explicit locking/transaction strategy (SQLite has no real row-level locking), which is a design decision, not a one-line fix — out of scope for a take-home's "representative test cases, not exhaustive coverage" bar (§10 #17), and this system's only live traffic is one person clicking through a LAN demo. Flagged rather than silently accepted: a genuinely concurrent-request test would need to be added alongside whatever guard is built, when this gets picked up. | Leslie |

## 11. Rollout

Not a phased product release — this is the build order for a single timeboxed
implementation pass, doubling as the structure `/tasks` will turn into issues:

1. **Scaffold** — project layout, config, DB models/migrations for org/user/crew/skill,
   seed script skeleton.
2. **Auth + RBAC + tenant scoping** — the boundary everything else depends on (FR-1–3),
   including the real login endpoint (§10 #24). Part of the real, tested vertical
   slice (§10 #17).
3. **Crew management** — profile, org-scoped skills, availability incl. `availability
   remove` (FR-4–7). Lighter-effort scaffolding (§10 #17), not a testing priority.
4. **Mission lifecycle + approval** — CRUD, requirements, state machine, the
   self-approval gate (FR-8–12, FR-17). Vertical slice.
5. **Matching engine** — the part "real thought about the problem space" is judged on;
   built and tested in isolation before wiring it to assignments (FR-13, weights per
   §10 #9). Vertical slice.
6. **Assignments** — propose from a match, crew response, double-booking guard
   (FR-14–16). Vertical slice.
7. **CLI** — wraps the full API surface as an HTTP client, JSON output (FR-18, §10
   #15). Remains the system of record for CLI coverage (§10 #19).
8. **Web UI showcase** — minimal React SPA (FR-21): mission list → detail → matcher/
   propose/approve, plus Crew Member's accept/decline screen; React Query, typed
   client over the existing endpoints (§10 #16–#23). First thing trimmed if time is
   short (§10 #14).
9. **Seed data, README, end-to-end verification** — representative multi-tenant seed
   (FR-19) incl. documented demo passwords (§10 #24), setup instructions, a full
   manual run-through of every workflow in §7.
10. **Transcript packaging** — export every AI-tool conversation (main session +
    any subagents) unedited into `transcripts/`, before final submission. Convention
    and the first instance already in place (§8) — refresh/add dated pairs to cover
    everything after this Discovery grilling session.

**Back-out:** N/A — a one-shot submission with no production system behind it. If a
requirement proves too large for the timebox, the brief's own guidance governs: cut
breadth, keep a coherent, verified vertical slice, and say so plainly in this document
rather than silently shipping less than what's written above.

## 12. Tasks

**Progress:** 10 tasks · 10 done (100%) — plus ad hoc Refinement-stage work (T8b, T11 — see
`## 13. Refinement log`; not tracked as GitHub issues, since they postdate Development)

Milestone: [Mission Control](https://github.com/leslielee888888/mission-control/milestone/1) (10/10 closed) ·
Project: [Mission Control](https://github.com/leslielee888888/mission-control/projects/8) (owner: leslielee888888)

| ID | Task | Reqs | Owner | Depends on | Issue | Status |
|----|------|------|-------|------------|-------|--------|
| T1 | Scaffold — project layout, DB models, seed skeleton, error handling | FR-20 | `python-programmer` | — | [#1](https://github.com/leslielee888888/mission-control/issues/1) | done |
| T2 | Auth + RBAC + tenant scoping | FR-1, FR-2, FR-3 | `python-programmer` | T1 | [#2](https://github.com/leslielee888888/mission-control/issues/2) | done |
| T3 | Crew management — profile, skills, availability | FR-4, FR-5, FR-6, FR-7 | `python-programmer` | T2 | [#3](https://github.com/leslielee888888/mission-control/issues/3) | done |
| T4 | Mission lifecycle + approval gate | FR-8, FR-9, FR-10, FR-11, FR-12, FR-17 | `python-programmer` | T2 | [#4](https://github.com/leslielee888888/mission-control/issues/4) | done |
| T5 | Matching engine — retrieval + ranking | FR-13 | `python-programmer` | T3, T4 | [#5](https://github.com/leslielee888888/mission-control/issues/5) | done |
| T6 | Assignments — propose, respond, double-booking guard | FR-14, FR-15, FR-16 | `python-programmer` | T5 | [#6](https://github.com/leslielee888888/mission-control/issues/6) | done |
| T7 | CLI (`missionctl`) — full workflow coverage | FR-18 | `python-programmer` | T2, T3, T4, T5, T6 | [#7](https://github.com/leslielee888888/mission-control/issues/7) | done |
| T8 | Web UI showcase SPA | FR-21 | `fe-programmer` | T2, T4, T5, T6 | [#8](https://github.com/leslielee888888/mission-control/issues/8) | done |
| T9 | Seed data, README, end-to-end verification | FR-19 | `python-programmer` | T7 | [#9](https://github.com/leslielee888888/mission-control/issues/9) | done |
| T10 | Transcript packaging | — | Leslie | T9 | [#10](https://github.com/leslielee888888/mission-control/issues/10) | done |

## 13. Refinement log`; not tracked as GitHub issues, since they postdate Development)

Milestone: [Mission Control](https://github.com/leslielee888888/mission-control/milestone/1) (10/10 closed) ·
Project: [Mission Control](https://github.com/leslielee888888/mission-control/projects/8) (owner: leslielee888888)

| ID | Task | Reqs | Owner | Depends on | Issue | Status |
|----|------|------|-------|------------|-------|--------|
| T1 | Scaffold — project layout, DB models, seed skeleton, error handling | FR-20 | `python-programmer` | — | [#1](https://github.com/leslielee888888/mission-control/issues/1) | done |
| T2 | Auth + RBAC + tenant scoping | FR-1, FR-2, FR-3 | `python-programmer` | T1 | [#2](https://github.com/leslielee888888/mission-control/issues/2) | done |
| T3 | Crew management — profile, skills, availability | FR-4, FR-5, FR-6, FR-7 | `python-programmer` | T2 | [#3](https://github.com/leslielee888888/mission-control/issues/3) | done |
| T4 | Mission lifecycle + approval gate | FR-8, FR-9, FR-10, FR-11, FR-12, FR-17 | `python-programmer` | T2 | [#4](https://github.com/leslielee888888/mission-control/issues/4) | done |
| T5 | Matching engine — retrieval + ranking | FR-13 | `python-programmer` | T3, T4 | [#5](https://github.com/leslielee888888/mission-control/issues/5) | done |
| T6 | Assignments — propose, respond, double-booking guard | FR-14, FR-15, FR-16 | `python-programmer` | T5 | [#6](https://github.com/leslielee888888/mission-control/issues/6) | done |
| T7 | CLI (`missionctl`) — full workflow coverage | FR-18 | `python-programmer` | T2, T3, T4, T5, T6 | [#7](https://github.com/leslielee888888/mission-control/issues/7) | done |
| T8 | Web UI showcase SPA | FR-21 | `fe-programmer` | T2, T4, T5, T6 | [#8](https://github.com/leslielee888888/mission-control/issues/8) | done |
| T9 | Seed data, README, end-to-end verification | FR-19 | `python-programmer` | T7 | [#9](https://github.com/leslielee888888/mission-control/issues/9) | done |
| T10 | Transcript packaging | — | Leslie | T9 | [#10](https://github.com/leslielee888888/mission-control/issues/10) | done |

### T1 — Scaffold

- [ ] Layout follows `routes → services → models` (§6 NFR)
- [ ] DB models exist for all 10 tables in the data model
- [ ] Invalid input → 422 with field-level messages (FR-20)
- [ ] Unhandled error → generic 500, full detail logged server-side, never leaked (FR-20)
- [ ] Seed script skeleton (fleshed out in T9)
- [ ] Synchronous route handlers + synchronous SQLAlchemy session (§8 coding constraints)
- [ ] `ruff` configured for lint + format; type hints on all function signatures
- [ ] `pytest` fixture standing up a real temporary SQLite DB per test session (not mocked)

### T2 — Auth + RBAC + tenant scoping

- [ ] Every record carries `org_id` from the authenticated caller, never client input (FR-1)
- [ ] Cross-org record access → 404, not 403 (FR-1)
- [ ] Real `POST /auth/login` (email + password) issues a bearer token; `missionctl login` too (FR-2, §10 #24)
- [ ] Missing/invalid token or wrong credentials → 401 (FR-2)
- [ ] Disallowed role → 403 naming the required role, no side effect (FR-3)
- [ ] Test: org A cannot read/write org B's data even with a valid token

### T3 — Crew management

- [ ] Crew edits own profile; Director/Lead view-only on others (FR-4)
- [ ] Director creates org-scoped, name-unique skills (FR-5)
- [ ] Proficiency 1–5 set per crew/skill, visible to Leads/Directors (FR-6)
- [ ] Non-overlapping availability windows, default-available (FR-7)
- [ ] `availability remove <id>` — delete-only (FR-7, §10 #2)

### T4 — Mission lifecycle + approval gate

- [ ] Mission create (draft) + requirements (FR-8)
- [ ] 6-state machine; invalid transition → 409, unchanged (FR-9) — one table-driven executor, not six handlers
- [ ] `submit` requires ≥1 requirement (FR-10)
- [ ] Non-creator Director approves; creator → 403; reject requires reason, returns to draft (FR-11)
- [ ] `activate`/`complete` explicit actions (FR-12)
- [ ] Fulfillment visible; under-staffing never blocks activation (FR-17)

### T5 — Matching engine

- [ ] Retrieval: 3 independent hard-filter predicates, not one compound condition (FR-13a)
- [ ] Ranking: 50/30/20 weighted, normalized 0–1, independent Strategy functions (FR-13b, §10 #9)
- [ ] Every eligible candidate returned, no cap, each with score + breakdown (FR-13c)
- [ ] Date-overlap helper shared with T6, not duplicated
- [ ] Representative test cases (§10 #17)

### T6 — Assignments

- [ ] Propose up to headcount; over-headcount rejected (FR-14)
- [ ] Accept → confirmed; decline → declined, headcount reopened (FR-15)
- [ ] Confirming over a conflicting confirmed assignment → 409 naming the conflict (FR-16)

### T7 — CLI

- [ ] Every §7 workflow via `missionctl` over HTTP, no direct DB reads (FR-18)
- [ ] JSON output, pretty-printed (§10 #15)
- [ ] System of record for CLI coverage — SPA is additional (§10 #19)

### T8 — Web UI showcase SPA

- [ ] Login (email+password → token in `localStorage`) (FR-21, §10 #24)
- [ ] Mission list → detail (requirements, fulfillment, matcher run) (FR-21)
- [ ] Propose/approve/reject with optimistic updates + loading/error states (FR-21, §10 #18)
- [ ] My Assignments (accept/decline), role-conditional (FR-21, §10 #23)
- [ ] React Query, `useState`, Tailwind, generated typed client (§10 #20/#21/#25)
- [ ] 2–3 screens, mocked data OK outside the vertical slice (§10 #16–#18)

### T9 — Seed data, README, end-to-end verification

- [ ] ≥2 orgs, Director + ≥2 Leads + ≥6 crew each, org skill taxonomy, missions in ≥3 states (FR-19)
- [ ] Demo passwords generated and documented (§10 #24)
- [ ] README: clean-checkout setup steps
- [ ] Manual run-through of every §7 workflow

### T10 — Transcript packaging

- [x] Every session (main + every subagent, incl. T8's `fe-programmer`) exported unedited to `transcripts/` (§8) — 19 subagent transcripts (9 build tasks + the mockup review + the 9-agent `/code-review` run on PR #11) plus the full main session, see `transcripts/README.md`
- [x] Refresh/add pairs covering everything after the Discovery grilling session

## 13. Refinement log

Appended during the Refinement stage — reached automatically once every T1–T10 task
merged into `feature/mission-control`. Three findings, all documentation catching up
to already-shipped, correct implementation (or an honestly-flagged open edge case) —
nothing here required new code.

| ID | Date | Finding | Change made | Loop back to Development? |
|----|------|---------|-------------|--------------------------|
| R-1 | 2026-09-15 | FR-13's availability-margin scoring factor had no defined formula — §10 #9 fixed only the three weights (50/30/20), not how margin itself is computed. T5 had to define one to ship. | Documented the exact formula (`min(gap_days, 30) / 30`) in FR-13's acceptance criteria, referencing `services/matcher.py`. | No — implementation already correct; PRD just hadn't caught up. |
| R-2 | 2026-09-15 | CORS was never addressed anywhere in the Discovery-stage PRD, since nothing before T8 was a browser client. T8 hit a hard blocker (every API call 405'd on preflight) until it was added. | Added a §8 Constraints bullet documenting CORS is enabled wide-open, with the reasoning (bearer token in a header, not a cookie — no ambient credential a stricter allowlist would protect). | No — same reasoning, just undocumented until now. |
| R-3 | 2026-09-15 | FR-14 doesn't say whether proposing the same crew member twice on one requirement should be blocked. T6 flagged it rather than silently deciding; today it's allowed, consuming two headcount slots for one person. | Added as a new open question, §10 Q26 — genuinely undecided, not folded into a "correct by default" answer. | No — not material enough to block Finalize; Leslie's call whenever it's convenient, a small guard if the answer is "block it." |
| R-4 | 2026-09-15 | Post-Refinement request: a CI gate (lint + test on every PR) and Docker images for the API and SPA, published to a registry. Not part of the original Discovery-stage scope — §3/§8 had explicitly framed Docker as optional and deployment as fully out of scope. | Added `.github/workflows/ci.yml` (ruff+pytest, oxlint+tsc+vite build, gating PRs into `main`/`feature/mission-control`) and `.github/workflows/docker-publish.yml` (builds + pushes `Dockerfile`/`web/Dockerfile` to GHCR on push, using the built-in `GITHUB_TOKEN` — no new secrets/accounts). Both images built and run-verified locally before commit. §3 and §8 reworded: containerized/CI-gated is not the same claim as hosted — still no live deployment target. | No — additive tooling, doesn't change any FR; committed directly to `feature/mission-control`, same as R-1/R-2/R-3. |
| R-5 | 2026-09-15 | Post-Refinement request: actually deploy the running system (not just publish images) — to Leslie's own Synology NAS, per his standing `nas-deploy` workflow. This directly reverses R-4's own "still no live deployment target" line and §3's "there is no NAS/cloud target for a take-home challenge," both written earlier the same day. | Added `docker-compose.yml`/`docker-compose.build.yml`/`.env.example`; stood up on the NAS at `192.168.1.176` — API on `:8100` (SQLite persisted in a named volume, seeded via a one-off `docker compose exec`), SPA on `:8101` as a separate `nas`-tagged image (`VITE_API_BASE_URL` bakes into the static bundle at build time, so it's a distinct image from the `:latest` used for local dev, not a runtime config swap). Verified end to end: `/health` reachable, SPA's bundled JS confirmed pointing at the NAS's own API URL, not `localhost`. §3 reworded again: a **LAN-only, personal, demo instance now exists** — still not a public/cloud target, which is what "no NAS/cloud target" was actually guarding against (the brief's scoring is on the repo + design doc + transcripts, not uptime of a hosted instance). | No — infrastructure only, no FR changed; not part of what gets evaluated, but real enough that the PRD should say it plainly rather than let §3 go stale a second time in one day. |
| R-6 | 2026-09-15 | Post-Refinement request: scale the seed data up (Org 1: 50 crew, 10 missions spanning every lifecycle state) and make it self-populating (`docker compose up -d` alone should give a working instance, no manual seed step) — for a reviewer landing on the repo cold. FR-19 only ever specified a *minimum* (≥2 orgs, ≥6 crew, ≥3 states); this is well above the floor, not a change to it. | Rewrote Org 1 in `scripts/seed.py` (54 users, 10 missions across all 6 FR-9 states, 18% of crew carry an availability window so the matcher's hard filter has real exclusions, 8 confirmed assignments for real workload data); Org 2 left untouched, deliberately — the size contrast is a better tenant-isolation demonstration than two similarly-sized orgs. Added `docker/entrypoint.sh`: seeds only if the db file doesn't exist yet, so a restart of an already-populated container never wipes it — verified directly (create a mission, restart, confirm it survives) with the NAS's own absolute-path `MISSION_CONTROL_DATABASE_URL`, not just the local default. Redeployed to the live NAS instance on top of this: wiped the old `mission-control_data` volume (Leslie's go-ahead — it held only demo data), re-pulled the new `:latest`/`:nas` images, confirmed via logs and a live login that the fresh instance actually holds 50 crew and 10 missions, not just that the code path exists. | No — FR-19's floor is unchanged, this is additive richness plus an onboarding improvement. |
| R-7 | 2026-09-15 | Same Refinement request's third part: remove duplicated docs (`TEST_CREDENTIALS.md` vs `seed_credentials.txt`) and bring the README up to date for a reviewer working cold. | Deleted `TEST_CREDENTIALS.md` (gitignored, never tracked — its two-table local-vs-NAS structure is what caused the login mix-up R-5 didn't anticipate); `seed_credentials.txt` (also gitignored, generated fresh by every seed run) is now the one source of demo credentials. Rewrote `README.md`: Docker quick-start, a "For reviewers" section pointing at the design doc/explainer/transcripts, and a Seed data section written to reference `scripts/seed.py`'s own docstring rather than hardcode counts, so it wouldn't drift when the counts changed (confirmed post-R-6 that it didn't need editing). | No — docs-only. |
| R-8 | 2026-09-15 | Even after R-7 removed the *duplicated* credentials doc, the underlying mismatch R-5 hit could still recur: `scripts/seed.py` generated a fresh random password per user on every run (`secrets.token_urlsafe`), so local, CI, and the NAS each got their own independent set — the same user's password was never actually the same in two places, only documented in one place per environment. | First pass derived a per-user password deterministically from the email (SHA-256-based); Leslie simplified further — a single static `DEMO_PASSWORD` for every seeded user, since this is pure demo/test data and per-user secrecy buys nothing there, while one fixed password removes lookup entirely. Verified: reseeded locally twice, confirmed the same password both times and across every user; full test suite (137 tests) still green; reseeded the NAS (`docker compose down -v && pull && up -d`) and confirmed `director.dana@northwind.demo` and other users log in with that same fixed password. | No — same seed-time password-generation contract (§10 #24), just static instead of random; no FR changed. |
| R-9 | 2026-09-15 | Leslie found a genuine gap while testing as a Mission Lead: the backend and CLI already let Mission Lead (or Director) create missions (`require_role(Role.DIRECTOR, Role.MISSION_LEAD)` on `POST /missions`), but the SPA had no "New Mission" affordance at all — `MissionListScreen` had no create button and the API client never wired up a `create` call. Not a permissions bug; the SPA's Q16/Q17 "not full CLI parity" scope had simply never covered mission creation, for either role. | Added `api.mission.create` to the client, a new `MissionCreateScreen` (name/description/start/end date, client-side end>=start validation mirroring the API's own check), and a "New Mission" button on `MissionListScreen`; wired into `App.tsx` as a third state alongside the missions list/detail (still no router, per §7's "no routing depth"), landing on the new mission's detail screen on success. Verified live in the browser, logged in as a Mission Lead (not a Director): created a mission end to end, watched it appear in the list (count 10→11, Draft 2→3). Typecheck, lint, and the full backend test suite (137 tests) all green. Rolling it out to the NAS surfaced a process gap R-4/R-5 hadn't caught: `docker-publish.yml` only ever builds the web image's `:latest`/`:<sha>` tags (pointed at `localhost` for local dev); the NAS's `:nas` tag — `VITE_API_BASE_URL` baked to the NAS's own LAN address — was a one-off manual build during R-5 that CI never touches again. So a NAS `docker compose pull` after a pure SPA change silently keeps serving the *old* bundle. Built and pushed a fresh `:nas` image by hand this time (confirmed the baked URL first by inspecting the running container's own JS bundle, not by guessing) and confirmed the new bundle landed. Documenting this so the next SPA-touching change doesn't quietly ship code to the NAS that isn't actually there — a proper fix (a second CI job building `:nas` with its own `VITE_API_BASE_URL`) is a reasonable follow-up but out of scope for this Refinement pass. | No — closes a scope gap in the SPA, doesn't change any FR or the API/CLI (which already supported this). |
| R-10 | 2026-09-16 | Finalize's `/code-review high` on PR #22 (the whole `feature/mission-control` → `main` diff, 129 files) — 10 findings after verification; 2 refuted (a duplicate-error-class false positive with no live cross-module catch mismatch, and R-8's static demo password, which was an explicitly discussed and accepted decision, not an unflagged one). | Fixed the real, cheap ones directly: `cli/main.py`'s `_load_session` now treats a corrupted `session.json` as "no session" instead of crashing with a raw traceback (+ a test); `docker-publish.yml` now only moves the `:latest` tag on `main` (`docker/metadata-action`'s `is_default_branch`) — every push still gets an immutable `:<sha>` tag, but a feature-branch push no longer clobbers what a NAS `docker compose pull` lands on; `AuthContext`'s auto-logout effect now checks specifically for a 401 instead of firing on any `whoami` error (a transient network blip or backend 500 was force-logging-out a validly-authenticated user); `App.tsx`'s role routing now explicitly allow-lists `director`/`mission_lead` instead of routing "anything that isn't `crew_member`" to the privileged app; `MissionDetailScreen`'s approve/reject and `MyAssignmentsScreen`'s accept/decline now also invalidate the queries they were leaving stale (the missions list; the affected mission's own detail/fulfillment); `MissionCreateScreen`'s subtitle no longer promises an add-requirement/submit UI that doesn't exist in this showcase — points at the CLI instead. The three concurrent-request race findings (headcount/double-booking/availability-overlap guards) are architecturally deeper — logged as new open question Q27 rather than fixed, same treatment Q26 got. | No — all fixes are bug fixes within already-agreed behavior (no FR's intent changed); Q27 is a genuinely new open question, not a scope change. |
| R-11 | 2026-09-16 | Post-Shipped maintenance (the delivery workflow doesn't say this log stops once §1's Status hits `Shipped`, and letting it go stale here would be the same mistake R-9 already caught once): `ci.yml`'s trigger hardcoded `feature/mission-control` instead of the delivery workflow's actual `feature/<slug>` shape, so any future PRD's feature branch would need this file edited by hand first — never exercised in this build (one PRD, one feature branch) but a real correctness gap in a workflow file meant to generalize. | `branches: [main, feature/mission-control]` → `branches: [main, "feature/**"]` for both `pull_request` and `push`. A `pull_request`'s branch filter matches its *base* branch, so `task/<slug>-t<n>` → `feature/<slug>` PRs were (and remain) covered without `task/**` needing to be listed separately. | No — CI-config only, no FR touched. |
| R-12 | 2026-09-16 | The README's "Fast architecture read" and "For reviewers" sections pointed at the *local* `docs/design/architecture-explainer.html` file path — needing a clone to open — despite it already being a published Claude artifact a reviewer could click straight into. The SPA mockups artifact wasn't linked from the README at all, only from this PRD. | Added the live artifact links (explainer + mockups) alongside the existing local-file references in the README's summary and "For reviewers" sections. Both artifacts were private (owner-only) at the time — flagged to Leslie, who made them public before this goes to Mutinex. | No — docs-only. |

## 14. Discovery grilling log

Full session transcript: `transcripts/2026-09-14-prd-discovery-grilling.{md,jsonl}`.

| Round | Question | Recommendation | Decision |
|-------|----------|-----------------|----------|
| 1 | Q1 Proficiency scale representation | Integer 1–5, presentation-only labels | Confirmed as proposed |
| 1 | Q2 Availability granularity | Date-range windows | Confirmed as proposed |
| 1 | Q3 Per-crew workload cap | No hard cap, soft factor only | Confirmed as proposed |
| 1 | Q4 Activation/completion trigger | Explicit CLI actions, no scheduler | Confirmed as proposed |
| 1 | Q5 Under-staffing blocks activation? | No — surfaced only | Confirmed as proposed |
| 1 | Q6 Matcher output granularity | Per-requirement ranked suggestions | Confirmed as proposed |
| 1 | Q7 Skill taxonomy structure | Flat + optional category tag | Confirmed as proposed |
| 1 | Q8 Self-approval rule scope | Identity check, role-agnostic | Confirmed as proposed |
| 1 | Q9 Matcher scoring formula (new) | Normalized weights 50/30/20, no result cap | Confirmed as proposed |
| 1 | Q10 Token issuance mechanism (new) | Seed-time only, drop invite endpoint | Later reopened and superseded by Q24 |
| 1 | Q11 User↔crew relationship (new) | Only Crew Members are matchable | Confirmed as proposed |
| 1 | Q12 Requirement mutability after submission (new) | Frozen at `pending_approval`+ | Confirmed as proposed |
| 1 | Q13 Decline reopening headcount on approved mission (new) | No automatic status change | Confirmed as proposed |
| 1 | Q14 Timebox cut line (new) | Cut FR-17 polish → seed richness → CLI formatting first | Confirmed — "build simple for demo" |
| 1 | Q15 CLI output format (new) | Plain text tables | **Changed** — user chose JSON |
| 2 | Q16 Web UI scope | Stay CLI-only (A) | **Changed** — user wants a web UI; opened Q17–Q23 |
| 3 | Q17 Real/mock boundary + test bar | Auth/RBAC/lifecycle/matcher/assignments real & tested; crew CRUD lighter | Confirmed boundary; test bar further softened to "a few representative cases" |
| 3 | Q18 SPA screen scope | Mission list → detail → matcher/propose/approve, 2–3 screens | Confirmed as proposed |
| 3 | Q19 SPA vs. CLI for FR-18 | CLI stays system of record | Confirmed as proposed |
| 3 | Q20 SPA state-management tool | React Query + `useState`, no Redux/Zustand | Confirmed; user added "RPC" for the API layer, prompting Q21 |
| 4 | Q21 SPA↔API "RPC" meaning | (A) Typed client over existing action-oriented REST endpoints, no second protocol | Confirmed (A) — user clarified RPC = "remote procedure call," matching the existing action-oriented endpoint design |
| 5 | Q22 SPA authorization endpoint | (A) Reuse the token-paste model, no new server endpoint | Later reopened and superseded by Q24 |
| 6 | Q23 Which roles does the SPA cover? | (A) All three, conditionally rendered | Confirmed (A) |
| 7 | Q24 Auth mechanism | N/A — user-initiated change from tokens to real login | Real `POST /auth/login` (email + password), one shared model for CLI and SPA — supersedes Q10 and Q22 |
| 8 | Q25 SPA styling approach | N/A — user-initiated addition | Tailwind CSS |
