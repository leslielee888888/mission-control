import { useMemo } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { Assignment, AssignmentStatus, MissionDetail } from "../api/types";
import { AssignmentStatusBadge } from "../components/StatusBadge";
import { ErrorBanner } from "../components/ErrorBanner";
import { Spinner } from "../components/Spinner";
import { formatDate, formatDateRange } from "../lib/format";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

// proposed needs a decision first, then confirmed, then declined history last.
const STATUS_ORDER: Record<AssignmentStatus, number> = { proposed: 0, confirmed: 1, declined: 2 };

interface RespondVars {
  assignmentId: number;
  action: "accept" | "decline";
}

export function MyAssignmentsScreen() {
  const queryClient = useQueryClient();

  const assignmentsQuery = useQuery({ queryKey: ["assignments"], queryFn: api.assignment.list });
  const assignments = useMemo(
    () => [...(assignmentsQuery.data ?? [])].sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status]),
    [assignmentsQuery.data],
  );

  const missionIds = useMemo(() => Array.from(new Set(assignments.map((a) => a.mission_id))), [assignments]);

  const missionQueries = useQueries({
    queries: missionIds.map((id) => ({
      queryKey: ["mission", id],
      queryFn: () => api.mission.get(id),
      enabled: assignmentsQuery.isSuccess,
    })),
  });
  const missionById = new Map<number, MissionDetail>();
  missionQueries.forEach((q, i) => {
    if (q.data) missionById.set(missionIds[i]!, q.data);
  });
  const missionsLoading = missionQueries.some((q) => q.isPending);

  const respondMutation = useMutation({
    mutationFn: (vars: RespondVars) => api.assignment.respond(vars.assignmentId, vars.action),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["assignments"] });
      const previous = queryClient.getQueryData<Assignment[]>(["assignments"]);
      queryClient.setQueryData<Assignment[]>(["assignments"], (old) =>
        (old ?? []).map((a) =>
          a.id === vars.assignmentId
            ? { ...a, status: vars.action === "accept" ? "confirmed" : "declined", responded_at: new Date().toISOString() }
            : a,
        ),
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["assignments"], context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["assignments"] }),
  });

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-10 py-8">
      <div>
        <div className="text-[22px] font-bold">My Assignments</div>
        <div className="mt-0.5 text-[13px] text-text-2">Missions you've been proposed or confirmed for.</div>
      </div>

      {assignmentsQuery.isError && (
        <ErrorBanner
          message={errorMessage(assignmentsQuery.error, "Couldn't load your assignments.")}
          onRetry={() => assignmentsQuery.refetch()}
        />
      )}

      {assignmentsQuery.isPending && (
        <div className="flex flex-col gap-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-[10px] border border-border bg-surface" />
          ))}
        </div>
      )}

      {assignmentsQuery.isSuccess && assignments.length === 0 && (
        <div className="rounded-[10px] border border-border bg-surface px-5 py-10 text-center text-sm text-text-3">
          You haven't been proposed for any missions yet.
        </div>
      )}

      <div className="flex flex-col gap-3">
        {assignments.map((assignment) => {
          const mission = missionById.get(assignment.mission_id);
          const requirement = mission?.requirements.find((r) => r.id === assignment.requirement_id);
          const isThisRow = respondMutation.variables?.assignmentId === assignment.id;
          const isPending = respondMutation.isPending && isThisRow;
          const isError = respondMutation.isError && isThisRow;

          return (
            <div
              key={assignment.id}
              className={`flex flex-col gap-2 rounded-[10px] border bg-surface px-[22px] py-[18px] ${
                assignment.status === "proposed" ? "border-pending" : "border-border"
              } ${assignment.status === "declined" ? "bg-surface-2 opacity-65" : ""} ${isPending ? "opacity-75" : ""}`}
            >
              <div className="flex items-center gap-5">
                <div className="flex-1">
                  <div className="flex items-center gap-2.5">
                    <div className="text-[15px] font-bold">{mission?.name ?? (missionsLoading ? "Loading…" : `Mission #${assignment.mission_id}`)}</div>
                    <AssignmentStatusBadge status={assignment.status} />
                  </div>
                  <div className="mt-1 text-[12.5px] text-text-2">
                    {mission ? formatDateRange(mission.start_date, mission.end_date) : ""}
                    {requirement ? ` · matched on ${requirement.skill_name} (min level ${requirement.min_proficiency})` : ""}
                  </div>
                </div>

                {isPending && (
                  <div className="flex items-center gap-2 text-sm font-semibold text-text-2">
                    <Spinner /> {respondMutation.variables?.action === "accept" ? "Accepting…" : "Declining…"}
                  </div>
                )}

                {!isPending && assignment.status === "proposed" && (
                  <div className="flex gap-2.5">
                    <button
                      type="button"
                      onClick={() => respondMutation.mutate({ assignmentId: assignment.id, action: "accept" })}
                      className="rounded-md bg-accent px-[18px] py-2 text-sm font-semibold text-white"
                    >
                      Accept
                    </button>
                    <button
                      type="button"
                      onClick={() => respondMutation.mutate({ assignmentId: assignment.id, action: "decline" })}
                      className="rounded-md border border-border bg-surface px-[18px] py-2 text-sm font-semibold text-text-2"
                    >
                      Decline
                    </button>
                  </div>
                )}

                {!isPending && assignment.status === "confirmed" && (
                  <div className="flex items-center gap-1.5 text-sm font-semibold text-approved">
                    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="9" />
                      <path d="M8.5 12.5l2.3 2.3L16 10" />
                    </svg>
                    You're on this mission
                  </div>
                )}

                {!isPending && assignment.status === "declined" && assignment.responded_at && (
                  <div className="text-xs text-text-3">
                    Declined {formatDate(assignment.responded_at.slice(0, 10))} — your response reopened this slot.
                  </div>
                )}
              </div>

              {isError && (
                <ErrorBanner
                  message={`Couldn't ${respondMutation.variables?.action} — ${errorMessage(respondMutation.error, "something went wrong.")}`}
                  onRetry={() =>
                    respondMutation.mutate({ assignmentId: assignment.id, action: respondMutation.variables!.action })
                  }
                />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
