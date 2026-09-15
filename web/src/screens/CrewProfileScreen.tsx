import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import { ErrorBanner } from "../components/ErrorBanner";
import { Spinner } from "../components/Spinner";
import { initials, proficiencyLabel } from "../lib/format";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

function BackLink({ onBack }: { onBack: () => void }) {
  return (
    <button type="button" onClick={onBack} className="flex w-fit items-center gap-1.5 text-xs text-text-2 hover:text-accent">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M15 6l-6 6 6 6" />
      </svg>
      All crew
    </button>
  );
}

/** Director/Mission Lead viewing another crew member's profile
 * (`GET /crew/{id}/profile`) — read-only per FR-4, no edit controls. */
export function CrewProfileScreen({ crewId, onBack }: { crewId: number; onBack: () => void }) {
  const profileQuery = useQuery({ queryKey: ["crew", "profile", crewId], queryFn: () => api.crew.profile(crewId) });

  if (profileQuery.isPending) {
    return (
      <div className="flex flex-1 items-center justify-center px-10 py-8">
        <Spinner className="h-6 w-6 text-text-3" />
      </div>
    );
  }

  if (profileQuery.isError) {
    return (
      <div className="flex flex-1 flex-col gap-4 px-10 py-8">
        <BackLink onBack={onBack} />
        <ErrorBanner
          message={errorMessage(profileQuery.error, "Couldn't load this crew member's profile.")}
          onRetry={() => profileQuery.refetch()}
        />
      </div>
    );
  }

  const profile = profileQuery.data;

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-10 py-7">
      <BackLink onBack={onBack} />

      <div className="flex items-center gap-3.5">
        <div className="flex h-12 w-12 flex-none items-center justify-center rounded-full bg-accent-2 text-sm font-bold text-accent-dark">
          {initials(profile.name)}
        </div>
        <div>
          <div className="text-2xl font-bold">{profile.name}</div>
          <div className="text-[13px] text-text-2">{profile.email}</div>
        </div>
      </div>

      <div className="flex items-start gap-7">
        <div className="flex min-w-0 flex-1 flex-col gap-5">
          <div className="rounded-[10px] border border-border bg-surface p-5">
            <div className="mb-3 text-[15px] font-bold">Bio</div>
            <p className="text-sm text-text-2">{profile.bio || <span className="text-text-3">No bio provided.</span>}</p>
          </div>

          <div className="rounded-[10px] border border-border bg-surface p-5">
            <div className="mb-4 text-[15px] font-bold">Skills</div>
            {profile.skills.length === 0 ? (
              <div className="text-sm text-text-3">No skill proficiencies recorded yet.</div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {profile.skills.map((skill) => (
                  <div key={skill.skill_id} className="flex items-center justify-between rounded-lg bg-surface-2 px-3.5 py-3">
                    <div className="text-[13.5px] font-semibold">{skill.skill_name}</div>
                    <div className="text-xs text-text-2">
                      {proficiencyLabel(skill.proficiency)} <span className="font-mono text-text-3">({skill.proficiency}/5)</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="w-72 flex-none">
          <div className="rounded-[10px] border border-border bg-surface p-5">
            <div className="mb-1.5 text-[13px] font-bold">Contact</div>
            <p className="text-xs leading-relaxed text-text-2">
              {profile.contact || <span className="text-text-3">No contact info provided.</span>}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
