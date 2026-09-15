import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type { AvailabilityWindow, CrewProfile } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ErrorBanner } from "../components/ErrorBanner";
import { Spinner } from "../components/Spinner";
import { formatDate, proficiencyLabel } from "../lib/format";

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}

const PROFICIENCY_LEVELS = [1, 2, 3, 4, 5];

interface ProfilePatchVars {
  name: string;
  contact: string;
  bio: string;
}

interface SkillSetVars {
  skillId: number;
  skillName: string;
  proficiency: number;
}

interface WindowAddVars {
  startDate: string;
  endDate: string;
}

/** Crew Member self-service: view/edit own profile (FR-4), set skill
 * proficiency (FR-6), and manage unavailability windows (FR-7). The one
 * screen in this task with real forms/mutations — reuses the
 * optimistic-update/loading/error pattern from MissionDetailScreen rather
 * than inventing a new one. */
export function MyProfileScreen() {
  const { user } = useAuth();
  const userId = user!.id;
  const queryClient = useQueryClient();

  const profileQuery = useQuery({ queryKey: ["crew", "profile", userId], queryFn: () => api.crew.profile(userId) });
  const skillsQuery = useQuery({ queryKey: ["skills"], queryFn: api.skills.list });
  const availabilityQuery = useQuery({
    queryKey: ["crew", "availability", userId],
    queryFn: () => api.crew.listAvailability(userId),
  });

  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [nameField, setNameField] = useState("");
  const [contactField, setContactField] = useState("");
  const [bioField, setBioField] = useState("");

  const [editingSkillId, setEditingSkillId] = useState<number | null>(null);
  const [editingProficiency, setEditingProficiency] = useState(3);
  const [newSkillId, setNewSkillId] = useState("");
  const [newProficiency, setNewProficiency] = useState(3);

  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");

  const profileMutation = useMutation({
    mutationFn: (vars: ProfilePatchVars) =>
      api.crew.updateProfile(userId, { name: vars.name, contact: vars.contact, bio: vars.bio }),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["crew", "profile", userId] });
      const previous = queryClient.getQueryData<CrewProfile>(["crew", "profile", userId]);
      if (previous) {
        queryClient.setQueryData<CrewProfile>(["crew", "profile", userId], {
          ...previous,
          name: vars.name,
          contact: vars.contact,
          bio: vars.bio,
        });
      }
      return { previous };
    },
    onSuccess: () => setIsEditingProfile(false),
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["crew", "profile", userId], context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["crew", "profile", userId] }),
  });

  const skillMutation = useMutation({
    mutationFn: (vars: SkillSetVars) => api.crew.setSkill(userId, vars.skillName, vars.proficiency),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["crew", "profile", userId] });
      const previous = queryClient.getQueryData<CrewProfile>(["crew", "profile", userId]);
      if (previous) {
        const held = previous.skills.some((s) => s.skill_id === vars.skillId);
        const skills = held
          ? previous.skills.map((s) => (s.skill_id === vars.skillId ? { ...s, proficiency: vars.proficiency } : s))
          : [...previous.skills, { skill_id: vars.skillId, skill_name: vars.skillName, proficiency: vars.proficiency }];
        queryClient.setQueryData<CrewProfile>(["crew", "profile", userId], { ...previous, skills });
      }
      return { previous };
    },
    onSuccess: () => {
      setEditingSkillId(null);
      setNewSkillId("");
      setNewProficiency(3);
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["crew", "profile", userId], context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["crew", "profile", userId] }),
  });

  const addWindowMutation = useMutation({
    mutationFn: (vars: WindowAddVars) => api.crew.addAvailability(userId, vars.startDate, vars.endDate),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ["crew", "availability", userId] });
      const previous = queryClient.getQueryData<AvailabilityWindow[]>(["crew", "availability", userId]);
      const optimistic: AvailabilityWindow = {
        id: -Date.now(),
        crew_id: userId,
        start_date: vars.startDate,
        end_date: vars.endDate,
      };
      queryClient.setQueryData<AvailabilityWindow[]>(["crew", "availability", userId], (old) => [
        ...(old ?? []),
        optimistic,
      ]);
      return { previous };
    },
    onSuccess: () => {
      setWindowStart("");
      setWindowEnd("");
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["crew", "availability", userId], context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["crew", "availability", userId] }),
  });

  const removeWindowMutation = useMutation({
    mutationFn: (windowId: number) => api.crew.removeAvailability(userId, windowId),
    onMutate: async (windowId) => {
      await queryClient.cancelQueries({ queryKey: ["crew", "availability", userId] });
      const previous = queryClient.getQueryData<AvailabilityWindow[]>(["crew", "availability", userId]);
      queryClient.setQueryData<AvailabilityWindow[]>(["crew", "availability", userId], (old) =>
        (old ?? []).filter((w) => w.id !== windowId),
      );
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["crew", "availability", userId], context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["crew", "availability", userId] }),
  });

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
        <ErrorBanner
          message={errorMessage(profileQuery.error, "Couldn't load your profile.")}
          onRetry={() => profileQuery.refetch()}
        />
      </div>
    );
  }

  const profile = profileQuery.data;
  const skills = skillsQuery.data ?? [];
  const heldSkillIds = new Set(profile.skills.map((s) => s.skill_id));
  const availableToAdd = skills.filter((s) => !heldSkillIds.has(s.id));
  const windows = [...(availabilityQuery.data ?? [])].sort((a, b) => a.start_date.localeCompare(b.start_date));

  return (
    <div className="flex flex-1 flex-col gap-5 overflow-y-auto px-10 py-7">
      <div>
        <div className="text-[22px] font-bold">My Profile</div>
        <div className="mt-0.5 text-[13px] text-text-2">Your profile, skills, and availability.</div>
      </div>

      <div className="flex items-start gap-7">
        {/* Left column */}
        <div className="flex min-w-0 flex-1 flex-col gap-5">
          {/* Profile details */}
          <div className="rounded-[10px] border border-border bg-surface p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="text-[15px] font-bold">Profile</div>
              {!isEditingProfile && (
                <button
                  type="button"
                  onClick={() => {
                    setNameField(profile.name);
                    setContactField(profile.contact ?? "");
                    setBioField(profile.bio ?? "");
                    setIsEditingProfile(true);
                  }}
                  className="text-[12.5px] font-semibold text-accent hover:text-accent-dark"
                >
                  Edit
                </button>
              )}
            </div>

            {!isEditingProfile ? (
              <div className="flex flex-col gap-3 text-sm">
                <Field label="Name" value={profile.name} />
                <Field label="Email" value={profile.email} />
                <Field label="Contact" value={profile.contact} placeholder="No contact info provided." />
                <Field label="Bio" value={profile.bio} placeholder="No bio provided." />
              </div>
            ) : (
              <form
                className="flex flex-col gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  profileMutation.mutate({ name: nameField, contact: contactField, bio: bioField });
                }}
              >
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="profile-name" className="text-xs font-semibold text-text-2">
                    Name
                  </label>
                  <input
                    id="profile-name"
                    type="text"
                    value={nameField}
                    onChange={(e) => setNameField(e.target.value)}
                    className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[13px] focus:border-accent focus:outline-none"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="profile-contact" className="text-xs font-semibold text-text-2">
                    Contact
                  </label>
                  <input
                    id="profile-contact"
                    type="text"
                    value={contactField}
                    onChange={(e) => setContactField(e.target.value)}
                    placeholder="Phone, alternate email, etc."
                    className="w-full rounded-md border border-border bg-surface px-3 py-2 text-[13px] focus:border-accent focus:outline-none"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="profile-bio" className="text-xs font-semibold text-text-2">
                    Bio
                  </label>
                  <textarea
                    id="profile-bio"
                    value={bioField}
                    onChange={(e) => setBioField(e.target.value)}
                    rows={3}
                    className="w-full rounded-md border border-border bg-surface p-2 text-[13px] focus:border-accent focus:outline-none"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    type="submit"
                    disabled={profileMutation.isPending || nameField.trim().length === 0}
                    className="flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2 text-[13px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {profileMutation.isPending && <Spinner />}
                    Save
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsEditingProfile(false)}
                    className="rounded-md border border-border px-4 py-2 text-[13px] font-semibold text-text-2"
                  >
                    Cancel
                  </button>
                </div>
                {profileMutation.isError && (
                  <ErrorBanner message={errorMessage(profileMutation.error, "Couldn't save your profile.")} />
                )}
              </form>
            )}
          </div>

          {/* Skills */}
          <div className="rounded-[10px] border border-border bg-surface p-5">
            <div className="mb-4 text-[15px] font-bold">Skills</div>

            {profile.skills.length === 0 ? (
              <div className="mb-4 text-sm text-text-3">You haven't set any skill proficiencies yet.</div>
            ) : (
              <div className="mb-4 flex flex-col gap-2.5">
                {profile.skills.map((skill) => {
                  const isEditingRow = editingSkillId === skill.skill_id;
                  const isThisRow = skillMutation.variables?.skillId === skill.skill_id;
                  const isPending = skillMutation.isPending && isThisRow;
                  const isError = skillMutation.isError && isThisRow;

                  return (
                    <div key={skill.skill_id} className="rounded-lg bg-surface-2 px-3.5 py-3">
                      <div className="flex items-center justify-between">
                        <div className="text-[13.5px] font-semibold">{skill.skill_name}</div>

                        {!isEditingRow && (
                          <div className="flex items-center gap-3">
                            <div className="text-xs text-text-2">
                              {proficiencyLabel(skill.proficiency)}{" "}
                              <span className="font-mono text-text-3">({skill.proficiency}/5)</span>
                            </div>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingSkillId(skill.skill_id);
                                setEditingProficiency(skill.proficiency);
                              }}
                              className="text-[12px] font-semibold text-accent hover:text-accent-dark"
                            >
                              Change
                            </button>
                          </div>
                        )}
                      </div>

                      {isEditingRow && (
                        <div className="mt-2.5 flex items-center gap-2">
                          <select
                            aria-label={`Proficiency for ${skill.skill_name}`}
                            value={editingProficiency}
                            onChange={(e) => setEditingProficiency(Number(e.target.value))}
                            className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs focus:border-accent focus:outline-none"
                          >
                            {PROFICIENCY_LEVELS.map((level) => (
                              <option key={level} value={level}>
                                {level} — {proficiencyLabel(level)}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            disabled={isPending}
                            onClick={() =>
                              skillMutation.mutate({
                                skillId: skill.skill_id,
                                skillName: skill.skill_name,
                                proficiency: editingProficiency,
                              })
                            }
                            className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
                          >
                            {isPending && <Spinner />}
                            Save
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingSkillId(null)}
                            className="rounded-md border border-border px-3 py-1.5 text-xs font-semibold text-text-2"
                          >
                            Cancel
                          </button>
                        </div>
                      )}

                      {isError && (
                        <div className="mt-2">
                          <ErrorBanner message={errorMessage(skillMutation.error, "Couldn't update this skill.")} />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {availableToAdd.length > 0 && (
              <form
                className="flex flex-wrap items-end gap-2 border-t border-border pt-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!newSkillId) return;
                  const skill = skills.find((s) => s.id === Number(newSkillId));
                  if (!skill) return;
                  skillMutation.mutate({ skillId: skill.id, skillName: skill.name, proficiency: newProficiency });
                }}
              >
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="new-skill" className="text-xs font-semibold text-text-2">
                    Add a skill
                  </label>
                  <select
                    id="new-skill"
                    value={newSkillId}
                    onChange={(e) => setNewSkillId(e.target.value)}
                    className="rounded-md border border-border bg-surface px-2.5 py-2 text-[13px] focus:border-accent focus:outline-none"
                  >
                    <option value="">Choose a skill…</option>
                    {availableToAdd.map((skill) => (
                      <option key={skill.id} value={skill.id}>
                        {skill.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="new-skill-proficiency" className="text-xs font-semibold text-text-2">
                    Proficiency
                  </label>
                  <select
                    id="new-skill-proficiency"
                    value={newProficiency}
                    onChange={(e) => setNewProficiency(Number(e.target.value))}
                    className="rounded-md border border-border bg-surface px-2.5 py-2 text-[13px] focus:border-accent focus:outline-none"
                  >
                    {PROFICIENCY_LEVELS.map((level) => (
                      <option key={level} value={level}>
                        {level} — {proficiencyLabel(level)}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="submit"
                  disabled={!newSkillId || (skillMutation.isPending && skillMutation.variables?.skillId === Number(newSkillId))}
                  className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-[13px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Add
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Right column: availability */}
        <div className="w-80 flex-none rounded-[10px] border border-border bg-surface p-5">
          <div className="mb-1 text-[15px] font-bold">Unavailability</div>
          <div className="mb-4 text-xs leading-relaxed text-text-3">
            Dates you're not available. Without any windows, you're available by default. Windows can't overlap — to
            correct a mistake, remove it and add a new one.
          </div>

          {availabilityQuery.isError && (
            <div className="mb-3">
              <ErrorBanner
                message={errorMessage(availabilityQuery.error, "Couldn't load your availability.")}
                onRetry={() => availabilityQuery.refetch()}
              />
            </div>
          )}

          {availabilityQuery.isPending && (
            <div className="mb-3 flex items-center gap-2 text-sm text-text-3">
              <Spinner /> Loading…
            </div>
          )}

          {availabilityQuery.isSuccess && windows.length === 0 && (
            <div className="mb-4 text-sm text-text-3">No unavailability windows — you're marked available.</div>
          )}

          {windows.length > 0 && (
            <div className="mb-4 flex flex-col gap-2">
              {windows.map((w) => {
                const isPending = removeWindowMutation.isPending && removeWindowMutation.variables === w.id;
                return (
                  <div key={w.id} className="flex items-center justify-between rounded-lg bg-surface-2 px-3 py-2.5">
                    <div className="text-xs font-medium">
                      {formatDate(w.start_date)} – {formatDate(w.end_date)}
                    </div>
                    <button
                      type="button"
                      disabled={isPending}
                      onClick={() => removeWindowMutation.mutate(w.id)}
                      className="text-xs font-semibold text-danger hover:underline disabled:opacity-60"
                    >
                      {isPending ? "Removing…" : "Remove"}
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <form
            className="flex flex-col gap-2.5 border-t border-border pt-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (!windowStart || !windowEnd) return;
              addWindowMutation.mutate({ startDate: windowStart, endDate: windowEnd });
            }}
          >
            <div className="flex gap-2">
              <div className="flex flex-1 flex-col gap-1.5">
                <label htmlFor="window-start" className="text-xs font-semibold text-text-2">
                  Start
                </label>
                <input
                  id="window-start"
                  type="date"
                  value={windowStart}
                  onChange={(e) => setWindowStart(e.target.value)}
                  className="w-full rounded-md border border-border bg-surface px-2.5 py-2 text-xs focus:border-accent focus:outline-none"
                />
              </div>
              <div className="flex flex-1 flex-col gap-1.5">
                <label htmlFor="window-end" className="text-xs font-semibold text-text-2">
                  End
                </label>
                <input
                  id="window-end"
                  type="date"
                  value={windowEnd}
                  onChange={(e) => setWindowEnd(e.target.value)}
                  className="w-full rounded-md border border-border bg-surface px-2.5 py-2 text-xs focus:border-accent focus:outline-none"
                />
              </div>
            </div>
            <button
              type="submit"
              disabled={addWindowMutation.isPending || !windowStart || !windowEnd}
              className="flex items-center justify-center gap-2 rounded-md bg-accent px-4 py-2 text-[13px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {addWindowMutation.isPending && <Spinner />}
              Add window
            </button>
            {addWindowMutation.isError && (
              <ErrorBanner message={errorMessage(addWindowMutation.error, "Couldn't add this window.")} />
            )}
          </form>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, placeholder }: { label: string; value: string | null; placeholder?: string }) {
  return (
    <div>
      <div className="text-xs font-semibold text-text-3">{label}</div>
      <div className="mt-0.5">{value || <span className="text-text-3">{placeholder}</span>}</div>
    </div>
  );
}
