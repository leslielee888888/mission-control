/**
 * Typed RPC-flavored client over the FastAPI backend.
 *
 * Judgment call (T8, §10 #21): the PRD's "typed client generated from the
 * API's schema" is satisfied here with hand-written types (api/types.ts)
 * instead of a generated OpenAPI client. For 8 routes across 4 resources,
 * adding an `openapi-typescript` (or similar) codegen step to the build
 * would be more tooling than the showcase needs; the request/response
 * shapes were read directly from `api/routes/*.py` so they stay accurate.
 * Calls still read RPC-style — `api.mission.approve(id)` — which is the
 * actual DX goal; only the type *source* differs from the PRD's suggestion.
 * If this app grows past a showcase, generating from `/openapi.json` is the
 * first thing to revisit.
 */

import type {
  Assignment,
  AvailabilityWindow,
  CrewProfile,
  CrewRosterEntry,
  CrewSkill,
  FieldError,
  LoginResponse,
  Mission,
  MissionDetail,
  RequirementMatch,
  Skill,
  User,
} from "./types";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

/** Thrown for any non-2xx response. Carries the parsed `detail` from the
 * API's error envelope (api/errors.py): a plain string for most errors, or
 * a list of field errors for 422 validation failures. */
export class ApiError extends Error {
  readonly status: number;
  readonly fieldErrors?: FieldError[];

  constructor(status: number, detail: unknown) {
    const { message, fieldErrors } = ApiError.parseDetail(detail);
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }

  private static parseDetail(detail: unknown): { message: string; fieldErrors?: FieldError[] } {
    if (typeof detail === "string" && detail.length > 0) {
      return { message: detail };
    }
    if (Array.isArray(detail)) {
      const fieldErrors = detail as FieldError[];
      return {
        message: fieldErrors.map((e) => `${e.field}: ${e.message}`).join("; ") || "Invalid request.",
        fieldErrors,
      };
    }
    return { message: "Something went wrong. Please try again." };
  }
}

type TokenGetter = () => string | null;

let getToken: TokenGetter = () => null;

/** Wired up once by AuthContext so the client always sends the current
 * token without every call site having to thread it through. */
export function configureAuthToken(getter: TokenGetter): void {
  getToken = getter;
}

/** Called on every 401 so the app can drop a stale/invalid token and
 * bounce back to the login screen. Wired up by AuthContext. */
let onUnauthorized: () => void = () => {};
export function configureUnauthorizedHandler(handler: () => void): void {
  onUnauthorized = handler;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (res.status === 204) {
    return undefined as T;
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    if (res.status === 401) onUnauthorized();
    const detail = body && typeof body === "object" && "detail" in (body as Record<string, unknown>)
      ? (body as Record<string, unknown>).detail
      : body;
    throw new ApiError(res.status, detail);
  }

  return body as T;
}

const get = <T>(path: string): Promise<T> => request<T>(path, { method: "GET" });
const post = <T>(path: string, data?: unknown): Promise<T> =>
  request<T>(path, { method: "POST", body: data === undefined ? undefined : JSON.stringify(data) });
const patch = <T>(path: string, data: unknown): Promise<T> =>
  request<T>(path, { method: "PATCH", body: JSON.stringify(data) });
const put = <T>(path: string, data: unknown): Promise<T> =>
  request<T>(path, { method: "PUT", body: JSON.stringify(data) });
const del = <T>(path: string): Promise<T> => request<T>(path, { method: "DELETE" });

export const api = {
  auth: {
    login: (email: string, password: string): Promise<LoginResponse> =>
      post<LoginResponse>("/auth/login", { email, password }),
    whoami: (): Promise<User> => get<User>("/auth/whoami"),
  },
  mission: {
    list: (): Promise<Mission[]> => get<Mission[]>("/missions"),
    get: (id: number): Promise<MissionDetail> => get<MissionDetail>(`/missions/${id}`),
    approve: (id: number): Promise<Mission> => post<Mission>(`/missions/${id}/approve`),
    reject: (id: number, reason: string): Promise<Mission> =>
      post<Mission>(`/missions/${id}/reject`, { reason }),
  },
  match: {
    /** Runs the matcher for every requirement on the mission (or, with
     * `requirementId`, just one). */
    run: (missionId: number, requirementId?: number): Promise<RequirementMatch[]> => {
      const query = requirementId !== undefined ? `?requirement_id=${requirementId}` : "";
      return get<RequirementMatch[]>(`/missions/${missionId}/match${query}`);
    },
  },
  assignment: {
    /** Director/Lead: every assignment in the org. Crew Member: only their
     * own (services/assignment.py scopes this server-side). */
    list: (): Promise<Assignment[]> => get<Assignment[]>("/assignments"),
    propose: (missionId: number, requirementId: number, crewId: number): Promise<Assignment> =>
      post<Assignment>("/assignments", {
        mission_id: missionId,
        requirement_id: requirementId,
        crew_id: crewId,
      }),
    respond: (assignmentId: number, action: "accept" | "decline"): Promise<Assignment> =>
      post<Assignment>(`/assignments/${assignmentId}/respond`, { action }),
  },
  crew: {
    /** Director/Lead only: the org's crew_member roster (api/routes/crew.py). */
    list: (): Promise<CrewRosterEntry[]> => get<CrewRosterEntry[]>("/crew"),
    /** Self, or (Director/Lead) another crew member's — read-only for the
     * latter case; the API itself enforces who may edit. */
    profile: (userId: number): Promise<CrewProfile> => get<CrewProfile>(`/crew/${userId}/profile`),
    /** Self only. Only the given fields change (PATCH semantics). */
    updateProfile: (
      userId: number,
      patchData: { name?: string; contact?: string; bio?: string },
    ): Promise<CrewProfile> => patch<CrewProfile>(`/crew/${userId}/profile`, patchData),
    /** Self, or a Director acting on the crew member's behalf. Upserts by
     * skill name — adds the skill if not already held, else updates it. */
    setSkill: (userId: number, skillName: string, proficiency: number): Promise<CrewSkill> =>
      put<CrewSkill>(`/crew/${userId}/skills`, { skill_name: skillName, proficiency }),
    listAvailability: (userId: number): Promise<AvailabilityWindow[]> =>
      get<AvailabilityWindow[]>(`/crew/${userId}/availability`),
    addAvailability: (userId: number, startDate: string, endDate: string): Promise<AvailabilityWindow> =>
      post<AvailabilityWindow>(`/crew/${userId}/availability`, { start_date: startDate, end_date: endDate }),
    removeAvailability: (userId: number, windowId: number): Promise<void> =>
      del<void>(`/crew/${userId}/availability/${windowId}`),
  },
  skills: {
    /** Any authenticated user in the org (api/routes/skills.py). */
    list: (): Promise<Skill[]> => get<Skill[]>("/skills"),
    /** Director only. */
    create: (name: string, category?: string): Promise<Skill> =>
      post<Skill>("/skills", { name, category: category ?? null }),
  },
};
