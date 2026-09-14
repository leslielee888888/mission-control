# Mission Control — web

A minimal React SPA showcasing the real Mission Control API (FR-21, PRD §7 "Web UI").
This is a showcase, not a second CLI: 2-3 screens, role-conditional on the logged-in
user, hitting the same FastAPI backend the CLI (`missionctl`) does.

- **Mission Lead / Director:** mission list → mission detail (requirements,
  fulfillment, a matcher run with ranked candidates and score breakdowns,
  propose/approve/reject).
- **Crew Member:** My Assignments (accept/decline).

Server state is [React Query](https://tanstack.com/query) — loading/error states and
optimistic updates on every mutating action are the actual point of this showcase, not
an afterthought. Local UI state (search box, reject-reason form, etc.) is plain
`useState`. Styling is Tailwind CSS, following the design mockups in
`../docs/design/spa-mockups/`.

## Running it

The API must be running first (from the repo root):

```bash
pip install -r requirements.txt
python scripts/seed.py   # creates the tables; T9 adds real demo data
uvicorn main:app --reload
```

Then, from `web/`:

```bash
npm install
npm run dev
```

By default the app talks to `http://localhost:8000`. If the API is on a different
port, copy `.env.example` to `.env.local` and set `VITE_API_BASE_URL`.

## Scripts

- `npm run dev` — Vite dev server with HMR.
- `npm run build` — typecheck (`tsc -b`) then production build.
- `npm run lint` — oxlint.

## The API client

`src/api/client.ts` + `src/api/types.ts` are a hand-written, RPC-flavored client
(`api.mission.approve(id)`, `api.assignment.propose(...)`) over the routes in
`../api/routes/*.py`, typed by hand rather than generated from the OpenAPI schema —
see the comment at the top of `client.ts` for why, and what to revisit if this app
grows past a showcase.
