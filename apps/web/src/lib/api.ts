import type {
  CalendarCommitment,
  DemoCalendarResponse,
  WeeklyAnalysisResponse,
} from "@/types/analysis";
import {
  isDemoCalendar,
  isPlanResponse,
  isRepairResponse,
  isWeeklyAnalysisResponse,
} from "@/lib/guards";
import type { PlanRequest, PlanResponse } from "@/types/plan";
import type { RepairRequest, RepairResponse } from "@/types/repair";
import type {
  PlanningProfile,
  PlanningProfileValidationResponse,
} from "@/types/planning-profile";

// Public, non-secret configuration only. Never put credentials in NEXT_PUBLIC_* variables.
const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);

export type ValidateResult =
  | { ok: true; profile: PlanningProfile }
  | { ok: false; kind: "validation"; messages: string[] }
  | { ok: false; kind: "server"; message: string }
  | { ok: false; kind: "network"; message: string };

interface FastApiIssue {
  loc?: (string | number)[];
  msg?: string;
}

function describeIssue(issue: FastApiIssue): string {
  const msg = (issue.msg ?? "Invalid value").replace(/^Value error, /, "");
  const path = (issue.loc ?? [])
    .filter((part) => part !== "body")
    .map(String)
    .join(" › ");
  return path ? `${path}: ${msg}` : msg;
}

export async function validatePlanningProfile(
  profile: PlanningProfile,
  signal?: AbortSignal,
): Promise<ValidateResult> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/planning-profile/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
      signal,
    });
  } catch {
    return {
      ok: false,
      kind: "network",
      message: `We could not reach the Room for Both service at ${API_BASE_URL}. Check that the backend is running and try again.`,
    };
  }

  if (response.status === 422) {
    try {
      const body = (await response.json()) as { detail?: FastApiIssue[] | string };
      const messages = Array.isArray(body.detail)
        ? body.detail.map(describeIssue)
        : [String(body.detail ?? "The service could not accept this setup.")];
      return { ok: false, kind: "validation", messages };
    } catch {
      return { ok: false, kind: "validation", messages: ["The service rejected this setup."] };
    }
  }

  if (!response.ok) {
    return {
      ok: false,
      kind: "server",
      message: `The service had a problem (HTTP ${response.status}). Please try again in a moment.`,
    };
  }

  try {
    const body = (await response.json()) as PlanningProfileValidationResponse;
    if (body.status !== "valid" || !body.profile) throw new Error("unexpected response");
    return { ok: true, profile: body.profile };
  } catch {
    return {
      ok: false,
      kind: "server",
      message: "The service sent a response we did not understand.",
    };
  }
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; message: string };

const UNREACHABLE = "We could not reach the Room for Both service. Check that it is running and try again.";
const UNEXPECTED = "The service sent a response we did not understand. Please try again.";
const CALENDAR_TIMEOUT_MS = 15_000;
const ANALYSIS_TIMEOUT_MS = 90_000;
const PLAN_TIMEOUT_MS = 15_000;
// Several OR-Tools solves run before Nemotron ranks the candidates.
const REPAIR_TIMEOUT_MS = 90_000;

// Shared fetch + JSON handling. Error messages are fixed strings: raw bodies, URLs and
// status details are never passed to the UI.
async function requestJson<T>(
  path: string,
  init: RequestInit,
  isValid: (body: unknown) => body is T,
  failure: string,
): Promise<ApiResult<T>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    return { ok: false, message: UNREACHABLE };
  }
  if (!response.ok) return { ok: false, message: failure };

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { ok: false, message: UNEXPECTED };
  }
  return isValid(body) ? { ok: true, data: body } : { ok: false, message: UNEXPECTED };
}

export function getDemoCalendar(signal?: AbortSignal): Promise<ApiResult<DemoCalendarResponse>> {
  return requestJson(
    "/api/v1/calendar/demo",
    { method: "GET", signal: signal ?? AbortSignal.timeout(CALENDAR_TIMEOUT_MS) },
    isDemoCalendar,
    "The prepared demo calendar could not be loaded. Please try again.",
  );
}

export function analyzeWeek(
  profile: PlanningProfile,
  commitments: CalendarCommitment[],
  signal?: AbortSignal,
): Promise<ApiResult<WeeklyAnalysisResponse>> {
  return requestJson(
    "/api/v1/analysis/weekly",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, commitments }),
      signal: signal ?? AbortSignal.timeout(ANALYSIS_TIMEOUT_MS),
    },
    isWeeklyAnalysisResponse,
    "Your week could not be analyzed right now. Please try again.",
  );
}

export function generatePlan(
  request: PlanRequest,
  signal?: AbortSignal,
): Promise<ApiResult<PlanResponse>> {
  return requestJson(
    "/api/v1/plan/generate",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal: signal ?? AbortSignal.timeout(PLAN_TIMEOUT_MS),
    },
    isPlanResponse,
    "Your weekly plan could not be built right now. Please try again.",
  );
}

export function requestRepairOptions(
  request: RepairRequest,
  signal?: AbortSignal,
): Promise<ApiResult<RepairResponse>> {
  return requestJson(
    "/api/v1/repair/options",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal: signal ?? AbortSignal.timeout(REPAIR_TIMEOUT_MS),
    },
    isRepairResponse,
    "Repair options could not be built right now. Please try again.",
  );
}
