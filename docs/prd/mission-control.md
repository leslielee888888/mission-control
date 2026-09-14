# PRD: Mission Control

- **Status:** `Draft` → **`Discovery`** → `In development` → `Refinement` → `Finalize` → `Shipped`
- **Author:** Leslie
- **Repo:** [`leslielee888888/mission-control`](https://github.com/leslielee888888/mission-control) — new
  standalone repo, created for this challenge. This doc, the source code, and the full
  unedited AI transcripts all live here, since the whole repo is what gets shared with
  Mutinex (not split across Leslie's private `ai-docs`).
- **Last updated:** 2026-09-14
- **Reviewers:** Leslie (self-owned). This document is also the **design document**
  Mutinex's brief asks for — the artifact "you would use to communicate the intended
  solution to an engineering team and guide an AI coding agent" — submitted alongside
  the code and transcripts.
- **Explainer artifact:** N/A — solo take-home challenge, no team to onboard separately;
  this PRD is itself the document that guides the AI coding agent and the eventual
  reviewer.
- **Design:** N/A — no UI. The brief states "a web interface is not required"; the
  primary workflows are exercised through a CLI (§7).

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
  still demonstrates real judgment (e.g. token auth instead of a full OAuth flow), not
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
with seeded data, no web UI required.

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

- A web UI — explicitly not required by the brief.
- Production-grade auth (OAuth/SSO, password reset, email verification, session
  refresh). Simple bearer tokens issued at seed/creation time are enough to demonstrate
  the RBAC and tenant-isolation boundaries, which are what's being evaluated.
- Globally optimal assignment solving (e.g. Hungarian algorithm across all requirements
  at once). The matcher does per-requirement ranked scoring with hard-constraint
  filtering — real judgment about the problem, without importing an optimisation
  library to solve a scale this system doesn't have yet (see §6 non-functional).
- Notifications (email/push) when a mission is approved or an assignment proposed — the
  CLI/API state is the source of truth; a crew member checks it, they aren't paged.
- Multi-role users, org-to-org collaboration, or missions spanning multiple
  organisations.
- Deployment/hosting — this runs locally against SQLite; there is no NAS/cloud target
  for a take-home challenge.

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
scope it names:

- [ ] A multi-tenant API enforces org scoping on every record and role-based access on
      every endpoint (FR-1–FR-3), with a test proving org A cannot read or write org B's
      data even with a valid token.
- [ ] The mission lifecycle (draft → pending approval → approved → active → completed,
      plus reject/cancel) is enforced server-side, and a Director cannot approve a
      mission they created (FR-9–FR-11).
- [ ] Crew management covers skill profiles (org-scoped taxonomy, per-crew proficiency)
      and availability (FR-4–FR-7).
- [ ] The auto-matching engine filters on hard constraints and ranks on soft factors,
      with visible reasoning per suggestion, covered by tests over the scoring logic
      (FR-13).
- [ ] A CLI exercises every primary workflow — login, crew/skill/availability
      management, mission planning through approval, running the matcher, assignment
      response — entirely by calling the real API (FR-18).
- [ ] The repo runs locally from a clean checkout with documented setup steps and seed
      data demonstrating ≥2 tenants (FR-19).
- [ ] The design document (this file) was written before implementation and is the
      artifact that guided the agent — checked by the grilling log (§14) and the
      refinement log (§13) actually reflecting real back-and-forth.
- [ ] Every AI-tool conversation from the build is captured unedited in `transcripts/`
      in this repo (§8).
- [ ] Commit history on the repo is meaningful (not one squashed blob) and public.

## 6. Requirements

### Functional

| ID | Requirement | Priority | Acceptance criteria (Given/When/Then) |
|----|-------------|----------|----------------------------------------|
| FR-1 | Tenant scoping | Must | **Given** any domain record (user, crew, skill, mission, assignment), **When** it is created, **Then** it carries an `org_id` derived from the authenticated caller, never from client input; **Given** a request for a specific record, **When** its `org_id` doesn't match the caller's, **Then** the API returns 404 (not 403) so a caller can't distinguish "not mine" from "doesn't exist." |
| FR-2 | Authentication | Must | **Given** a seeded user with an issued bearer token, **When** the CLI runs `missionctl login <email>` with that token, **Then** it's stored locally and attached to subsequent requests; **Given** a request with a missing or invalid token, **Then** the API returns 401. Tokens are opaque random strings, hashed at rest. |
| FR-3 | Role-based access control | Must | **Given** an endpoint declares its allowed role(s), **When** a request arrives from an authenticated user whose role isn't allowed, **Then** the API returns 403 with a message naming the required role, and no side effect occurs. |
| FR-4 | Crew profile management | Must | **Given** a crew member, **When** they call `missionctl profile update`, **Then** they can change their own name/contact/bio; **Given** a Director or Mission Lead, **Then** they can view (not edit) any crew member's profile in their org. |
| FR-5 | Org-scoped skill taxonomy | Must | **Given** a Director, **When** they create a skill (`missionctl skills add <name>`), **Then** it's scoped to their org and unique by name within it; **Given** two different orgs, **Then** each can define a skill with the same name independently (no cross-org collision). |
| FR-6 | Crew skill profiles | Must | **Given** a crew member and an org-defined skill, **When** the crew member (or a Director on their behalf) sets a proficiency level (1–5 integer scale), **Then** it's stored on their profile and visible to Mission Leads/Directors in the org; a crew member can hold any number of skills. |
| FR-7 | Crew availability | Must | **Given** a crew member, **When** they add an unavailability window (start/end date), **Then** it's recorded against their profile; absent any window, a crew member defaults to available. Windows can't overlap for the same crew member. |
| FR-8 | Mission creation & requirements | Must | **Given** a Mission Lead (or Director), **When** they create a mission (name, description, start date, end date), **Then** it starts in `draft`; **When** they add a requirement (skill, minimum proficiency, headcount needed), **Then** it's attached to the mission; a mission can have multiple requirements across different skills. |
| FR-9 | Mission lifecycle state machine | Must | **Given** a mission, **Then** its status is one of `draft`, `pending_approval`, `approved`, `active`, `completed`, `cancelled`; **Given** a transition not in the allowed set (`draft→pending_approval`, `pending_approval→approved`, `pending_approval→draft` [reject], `approved→active`, `active→completed`, and `cancelled` from any pre-completed state), **When** it's attempted, **Then** the API returns 409 and the status is unchanged. |
| FR-10 | Submit for approval | Must | **Given** a `draft` mission, **When** its creator calls `missionctl mission submit`, **Then** it moves to `pending_approval` **only if** at least one requirement is defined; with zero requirements, submission is rejected with a clear message. |
| FR-11 | Approval gate — no self-approval | Must | **Given** a `pending_approval` mission, **When** a Director who is **not** the mission's creator approves it, **Then** it moves to `approved`; **When** the mission's own creator (regardless of their role) attempts to approve it, **Then** the API returns 403. Rejection (back to `draft`, with a required reason) follows the same identity check. |
| FR-12 | Activation & completion | Must | **Given** an `approved` mission, **When** a Mission Lead or Director calls `missionctl mission activate` / `...complete`, **Then** it transitions to `active` / `completed`. Transitions are explicit actions, not date-triggered — no scheduler in this build (see §10 open questions). |
| FR-13 | Auto-matching engine | Must | **Given** a mission with requirements, **When** `missionctl match run <mission>` is called, **Then** for each requirement the engine: (a) **hard-filters** crew to those in the same org who hold the required skill at ≥ the minimum proficiency, have no unavailability window overlapping the mission's dates, and have no *confirmed* assignment on another mission with an overlapping date range; then (b) **ranks** survivors by a weighted score — proficiency surplus (their level minus the minimum), current workload (fewer active confirmed assignments scores higher), and availability margin (slack between their free window and the mission's) — and (c) returns each candidate with their score and a one-line breakdown of which factors contributed, not just a bare number. |
| FR-14 | Propose assignment from a match | Must | **Given** matcher output (or any eligible crew member found by other means), **When** a Mission Lead calls `missionctl assign propose <mission> <requirement> <crew>`, **Then** an assignment is created in `proposed` status, up to the requirement's headcount; proposing beyond headcount is rejected. |
| FR-15 | Crew response to assignment | Must | **Given** a `proposed` assignment, **When** the named crew member accepts, **Then** it becomes `confirmed`; **When** they decline, **Then** it becomes `declined` and the requirement's remaining headcount is recalculated so the matcher/lead can fill it from someone else. |
| FR-16 | Double-booking guard | Must | **Given** an assignment is about to become `confirmed`, **When** the same crew member already holds a `confirmed` assignment on a mission with an overlapping date range, **Then** the confirmation is rejected (409) naming the conflicting mission — enforced here as a safety net even though the matcher already filters for it in FR-13, since assignments can also be proposed manually, outside the matcher. |
| FR-17 | Requirement fulfillment visibility | Should | **Given** a mission, **When** its detail is viewed, **Then** each requirement shows confirmed-vs-needed headcount at a glance. Under-staffing does **not** block activation (FR-12) — a lead may knowingly launch short-staffed — it's surfaced, not enforced (see §10 open questions). |
| FR-18 | CLI coverage of primary workflows | Must | **Given** the API is running, **When** any of the workflows in §7 is exercised via `missionctl`, **Then** every command talks to the API over HTTP using the logged-in user's token — no command reads the database directly — so the CLI is genuinely a client proving the API surface, not a shortcut around it. |
| FR-19 | Seed data | Must | **Given** a fresh database, **When** the seed script runs, **Then** it creates ≥2 organisations, each with a Director, ≥2 Mission Leads, a roster of ≥6 crew with varied skills/proficiencies/availability, an org-specific skill taxonomy, and missions in at least three different lifecycle states — enough to demonstrate tenant isolation and a non-trivial matcher run without any manual setup. |
| FR-20 | Validation & error handling | Must | **Given** invalid input at any endpoint (missing field, bad enum, invalid date range, end before start), **Then** the API returns 422 with field-level messages; **Given** an unhandled server error, **Then** the client receives a generic 500 with no stack trace or internal detail, while the full error is logged server-side. |

### Non-functional

- **Tenant isolation is structural, not just tested.** Every data-access function takes
  the caller's `org_id` as a required parameter (not an optional filter) so it's
  impossible to write a query that accidentally spans tenants; a dedicated test suite
  (§6 FR-1) asserts this at the API boundary, not just the ORM layer.
- **Local runnability.** SQLite file-based storage, no external services (no Postgres,
  no Redis, no Docker requirement) — a fresh checkout runs with a documented
  `pip install` + one seed command + one run command. A `Dockerfile`/compose file is a
  nicety, not the primary path, since the brief asks for "easy to run locally." SQLite
  (not a habitual database default) fits because the domain is genuinely relational —
  orgs, users, crew, skills, missions, requirements, and assignments with real foreign
  keys and joins — not because a data store was reached for out of convention.
- **Matcher performance.** Correct at the tested scale (tens of crew, single-digit
  requirements per mission) via straightforward filtering + scoring — no external
  solver library. Noted, not built: at real scale, filling many requirements
  simultaneously without one crew member being double-suggested across them would
  benefit from a true assignment-problem solver (e.g. Hungarian algorithm); out of
  scope here (§3 non-goals).
- **Testability.** A `pytest` suite covers the lifecycle state machine, RBAC boundaries,
  tenant isolation, and the matcher's filtering/scoring logic with fixtures — runnable
  with one command, and referenced as verification evidence in the transcripts.
- **Code structure for a team.** Layered: `api/` (thin route handlers) → `services/`
  (lifecycle transitions, matching algorithm, assignment rules — the actual domain
  logic) → `models/` (SQLModel/SQLAlchemy entities + queries). The CLI is a separate
  package that only speaks HTTP to the API, so a web UI could be added later without
  touching business logic.
- **Security hygiene.** Tokens hashed at rest even in this seeded/demo auth model; no
  secret or token ever appears in a log line or an error response.

## 7. UX

CLI-only (`missionctl`), talking to a local FastAPI service over HTTP. Grouped by
workflow, each command handles success / validation-error / permission-denied /
not-found states with a clear message (never a raw traceback):

- **Auth:** `login <email> <token>` (stores a session locally), `whoami`.
- **Org & skills (Director):** `skills add <name>`, `skills list`.
- **Crew (Crew Member on self; Director/Lead read-only on others):** `profile show`,
  `profile update`, `skills set <skill> <proficiency>`, `availability add
  <start> <end>`, `availability list`.
- **Missions (Mission Lead / Director):** `mission create`, `mission add-requirement
  <mission> <skill> <min-proficiency> <headcount>`, `mission submit`, `mission approve
  / reject` (Director only, not-creator only), `mission activate / complete /
  cancel`, `mission show` (status, requirements, fulfillment — FR-17).
- **Matching & assignment:** `match run <mission>` (prints ranked candidates per
  requirement with score breakdown), `assign propose <mission> <requirement>
  <crew>`, `assign respond <assignment> accept|decline` (crew member).
- **Listing:** `mission list`, `crew list` (Director/Lead only — FR visibility rules),
  `assignment list` (scoped to caller's role — a crew member sees only their own).

## 8. Constraints & dependencies

- **Language/stack:** Python. FastAPI for the API, SQLModel (SQLAlchemy + Pydantic) for
  models and validation, SQLite as the store, Typer for the CLI (pairs naturally with
  FastAPI's type-hint style and Pydantic schemas), `httpx` for the CLI's HTTP client,
  `pytest` for tests. Matches Mutinex's internal stack (they use TypeScript, React,
  Python, GCP) and is Leslie's explicit choice for this build over Node/TS.
- **No external infrastructure.** SQLite file, no queue, no cache, no cloud dependency —
  deliberately, given the timebox and "easy to run locally" requirement.
- **Auth is intentionally minimal.** Bearer tokens issued at seed time (or via an
  admin/director "invite" endpoint that issues one), not a full OAuth/session/refresh
  flow — see §3 non-goals.
- **AI transcripts are a submission deliverable, not incidental.** Mutinex requires
  "every conversation with your AI coding tool during the challenge, unedited." Since
  Leslie's normal build uses subagents in git worktrees (per his standing delivery
  workflow), that means **every** subagent's transcript — not just the main session's —
  needs exporting into `transcripts/` in this repo before submission. This is tracked
  as an explicit task in §11/§12, not assumed to happen automatically.
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

Since nobody but Leslie is available to answer these during the build, each carries a
firm proposed default that the implementation will actually follow — grilling (§14)
either confirms these or changes them before `/tasks` runs.

| # | Question / decision needed | Why it matters | Proposed default | Owner |
|---|----------------------------|----------------|-------------------|-------|
| Q1 | Proficiency scale representation | Drives FR-6, FR-13 scoring math | Integer 1–5 scale, stored as an int; display labels (e.g. "Novice"..."Expert") are a presentation-layer mapping, not a separate field. Simplest sortable representation. | Leslie |
| Q2 | Availability granularity | Drives FR-7 and the matcher's date overlap logic | Date-range unavailability windows (not hourly/calendar-slot). Missions are multi-day operations, not hour-scheduled shifts, so day-granularity is the right resolution and is far simpler to reason about and test. | Leslie |
| Q3 | Per-crew workload cap | Whether the matcher/guard need a hard concurrent-assignment ceiling | No hard cap by default — workload is a *soft* scoring factor (FR-13), not a hard filter. A real ceiling is an org-level setting a Director could add later; out of scope now (a config field would be easy to bolt on, but there's no evidence yet of what a sensible default limit is). | Leslie |
| Q4 | Mission activation/completion trigger | Whether transitions are date-driven or explicit actions | Explicit CLI actions only (FR-12) — no scheduler/cron in this build. Date-driven transitions would need a background process, which is disproportionate machinery for a 3–5 hour build and doesn't change what's being evaluated (the state machine and approval gate, not scheduling). | Leslie |
| Q5 | Does under-staffing block activation? | FR-17's teeth | No — surfaced, not enforced. A real mission lead sometimes launches short-staffed deliberately; hard-blocking would be presumptuous product behaviour without more context on the domain. | Leslie |
| Q6 | Matcher output granularity | Whether the matcher proposes a whole-mission staffing plan or per-requirement rankings | Per-requirement ranked suggestions (FR-13), left for the Mission Lead to act on one at a time via `assign propose`. A whole-mission simultaneous solve (bipartite optimum across all requirements at once) is more "impressive" on paper but harder to explain, test, and verify in the time available — and explainability is explicitly part of what's being evaluated, not just sophistication for its own sake. | Leslie |
| Q7 | Skill taxonomy structure | Whether skills are flat or hierarchical/categorized | Flat, org-scoped list (name + optional free-text category tag), not a hierarchy. Satisfies "different skill taxonomies" per org (FR-5) without building taxonomy management the brief doesn't ask for. | Leslie |
| Q8 | Self-approval rule scope | Exactly what FR-11 blocks | Identity check only: `approver.id != mission.created_by_id`, regardless of whether the creator also happens to hold Director permissions elsewhere. This is the literal, defensible reading of "[Mission Leads] should not be able to approve their own missions" and covers the edge case even if roles turn out not to be strictly exclusive. | Leslie |

## 11. Rollout

Not a phased product release — this is the build order for a single timeboxed
implementation pass, doubling as the structure `/tasks` will turn into issues:

1. **Scaffold** — project layout, config, DB models/migrations for org/user/crew/skill,
   seed script skeleton.
2. **Auth + RBAC + tenant scoping** — the boundary everything else depends on (FR-1–3).
3. **Crew management** — profile, org-scoped skills, availability (FR-4–7).
4. **Mission lifecycle + approval** — CRUD, requirements, state machine, the
   self-approval gate (FR-8–12, FR-17).
5. **Matching engine** — the part "real thought about the problem space" is judged on;
   built and tested in isolation before wiring it to assignments (FR-13).
6. **Assignments** — propose from a match, crew response, double-booking guard
   (FR-14–16).
7. **CLI** — wraps the full API surface as an HTTP client (FR-18).
8. **Seed data, README, end-to-end verification** — representative multi-tenant seed
   (FR-19), setup instructions, a full manual run-through of every workflow in §7.
9. **Transcript packaging** — export every AI-tool conversation (main session +
   any subagents) unedited into `transcripts/`, before final submission.

**Back-out:** N/A — a one-shot submission with no production system behind it. If a
requirement proves too large for the timebox, the brief's own guidance governs: cut
breadth, keep a coherent, verified vertical slice, and say so plainly in this document
rather than silently shipping less than what's written above.

## 13. Refinement log

Appended during the Refinement stage. Empty until then.

| ID | Date | Finding | Change made | Loop back to Development? |
|----|------|---------|-------------|--------------------------|
| — | — | — | — | — |

## 14. Discovery grilling log

Appended during grilling (`grill-me`). Empty until then.

| Round | Question | Recommendation | Decision |
|-------|----------|-----------------|----------|
| — | — | — | — |
