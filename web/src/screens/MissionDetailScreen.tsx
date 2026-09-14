import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { Assignment, MissionDetail } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { MissionStatusBadge } from "../components/StatusBadge";
import { ErrorBanner } from "../components/ErrorBanner";
import { Spinner } from "../components/Spinner";
import { FulfillmentBar } from "../components/FulfillmentBar";
import { formatDateRange, initials } from "../lib/format";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

interface ProposeVars {
  requirementId: number;
  crewId: number;
}

export function MissionDetailScreen({ missionId, onBack }: { missionId: number; onBack: () => void }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [hasRunMatcher, setHasRunMatcher] = useState(false);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const missionQuery = useQuery({
    queryKey: ["mission", missionId],
    queryFn: () => api.mission.get(missionId),
  });

  const assignmentsQuery = useQuery({
    queryKey: ["assignments"],
    queryFn: api.assignment.list,
  });

  const matchQuery = useQuery({
    queryKey: ["match", missionId],
    queryFn: () => api.match.run(missionId),
    enabled: hasRunMatcher,
  });

  const approveMutation = useMutation({
    mutationFn: () => api.mission.approve(missionId),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["mission", missionId] });
      const previous = queryClient.getQueryData<MissionDetail>(["mission", missionId]);
      if (previous) queryClient.setQueryData<MissionDetail>(["mission", missionId], { ...previous, status: "approved" });
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["mission", missionId], context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["mission", missionId] }),
  });

  const rejectMutation = useMutation({
    mutationFn: (reason: string) => api.mission.reject(missionId, reason),
    onMutate: async (reason) => {
      await queryClient.cancelQueries({ queryKey: ["mission", missionId] });
      const previous = queryClient.getQueryData<MissionDetail>(["mission", missionId]);
      if (previous) queryClient.setQueryData<MissionDetail>(["mission", missionId], { ...previous, status: "draft" });
      return { previous, reason };
    },
    onSuccess: () => {
      setShowRejectForm(false);
      setRejectReason("");
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["mission", missionId], context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["mission", missionId] }),
  });

  const proposeMutation = useMutation({
    mutationFn: (vars: ProposeVars) => api.assignment.propose(missionId, vars.requirementId, vars.crewId),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["assignments"] });
      const previous = queryClient.getQueryData<Assignment[]>(["assignments"]);
      const optimistic: Assignment = {
        // Negative id marks this row as "not yet confirmed by the server" —
        // the UI uses it to show the optimistic-update note (mockup: "shown
        // instantly on click"). Replaced by the real row once settled.
        id: -Date.now(),
        mission_id: missionId,
        requirement_id: vars.requirementId,
        crew_id: vars.crewId,
        proposed_by: user?.id ?? 0,
        status: "proposed",
        proposed_at: new Date().toISOString(),
        responded_at: null,
      };
      queryClient.setQueryData<Assignment[]>(["assignments"], (old) => [...(old ?? []), optimistic]);
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["assignments"], context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["assignments"] }),
  });

  if (missionQuery.isPending) {
    return (
      <div className="flex flex-1 items-center justify-center px-10 py-8">
        <Spinner className="h-6 w-6 text-text-3" />
      </div>
    );
  }

  if (missionQuery.isError) {
    return (
      <div className="flex flex-1 flex-col gap-4 px-10 py-8">
        <BackLink onBack={onBack} />
        <ErrorBanner message={errorMessage(missionQuery.error, "Couldn't load this mission.")} onRetry={() => missionQuery.refetch()} />
      </div>
    );
  }

  const mission = missionQuery.data;
  const assignments = assignmentsQuery.data ?? [];
  const canReview = user?.role === "director" && mission.status === "pending_approval";
  const isOwnMission = mission.created_by === user?.id;

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-10 py-7">
      <BackLink onBack={onBack} />

      <div>
        <div className="flex items-center gap-3">
          <div className="text-2xl font-bold">{mission.name}</div>
          <MissionStatusBadge status={mission.status} />
        </div>
        <div className="mt-1.5 text-[13px] text-text-2">{formatDateRange(mission.start_date, mission.end_date)}</div>
        <p className="mt-2 max-w-2xl text-sm text-text-2">{mission.description}</p>
      </div>

      <div className="flex items-start gap-7">
        {/* Left column */}
        <div className="flex min-w-0 flex-1 flex-col gap-5">
          <div className="rounded-[10px] border border-border bg-surface p-5">
            <div className="mb-4 text-[15px] font-bold">Requirements</div>
            {mission.requirements.length === 0 ? (
              <div className="text-sm text-text-3">No requirements added yet.</div>
            ) : (
              <div className="flex flex-col gap-3.5">
                {mission.requirements.map((req) => (
                  <div key={req.id} className="flex items-center justify-between rounded-lg bg-surface-2 px-3.5 py-3">
                    <div>
                      <div className="text-[13.5px] font-semibold">{req.skill_name}</div>
                      <div className="text-xs text-text-3">
                        Proficiency ≥ {req.min_proficiency} · needs {req.headcount}
                      </div>
                    </div>
                    <FulfillmentBar confirmed={req.confirmed} headcount={req.headcount} />
                  </div>
                ))}
              </div>
            )}
          </div>

          {(user?.role === "director" || user?.role === "mission_lead") && (
            <div className="rounded-[10px] border border-border bg-surface p-5">
              <div className="mb-1 flex items-center justify-between">
                <div className="text-[15px] font-bold">Matcher</div>
                {hasRunMatcher && (
                  <button
                    type="button"
                    onClick={() => matchQuery.refetch()}
                    disabled={matchQuery.isFetching}
                    className="flex items-center gap-1.5 text-[12.5px] text-accent hover:text-accent-dark disabled:opacity-60"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M21 12a9 9 0 1 1-3-6.7M21 3v6h-6" />
                    </svg>
                    Re-run matcher
                  </button>
                )}
              </div>
              <div className="mb-4 text-xs text-text-3">
                Ranked by proficiency surplus (50%) · workload (30%) · availability margin (20%). Every eligible crew
                member is shown, not just the top few.
              </div>

              {!hasRunMatcher && (
                <button
                  type="button"
                  onClick={() => setHasRunMatcher(true)}
                  className="rounded-md bg-accent px-4 py-2 text-[13px] font-semibold text-white"
                >
                  Run matcher
                </button>
              )}

              {hasRunMatcher && matchQuery.isPending && (
                <div className="flex items-center gap-2 text-sm text-text-3">
                  <Spinner /> Running matcher…
                </div>
              )}

              {hasRunMatcher && matchQuery.isError && (
                <ErrorBanner message={errorMessage(matchQuery.error, "Couldn't run the matcher.")} onRetry={() => matchQuery.refetch()} />
              )}

              {hasRunMatcher && matchQuery.isSuccess && (
                <div className="flex flex-col gap-6">
                  {matchQuery.data.map((requirementMatch) => {
                    const requirement = mission.requirements.find((r) => r.id === requirementMatch.requirement_id);
                    return (
                      <div key={requirementMatch.requirement_id}>
                        <div className="mb-2.5 text-[13px] font-semibold text-text-2">
                          {requirement?.skill_name ?? `Requirement #${requirementMatch.requirement_id}`}
                        </div>
                        {requirementMatch.candidates.length === 0 ? (
                          <div className="text-sm text-text-3">No eligible candidates for this requirement.</div>
                        ) : (
                          <div className="flex flex-col gap-2.5">
                            {requirementMatch.candidates.map((candidate) => (
                              <CandidateRow
                                key={candidate.crew_id}
                                candidate={candidate}
                                requirementId={requirementMatch.requirement_id}
                                assignments={assignments}
                                proposeMutation={proposeMutation}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right column */}
        <div className="flex w-72 flex-none flex-col gap-4.5">
          {canReview && (
            <div className="rounded-[10px] border border-pending bg-surface p-5">
              <div className="mb-1.5 text-sm font-bold">Awaiting your review</div>
              {isOwnMission ? (
                <p className="text-xs leading-relaxed text-text-2">
                  You created this mission, so you're not eligible to approve or reject it — another Director must
                  review it.
                </p>
              ) : (
                <>
                  <p className="mb-4 text-xs leading-relaxed text-text-2">
                    This mission is pending your approval.
                  </p>
                  <div className="flex flex-col gap-2.5">
                    <button
                      type="button"
                      onClick={() => approveMutation.mutate()}
                      disabled={approveMutation.isPending}
                      className="flex w-full items-center justify-center gap-2 rounded-md bg-approved px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-70"
                    >
                      {approveMutation.isPending && <Spinner />}
                      Approve
                    </button>
                    {!showRejectForm && (
                      <button
                        type="button"
                        onClick={() => setShowRejectForm(true)}
                        className="w-full rounded-md border border-danger-border bg-surface px-4 py-2.5 text-sm font-semibold text-danger"
                      >
                        Reject…
                      </button>
                    )}
                    {showRejectForm && (
                      <div className="flex flex-col gap-2">
                        <label htmlFor="reject-reason" className="text-xs font-semibold text-text-2">
                          Reason for rejecting
                        </label>
                        <textarea
                          id="reject-reason"
                          value={rejectReason}
                          onChange={(e) => setRejectReason(e.target.value)}
                          rows={3}
                          className="w-full rounded-md border border-border bg-surface p-2 text-xs focus:border-accent focus:outline-none"
                          placeholder="Why is this mission being sent back to draft?"
                        />
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={() => rejectMutation.mutate(rejectReason)}
                            disabled={rejectMutation.isPending || rejectReason.trim().length === 0}
                            className="flex flex-1 items-center justify-center gap-2 rounded-md bg-danger px-3 py-2 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {rejectMutation.isPending && <Spinner />}
                            Confirm reject
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setShowRejectForm(false);
                              setRejectReason("");
                            }}
                            className="rounded-md border border-border px-3 py-2 text-xs font-semibold text-text-2"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
              {approveMutation.isError && (
                <div className="mt-3">
                  <ErrorBanner message={errorMessage(approveMutation.error, "Couldn't approve this mission.")} onRetry={() => approveMutation.mutate()} />
                </div>
              )}
              {rejectMutation.isError && (
                <div className="mt-3">
                  <ErrorBanner message={errorMessage(rejectMutation.error, "Couldn't reject this mission.")} />
                </div>
              )}
            </div>
          )}

          <div className="rounded-[10px] border border-border bg-surface p-5">
            <div className="mb-3.5 text-[13px] font-bold">Fulfillment</div>
            {mission.requirements.length === 0 ? (
              <div className="text-xs text-text-3">No requirements yet.</div>
            ) : (
              <div className="flex flex-col gap-3">
                {mission.requirements.map((req) => {
                  const pct = req.headcount > 0 ? Math.min(100, Math.round((req.confirmed / req.headcount) * 100)) : 0;
                  return (
                    <div key={req.id}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span>{req.skill_name}</span>
                        <span className="font-mono text-text-2">
                          {req.confirmed}/{req.headcount}
                        </span>
                      </div>
                      <div className="h-1 rounded-full bg-border">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${pct}%`,
                            backgroundColor: req.confirmed >= req.headcount ? "var(--color-approved)" : "var(--color-pending)",
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" onClick={onBack} className="flex w-fit items-center gap-1.5 text-xs text-text-2 hover:text-accent">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M15 6l-6 6 6 6" />
      </svg>
      All missions
    </button>
  );
}

function CandidateRow({
  candidate,
  requirementId,
  assignments,
  proposeMutation,
}: {
  candidate: { crew_id: number; crew_name: string; score: number; breakdown: string };
  requirementId: number;
  assignments: Assignment[];
  proposeMutation: ReturnType<typeof useMutation<Assignment, Error, ProposeVars>>;
}) {
  const existing = assignments.find(
    (a) => a.requirement_id === requirementId && a.crew_id === candidate.crew_id && a.status !== "declined",
  );
  const isThisRow =
    proposeMutation.variables?.requirementId === requirementId && proposeMutation.variables?.crewId === candidate.crew_id;
  const isPending = proposeMutation.isPending && isThisRow;
  const isError = proposeMutation.isError && isThisRow;

  return (
    <div className="flex flex-col gap-2.5 rounded-lg border border-border p-3.5">
      <div className={`flex items-center gap-3.5 ${isPending ? "opacity-70" : ""}`}>
        <div className="flex h-8 w-8 flex-none items-center justify-center rounded-full bg-surface-2 text-xs font-bold text-text-2">
          {initials(candidate.crew_name)}
        </div>
        <div className="flex-1">
          <div className="text-[13.5px] font-semibold">
            {candidate.crew_name} <span className="font-mono text-xs font-medium text-text-2">· score {candidate.score.toFixed(2)}</span>
          </div>
          <div className="mt-0.5 font-mono text-[11.5px] text-text-3">{candidate.breakdown}</div>
        </div>

        {isPending && (
          <div className="flex items-center gap-1.5 text-xs font-semibold text-text-2">
            <Spinner /> Proposing…
          </div>
        )}

        {!isPending && existing?.status === "confirmed" && (
          <div className="flex items-center gap-1.5 rounded-full bg-approved-bg px-3 py-1.5 text-xs font-semibold text-approved">
            Confirmed
          </div>
        )}

        {!isPending && existing?.status === "proposed" && (
          <div className="flex items-center gap-1.5 rounded-full border border-dashed border-pending px-3 py-1.5 text-xs font-semibold text-pending">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="none">
              <circle cx="12" cy="12" r="6" />
            </svg>
            Pending confirmation
          </div>
        )}

        {!isPending && !existing && (
          <button
            type="button"
            onClick={() => proposeMutation.mutate({ requirementId, crewId: candidate.crew_id })}
            className="rounded-md bg-accent px-3.5 py-1.5 text-xs font-semibold text-white"
          >
            Propose
          </button>
        )}
      </div>

      {!isPending && existing?.status === "proposed" && existing.id < 0 && (
        <div className="ml-[46px] flex items-center gap-1.5 text-[11px] text-text-3">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M21 12a9 9 0 1 1-3-6.7" />
          </svg>
          Shown instantly on click — confirming with the server in the background
        </div>
      )}

      {isError && (
        <div className="ml-[46px]">
          <ErrorBanner
            message={`Couldn't propose — ${errorMessage(proposeMutation.error, "something went wrong.")}`}
            onRetry={() => proposeMutation.mutate({ requirementId, crewId: candidate.crew_id })}
          />
        </div>
      )}
    </div>
  );
}
