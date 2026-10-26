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
