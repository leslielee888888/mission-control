import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { Skill } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { Spinner } from "../components/Spinner";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

// Stable reference so `skills` doesn't change identity while the query is
// pending — same trick as MissionListScreen's EMPTY_MISSIONS.
const EMPTY_SKILLS: Skill[] = [];

/** Org skill taxonomy (FR-5). Director/Mission Lead both see the list;
 * only Director gets the "add a skill" control. */
export function SkillsScreen() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const skillsQuery = useQuery({ queryKey: ["skills"], queryFn: api.skills.list });
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");

  const skills = skillsQuery.data ?? EMPTY_SKILLS;
  const canAdd = user?.role === "director";

  const createMutation = useMutation({
    mutationFn: () => api.skills.create(name.trim(), category.trim() || undefined),
    onSuccess: () => {
      setName("");
      setCategory("");
      queryClient.invalidateQueries({ queryKey: ["skills"] });
    },
  });

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-10 py-8">
      <div>
        <div className="text-[22px] font-bold">Skills</div>
        <div className="mt-0.5 text-[13px] text-text-2">
          {skillsQuery.isSuccess ? `${skills.length} skill${skills.length === 1 ? "" : "s"} in your organization's taxonomy` : " "}
        </div>
      </div>

      {skillsQuery.isError && (
        <ErrorBanner
          message={errorMessage(skillsQuery.error, "Couldn't load the skill taxonomy.")}
          onRetry={() => skillsQuery.refetch()}
        />
      )}

      <div className="flex items-start gap-7">
        <div className="min-w-0 flex-1 overflow-hidden rounded-[10px] border border-border bg-surface">
          <div className="grid grid-cols-[2fr_1.2fr] gap-3 border-b border-border px-5 py-3 text-[11.5px] font-semibold uppercase tracking-wide text-text-3">
            <div>Name</div>
            <div>Category</div>
          </div>

          {skillsQuery.isPending && (
            <>
              {[0, 1, 2].map((i) => (
                <div key={i} className="grid grid-cols-[2fr_1.2fr] items-center gap-3 border-b border-border px-5 py-4 last:border-b-0">
                  <div className="h-4 w-32 animate-pulse rounded bg-surface-2" />
                  <div className="h-4 w-20 animate-pulse rounded bg-surface-2" />
                </div>
              ))}
            </>
          )}

          {skillsQuery.isSuccess && skills.length === 0 && (
            <div className="px-5 py-10 text-center text-sm text-text-3">No skills defined yet.</div>
          )}

          {skills.map((skill) => (
            <div
              key={skill.id}
              className="grid grid-cols-[2fr_1.2fr] items-center gap-3 border-b border-border px-5 py-4 last:border-b-0"
            >
              <div className="text-sm font-semibold">{skill.name}</div>
              <div className="text-[13px] text-text-2">{skill.category || <span className="text-text-3">—</span>}</div>
            </div>
          ))}
        </div>

        {canAdd && (
          <div className="w-72 flex-none rounded-[10px] border border-border bg-surface p-5">
            <div className="mb-3.5 text-[13px] font-bold">Add a skill</div>
            <form
              className="flex flex-col gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (name.trim().length === 0) return;
                createMutation.mutate();
              }}
            >
              <div className="flex flex-col gap-1.5">
                <label htmlFor="skill-name" className="text-xs font-semibold text-text-2">
                  Name
                </label>
                <input
                  id="skill-name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Swift-Water Rescue"
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[13px] focus:border-accent focus:outline-none"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="skill-category" className="text-xs font-semibold text-text-2">
                  Category <span className="font-normal text-text-3">(optional)</span>
                </label>
                <input
                  id="skill-category"
                  type="text"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="e.g. rescue"
                  className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[13px] focus:border-accent focus:outline-none"
                />
              </div>
              <button
                type="submit"
                disabled={createMutation.isPending || name.trim().length === 0}
                className="flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2 text-[13px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
              >
                {createMutation.isPending && <Spinner />}
                Add skill
              </button>
              {createMutation.isError && (
                <ErrorBanner message={errorMessage(createMutation.error, "Couldn't create this skill.")} />
              )}
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
