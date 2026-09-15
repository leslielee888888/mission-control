/** Formats an ISO `YYYY-MM-DD` date as e.g. "Mar 4". */
export function formatDate(isoDate: string): string {
  // Avoid the UTC/local timezone-shift trap `new Date("2026-03-04")` has —
  // append a time so it's parsed as local midnight, not UTC midnight.
  const date = new Date(`${isoDate}T00:00:00`);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Formats a start/end date pair as e.g. "Mar 4 – Mar 16". */
export function formatDateRange(startIso: string, endIso: string): string {
  return `${formatDate(startIso)} – ${formatDate(endIso)}`;
}

/** Up to two uppercase initials from a display name, for avatar chips. */
export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase();
}

const ROLE_LABELS: Record<string, string> = {
  director: "Director",
  mission_lead: "Mission Lead",
  crew_member: "Crew Member",
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}

const MISSION_STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  pending_approval: "Pending approval",
  approved: "Approved",
  active: "Active",
  completed: "Completed",
  cancelled: "Cancelled",
};

export function missionStatusLabel(status: string): string {
  return MISSION_STATUS_LABELS[status] ?? status;
}

const ASSIGNMENT_STATUS_LABELS: Record<string, string> = {
  proposed: "Proposed",
  confirmed: "Confirmed",
  declined: "Declined",
};

export function assignmentStatusLabel(status: string): string {
  return ASSIGNMENT_STATUS_LABELS[status] ?? status;
}

/** Presentation-layer label for the 1-5 proficiency scale (PRD Q1: the
 * scale itself is stored as a plain int; labels are display-only). */
const PROFICIENCY_LABELS: Record<number, string> = {
  1: "Novice",
  2: "Beginner",
  3: "Intermediate",
  4: "Advanced",
  5: "Expert",
};

export function proficiencyLabel(level: number): string {
  return PROFICIENCY_LABELS[level] ?? `Level ${level}`;
}
