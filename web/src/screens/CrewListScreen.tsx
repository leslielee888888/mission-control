import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { CrewRosterEntry } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { initials } from "../lib/format";

// Stable reference so `crew` doesn't change identity on every render while
// the query is pending (a fresh `[]` literal would) — same trick as
// MissionListScreen's EMPTY_MISSIONS.
const EMPTY_CREW: CrewRosterEntry[] = [];

function CrewRowSkeleton() {
  return (
    <div className="grid grid-cols-[2fr_2fr_1fr_32px] items-center gap-3 border-b border-border px-5 py-4">
      <div className="h-4 w-32 animate-pulse rounded bg-surface-2" />
      <div className="h-4 w-40 animate-pulse rounded bg-surface-2" />
      <div className="h-4 w-16 animate-pulse rounded bg-surface-2" />
      <div />
    </div>
  );
}

/** Director/Mission Lead: org crew roster (`GET /crew`, FR-4), read-only —
 * click through to a crew member's profile. */
export function CrewListScreen({ onSelectCrew }: { onSelectCrew: (userId: number) => void }) {
  const crewQuery = useQuery({ queryKey: ["crew"], queryFn: api.crew.list });
  const [search, setSearch] = useState("");

  const crew = crewQuery.data ?? EMPTY_CREW;

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return crew;
    return crew.filter((c) => c.name.toLowerCase().includes(term) || c.email.toLowerCase().includes(term));
  }, [crew, search]);

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-10 py-8">
      <div>
        <div className="text-[22px] font-bold">Crew</div>
        <div className="mt-0.5 text-[13px] text-text-2">
          {crewQuery.isSuccess ? `${crew.length} crew member${crew.length === 1 ? "" : "s"} in your organization` : " "}
        </div>
      </div>

      <div className="relative w-64">
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--color-text-3)"
          strokeWidth="2"
          className="pointer-events-none absolute left-[11px] top-1/2 -translate-y-1/2"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4-4" />
        </svg>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search crew"
          aria-label="Search crew"
          className="w-full rounded-md border border-border bg-surface py-2.5 pl-8 pr-3 text-[13.5px] text-text placeholder:text-text-3 focus:border-accent focus:outline-none"
        />
      </div>

      {crewQuery.isError && (
        <ErrorBanner
          message={crewQuery.error instanceof ApiError ? crewQuery.error.message : "Couldn't load the crew roster."}
          onRetry={() => crewQuery.refetch()}
        />
      )}

      <div className="overflow-hidden rounded-[10px] border border-border bg-surface">
        <div className="grid grid-cols-[2fr_2fr_1fr_32px] gap-3 border-b border-border px-5 py-3 text-[11.5px] font-semibold uppercase tracking-wide text-text-3">
          <div>Name</div>
          <div>Email</div>
          <div>Skills</div>
          <div />
        </div>

        {crewQuery.isPending && (
          <>
            <CrewRowSkeleton />
            <CrewRowSkeleton />
            <CrewRowSkeleton />
          </>
        )}

        {crewQuery.isSuccess && filtered.length === 0 && (
          <div className="px-5 py-10 text-center text-sm text-text-3">
            {crew.length === 0 ? "No crew members yet." : "No crew members match your search."}
          </div>
        )}

        {filtered.map((member) => (
          <button
            key={member.user_id}
            type="button"
            onClick={() => onSelectCrew(member.user_id)}
            className="grid w-full grid-cols-[2fr_2fr_1fr_32px] items-center gap-3 border-b border-border px-5 py-4 text-left last:border-b-0 hover:bg-surface-2"
          >
            <div className="flex min-w-0 items-center gap-2.5">
              <div className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-surface-2 text-xs font-bold text-text-2">
                {initials(member.name)}
              </div>
              <div className="truncate text-sm font-semibold">{member.name}</div>
            </div>
            <div className="truncate text-[13px] text-text-2">{member.email}</div>
            <div className="text-[13px] text-text-2">
              {member.skill_count} skill{member.skill_count === 1 ? "" : "s"}
            </div>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-3)" strokeWidth="1.75">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
        ))}
      </div>
    </div>
  );
}
