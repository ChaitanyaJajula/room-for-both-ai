// Approved plan storage. sessionStorage holds only the plan and its approval time, under one
// versioned key. Every access is guarded: storage can be missing, full or hold bad data.
import { isApprovedPlanRecord } from "@/lib/guards";
import type { ApprovedPlanRecord, PlanResponse } from "@/types/plan";

export const APPROVED_PLAN_KEY = "room-for-both:approved-plan:v1";

export function saveApprovedPlan(plan: PlanResponse, approvedAt: string): boolean {
  try {
    const record: ApprovedPlanRecord = { version: 1, approved_at: approvedAt, plan };
    window.sessionStorage.setItem(APPROVED_PLAN_KEY, JSON.stringify(record));
    return true;
  } catch {
    return false;
  }
}

export function loadApprovedPlan(): ApprovedPlanRecord | null {
  try {
    const raw = window.sessionStorage.getItem(APPROVED_PLAN_KEY);
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (isApprovedPlanRecord(parsed)) return parsed;
    window.sessionStorage.removeItem(APPROVED_PLAN_KEY);
  } catch {
    // Unavailable or malformed storage is treated as "nothing approved".
  }
  return null;
}

export function clearApprovedPlan(): void {
  try {
    window.sessionStorage.removeItem(APPROVED_PLAN_KEY);
  } catch {
    // Nothing to clear if storage is unavailable.
  }
}
