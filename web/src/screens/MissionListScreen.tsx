import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { Mission, MissionStatus } from "../api/types";
import { MissionStatusBadge } from "../components/StatusBadge";
import { ErrorBanner } from "../components/ErrorBanner";
import { formatDateRange, missionStatusLabel } from "../lib/format";

const STATUS_FILTERS: MissionStatus[] = [
  "draft",
  "pending_approval",
  "approved",
  "active",
  "completed",
  "cancelled",
];

// Stable reference so `missions` doesn't change identity on every render
// while the query is pending (a fresh `[]` literal would).
const EMPTY_MISSIONS: Mission[] = [];

function MissionRowSkeleton() {
  return (
    <div className="grid grid-cols-[2.4fr_1.3fr_1fr_32px] items-center gap-3 border-b border-border px-5 py-4">
      <div className="h-4 w-40 animate-pulse rounded bg-surface-2" />
      <div className="h-4 w-24 animate-pulse rounded bg-surface-2" />
      <div className="h-6 w-20 animate-pulse rounded-full bg-surface-2" />
      <div />
    </div>
  );
}

export function MissionListScreen({
  onSelectMission,
  onCreateMission,
}: {
  onSelectMission: (missionId: number) => void;
  onCreateMission: () => void;
}) {
  const missionsQuery = useQuery({ queryKey: ["missions"], queryFn: api.mission.list });
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<MissionStatus | "all">("all");

  const missions = missionsQuery.data ?? EMPTY_MISSIONS;

  const counts = useMemo(() => {
    const byStatus: Partial<Record<MissionStatus, number>> = {};
    for (const m of missions) byStatus[m.status] = (byStatus[m.status] ?? 0) + 1;
    return byStatus;
  }, [missions]);

  const filtered = useMemo(() => {
    return missions.filter((m: Mission) => {
      if (statusFilter !== "all" && m.status !== statusFilter) return false;
      if (search.trim() && !m.name.toLowerCase().includes(search.trim().toLowerCase())) return false;
      return true;
    });
  }, [missions, statusFilter, search]);

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-10 py-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[22px] font-bold">Missions</div>
          <div className="mt-0.5 text-[13px] text-text-2">
            {missionsQuery.isSuccess ? `${missions.length} mission${missions.length === 1 ? "" : "s"} in your organization` : " "}
          </div>
        </div>
        <button
          type="button"
          onClick={onCreateMission}
          className="flex flex-none items-center gap-1.5 rounded-md bg-accent px-4 py-2.5 text-[13px] font-semibold text-white"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25">
            <path d="M12 5v14M5 12h14" />
          </svg>
          New mission
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2.5">
        <div className="relative">
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
            placeholder="Search missions"
            aria-label="Search missions"
            className="w-64 rounded-md border border-border bg-surface py-2.5 pl-8 pr-3 text-[13.5px] text-text placeholder:text-text-3 focus:border-accent focus:outline-none"
          />
        </div>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => setStatusFilter("all")}
          className={`rounded-full border px-3 py-1.5 text-[12.5px] font-medium ${
            statusFilter === "all" ? "border-transparent bg-accent-2 text-accent-dark" : "border-border bg-surface text-text-2"
          }`}
        >
          All · {missions.length}
        </button>
        {STATUS_FILTERS.map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => setStatusFilter(status)}
            className={`rounded-full border px-3 py-1.5 text-[12.5px] font-medium ${
              statusFilter === status ? "border-transparent bg-accent-2 text-accent-dark" : "border-border bg-surface text-text-2"
            }`}
          >
            {missionStatusLabel(status)} · {counts[status] ?? 0}
          </button>
        ))}
      </div>

      {missionsQuery.isError && (
        <ErrorBanner
          message={missionsQuery.error instanceof Error ? missionsQuery.error.message : "Couldn't load missions."}
          onRetry={() => missionsQuery.refetch()}
        />
      )}

      <div className="overflow-hidden rounded-[10px] border border-border bg-surface">
        <div className="grid grid-cols-[2.4fr_1.3fr_1fr_32px] gap-3 border-b border-border px-5 py-3 text-[11.5px] font-semibold uppercase tracking-wide text-text-3">
          <div>Mission</div>
          <div>Dates</div>
          <div>Status</div>
          <div />
        </div>

        {missionsQuery.isPending && (
          <>
            <MissionRowSkeleton />
            <MissionRowSkeleton />
            <MissionRowSkeleton />
          </>
        )}

        {missionsQuery.isSuccess && filtered.length === 0 && (
          <div className="px-5 py-10 text-center text-sm text-text-3">
            {missions.length === 0 ? "No missions yet." : "No missions match your search."}
          </div>
        )}

        {filtered.map((mission) => (
          <button
            key={mission.id}
            type="button"
            onClick={() => onSelectMission(mission.id)}
            className="grid w-full grid-cols-[2.4fr_1.3fr_1fr_32px] items-center gap-3 border-b border-border px-5 py-4 text-left last:border-b-0 hover:bg-surface-2"
          >
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold">{mission.name}</div>
            </div>
            <div className="text-[13px] text-text-2">{formatDateRange(mission.start_date, mission.end_date)}</div>
            <div>
              <MissionStatusBadge status={mission.status} />
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
