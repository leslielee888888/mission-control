/**
 * Hand-written types mirroring the Pydantic response/request models in
 * `api/routes/*.py` (auth, mission, match, assignment). See client.ts for
 * why this is hand-written rather than generated from the OpenAPI schema.
 */

export type Role = "director" | "mission_lead" | "crew_member";

export type MissionStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "active"
  | "completed"
  | "cancelled";

export type AssignmentStatus = "proposed" | "confirmed" | "declined";

export interface User {
  id: number;
  org_id: number;
  email: string;
  name: string;
  role: Role;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export interface Mission {
  id: number;
  org_id: number;
  created_by: number;
  name: string;
  description: string;
  start_date: string;
  end_date: string;
  status: MissionStatus;
}

export interface Requirement {
  id: number;
  mission_id: number;
  skill_id: number;
  skill_name: string;
  min_proficiency: number;
  headcount: number;
  confirmed: number;
}

export interface MissionDetail extends Mission {
  requirements: Requirement[];
}

export interface MatchCandidate {
  crew_id: number;
  crew_name: string;
  score: number;
  proficiency_surplus_score: number;
  workload_score: number;
  availability_margin_score: number;
  breakdown: string;
}

export interface RequirementMatch {
  requirement_id: number;
  skill_id: number;
  min_proficiency: number;
  headcount: number;
  candidates: MatchCandidate[];
}

export interface Assignment {
  id: number;
  mission_id: number;
  requirement_id: number;
  crew_id: number;
  proposed_by: number;
  status: AssignmentStatus;
  proposed_at: string;
  responded_at: string | null;
}

/** Field-level shape the API's 422 handler emits (api/errors.py). */
export interface FieldError {
  field: string;
  message: string;
}

/** One entry in a Director/Lead's org roster (`GET /crew`, api/routes/crew.py). */
export interface CrewRosterEntry {
  user_id: number;
  name: string;
  email: string;
  skill_count: number;
}

/** A skill proficiency held by a crew member, as it appears on their profile. */
export interface CrewSkill {
  skill_id: number;
  skill_name: string;
  proficiency: number;
}

/** `GET /crew/{id}/profile` response — self, or (Director/Lead) another
 * crew member's, read-only in that case. */
export interface CrewProfile {
  user_id: number;
  org_id: number;
  name: string;
  email: string;
  contact: string | null;
  bio: string | null;
  skills: CrewSkill[];
}

/** An org-scoped skill taxonomy entry (`/skills`, FR-5). */
export interface Skill {
  id: number;
  org_id: number;
  name: string;
  category: string | null;
}

/** An unavailability window on a crew member's profile (FR-7). Absent any
 * window, a crew member defaults to available. */
export interface AvailabilityWindow {
  id: number;
  crew_id: number;
  start_date: string;
  end_date: string;
}
