import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { Mission } from "../api/types";
import { ErrorBanner } from "../components/ErrorBanner";
import { Spinner } from "../components/Spinner";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

const inputClass =
  "w-full rounded-md border border-border bg-surface px-3 py-2.5 text-sm text-text placeholder:text-text-3 focus:border-accent focus:outline-none";
const labelClass = "text-xs font-semibold text-text-2";

/** Director/Mission Lead only (mirrors the API's `require_role` on
 * `POST /missions`, api/routes/mission.py) — starts the mission in `draft`
 * (FR-8), with no requirements yet; those are added from the detail screen
 * once the mission exists. */
export function MissionCreateScreen({
  onCreated,
  onCancel,
}: {
  onCreated: (missionId: number) => void;
  onCancel: () => void;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const createMutation = useMutation({
    mutationFn: () => api.mission.create({ name, description, startDate, endDate }),
    onSuccess: (mission: Mission) => {
      queryClient.invalidateQueries({ queryKey: ["missions"] });
      onCreated(mission.id);
    },
  });

  const dateOrderInvalid = Boolean(startDate && endDate && endDate < startDate);
  const canSubmit = name.trim().length > 0 && startDate.length > 0 && endDate.length > 0 && !dateOrderInvalid;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    createMutation.mutate();
  }

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-10 py-8">
      <button
        type="button"
        onClick={onCancel}
        className="flex w-fit items-center gap-1.5 text-xs text-text-2 hover:text-accent"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M15 6l-6 6 6 6" />
        </svg>
        All missions
      </button>

      <div>
        <div className="text-[22px] font-bold">New mission</div>
        <div className="mt-0.5 text-[13px] text-text-2">
          Starts in draft. Adding requirements and submitting for approval isn't in this
          showcase UI yet — use <code className="font-mono">missionctl mission add-requirement</code> and{" "}
          <code className="font-mono">missionctl mission submit</code> from the CLI.
        </div>
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex max-w-xl flex-col gap-[18px] rounded-[10px] border border-border bg-surface p-6"
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="mission-name" className={labelClass}>
            Name
          </label>
          <input
            id="mission-name"
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Coastal flood response — Sector 4"
            className={inputClass}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="mission-description" className={labelClass}>
            Description
          </label>
          <textarea
            id="mission-description"
            rows={4}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this mission covers, and any context crew proposing to join should know."
            className={inputClass}
          />
        </div>

        <div className="flex gap-4">
          <div className="flex flex-1 flex-col gap-1.5">
            <label htmlFor="mission-start" className={labelClass}>
              Start date
            </label>
            <input
              id="mission-start"
              type="date"
              required
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className={inputClass}
            />
          </div>
          <div className="flex flex-1 flex-col gap-1.5">
            <label htmlFor="mission-end" className={labelClass}>
              End date
            </label>
            <input
              id="mission-end"
              type="date"
              required
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className={inputClass}
            />
          </div>
        </div>

        {dateOrderInvalid && (
          <div className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-xs text-danger" role="alert">
            End date can't be before the start date.
          </div>
        )}

        {createMutation.isError && (
          <ErrorBanner message={errorMessage(createMutation.error, "Couldn't create this mission.")} onRetry={() => createMutation.mutate()} />
        )}

        <div className="flex gap-2.5">
          <button
            type="submit"
            disabled={!canSubmit || createMutation.isPending}
            className="flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
          >
            {createMutation.isPending && <Spinner />}
            {createMutation.isPending ? "Creating…" : "Create mission"}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border px-4 py-2.5 text-sm font-semibold text-text-2"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
