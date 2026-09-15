# Design Pattern Review Report

## Project Summary

| Field | Value |
|-------|-------|
| Language(s) | Python (FastAPI, SQLModel) — backend; TypeScript/React — showcase SPA. Declared in PRD §8; no code exists yet, no language config files present. |
| Mode | Design Doc Review |
| Scope | Full project |
| Design docs reviewed | `docs/prd/mission-control.md` (full PRD), `docs/design/architecture-explainer.html` ("Design patterns" and "Decisions worth knowing" sections) |

---

## Patterns Currently in Use

> Patterns identified in the design documents and an assessment of their usage.

| Pattern | Category | Location | Assessment |
|---------|----------|----------|------------|
| Layered Architecture (N-Tier) | Architectural | PRD §6 NFR "Code structure for a team"; explainer request-flow diagram | Well implemented — clean `routes → services → models` split, explicitly stated as the reason CLI and SPA can both be thin clients with zero business logic. |
| Dependency Injection | Modern | Explainer "Design patterns" §, "Dependency injection" | Well implemented — correctly scoped to FastAPI's built-in `Depends()` (session, current-user, role guard) rather than introducing a DI framework/container this project doesn't need. |
| Repository | Modern | Explainer "Design patterns" §, "Repository" | Well implemented — plain per-entity query functions taking `org_id` explicitly, not a generic `IRepository<T>` interface hierarchy. Correctly justified as unnecessary ceremony given there's exactly one datastore (SQLite) and no second one planned. |
| Singleton | Creational | Explainer "Design patterns" §, "Singleton" | Well implemented — narrowly scoped to the SQLAlchemy engine only (framework-provided, not hand-rolled), with an explicit, correct call-out that services must **not** be singletons in a multi-tenant system (shared mutable state across requests would be a cross-tenant leak vector). This is the strongest entry in the doc — it names both where the pattern applies and, just as importantly, where it doesn't. |
| State | Behavioral | Explainer "Table-driven state machine"; PRD FR-9 | Well implemented — the mission lifecycle (6 states, 7 transitions) is checked against one literal `ALLOWED_TRANSITIONS` table, matching this pattern's textbook trigger ("large `if/else` on a state enum spread across many methods" is exactly the code smell this avoids). |
| Strategy | Behavioral | Explainer "Design patterns" §, "Strategy (one narrow use)"; PRD FR-13 | Well implemented — the matcher's three scoring factors (proficiency surplus, workload, availability margin) as independent, individually-testable functions combined by a ranker. Correctly scoped as narrow — not generalized into a pluggable matcher-strategy registry the requirements don't call for. |
| Command | Behavioral | PRD FR-10/11/12 (submit/approve/reject/activate/complete); implied but not named in the explainer | Partially applied — the *behavior* described (one transition action, varying required payload/preconditions per action, e.g. reject needs a `reason`) is exactly what a Command object formalizes, but the design doc never names it. Functionally this doesn't change anything (the PRD's Given/When/Then criteria already fully pin the behavior), but naming it would reduce the risk of `python-programmer` implementing six near-duplicate handler functions instead of one parameterized executor. See recommendation below. |

---

## Recommended Patterns

> Opportunities where naming a pattern explicitly would reduce implementation risk. Both are documentation-completeness gaps, not functional gaps — the PRD's acceptance criteria already fully specify the required behavior either way.

| Opportunity | Suggested Pattern | Location | Impact | Priority |
|------------|-------------------|----------|--------|----------|
| The six mission-lifecycle actions (submit/approve/reject/activate/complete/cancel) are described action-by-action in FR-10/11/12 without naming the shared mechanism that should implement all of them | Command | New subsection near "Table-driven state machine" in the explainer, or a line in PRD §6 NFR | Medium | Medium |
| FR-13's three hard filters (skill+proficiency, availability, no conflicting confirmed assignment) are described in prose as a conjunction but never named as a composable structure | Pipe and Filter (or an explicit "each hard constraint is one predicate" note) | New subsection near "Strategy" in the explainer | Medium | Medium |

_No high-priority gaps — the design is unusually explicit for a pre-code PRD; both items above are about naming, not missing behavior._

---

## Detailed Recommendations

### Command — mission lifecycle actions

**Problem:** FR-10, FR-11, and FR-12 each describe one lifecycle action's precondition and effect in isolation (submit needs ≥1 requirement; approve/reject need the non-creator identity check; activate/complete need `approved`/`active` respectively). Read independently, nothing in the PRD tells an implementer these six actions should share one code path rather than six separate route handlers each re-deriving the state-machine check.

**Why this pattern fits:** All six are the same shape — validate a precondition specific to the action, look up the allowed target state(s) in the transition table, apply an optional payload (only `reject` requires one: `reason`), persist. That's a Command: one `execute_transition(mission, action, actor, **payload)` entry point, with `action` selecting which precondition function runs. This is also exactly how the design's own "table-driven state machine" earns its value — a shared executor is what makes the table the single source of truth, rather than the table being a table for FR-9's own sake, with each route reimplementing it.

**How to apply:** One function (or a small `ACTIONS: dict[str, MissionAction]` registry) in `services/missions.py`, where each `MissionAction` bundles: target state, an optional precondition callable (`requires_creator`, `requires_not_creator`, `requires_min_requirements`), and required payload fields. Route handlers become a one-line call each: `mission_service.execute_transition(mission_id, "reject", current_user, reason=body.reason)`.

**Trade-offs to consider:** For only six actions on one entity, a fully generic Command *object* hierarchy (with `execute()`/`undo()` methods, a command queue, etc.) would be over-engineering — the PRD's own scope discipline argues for the lightweight version (one function + a small config table), not a formal Command class per action. Undo/redo is not a requirement here (rejection already *is* the "undo" path back to `draft`), so skip any Command machinery built around reversibility.

### Pipe and Filter (Specification-style) — matcher hard filters

**Problem:** FR-13(a) reads as one compound condition ("hard-filters crew to those who hold the required skill at ≥ minimum proficiency, have no unavailability window overlapping the mission's dates, and have no confirmed assignment on another mission with an overlapping date range"). Written as prose, it invites being implemented as one large boolean expression or one big SQL query with three `AND`ed conditions inlined — which is exactly the kind of thing that's hard to unit-test per-condition and easy to get an off-by-one wrong in (especially the two independent date-overlap checks).

**Why this pattern fits:** Each hard constraint is naturally its own predicate over a candidate crew member, with no dependency between them — the classic shape for a small filter pipeline. Modeling each as its own function (`has_skill_at_proficiency`, `is_available_for_window`, `has_no_conflicting_confirmed_assignment`) that returns true/false for one crew member lets each be unit-tested with a minimal fixture (one crew record, one mission window) instead of needing a full seeded scenario to exercise all three at once.

**How to apply:** Three small functions in `services/matcher.py`, each taking `(crew, mission, requirement)` and returning `bool`; the hard-filter step is `all(check(crew, mission, requirement) for check in HARD_FILTERS)`. Reuse the same date-overlap helper for both the availability check and the double-booking check (FR-16 needs the identical overlap logic as a safety-net check outside the matcher, so this helper is shared, not duplicated).

**Trade-offs to consider:** Don't generalize this into a registered/pluggable filter chain (e.g., letting orgs configure their own hard constraints) — nothing in the PRD asks for that, and §10 #17's real/tested vertical slice is specifically scoped to *these three* constraints. Three named functions is the right amount of structure; a filter-registration framework would be solving a problem that doesn't exist yet.

---

## Anti-Patterns Observed

No anti-patterns observed. Notably, the design doc's own "Deliberately skipped" list (repository interfaces + a DI container, CQRS/event sourcing, a pluggable matcher-strategy registry) heads off the most likely anti-pattern for a project like this — pattern over-application for its own sake — before it could happen. That list is itself good practice: naming what you're *not* doing, and why, is rarer and more useful than another pattern diagram.

---

## Summary

- **Patterns in use:** 7 (6 fully named and documented, 1 — Command — implied by the requirements but not yet named)
- **New opportunities identified:** 2
- **High priority recommendations:** 0
- **Anti-patterns observed:** 0

> This is a well-matched pattern set for a 3–5 hour scope: nothing chosen is more than the requirements actually call for, and the explainer's "deliberately skipped" list shows real judgment about where to stop. The one gap worth closing before implementation starts is naming Command explicitly for the lifecycle transitions — cheap to add, and it's the difference between `python-programmer` writing one well-tested transition executor versus six subtly-inconsistent route handlers.

---

## Machine-Parsable Summary

```json
{
  "review_date": "2026-09-14",
  "mode": "design_doc",
  "languages": ["python", "typescript"],
  "scope": "full",
  "patterns_in_use": [
    { "pattern": "Layered Architecture (N-Tier)", "category": "architectural", "location": "PRD §6 NFR; explainer request-flow diagram", "assessment": "well_implemented" },
    { "pattern": "Dependency Injection", "category": "modern", "location": "explainer 'Design patterns' section", "assessment": "well_implemented" },
    { "pattern": "Repository", "category": "modern", "location": "explainer 'Design patterns' section", "assessment": "well_implemented" },
    { "pattern": "Singleton", "category": "creational", "location": "explainer 'Design patterns' section", "assessment": "well_implemented" },
    { "pattern": "State", "category": "behavioral", "location": "explainer 'Table-driven state machine'; PRD FR-9", "assessment": "well_implemented" },
    { "pattern": "Strategy", "category": "behavioral", "location": "explainer 'Design patterns' section; PRD FR-13", "assessment": "well_implemented" },
    { "pattern": "Command", "category": "behavioral", "location": "PRD FR-10/11/12", "assessment": "partially_applied" }
  ],
  "recommendations": [
    { "opportunity": "Six lifecycle actions described individually without naming the shared executor pattern", "pattern": "Command", "location": "PRD §6 NFR / explainer", "impact": "medium", "priority": "medium" },
    { "opportunity": "Matcher's three hard filters described as one compound condition, not a composable structure", "pattern": "Pipe and Filter", "location": "explainer 'Design patterns' section", "impact": "medium", "priority": "medium" }
  ],
  "anti_patterns": [],
  "counts": {
    "patterns_in_use": 7,
    "opportunities": 2,
    "high_priority": 0,
    "anti_patterns": 0
  }
}
```
