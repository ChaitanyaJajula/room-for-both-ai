// Runtime checks for backend JSON, so a malformed response never reaches rendering.
import type { DemoCalendarResponse, WeeklyAnalysisResponse } from "@/types/analysis";
import { DAYS_OF_WEEK } from "@/types/planning-profile";

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const isStr = (v: unknown): v is string => typeof v === "string";
const isNonEmpty = (v: unknown): v is string => isStr(v) && v.trim().length > 0;
const isMinutes = (v: unknown): v is number =>
  typeof v === "number" && Number.isFinite(v) && v >= 0;
const isDay = (v: unknown) => isStr(v) && (DAYS_OF_WEEK as readonly string[]).includes(v);
const arrayOf = (v: unknown, check: (item: unknown) => boolean) =>
  Array.isArray(v) && v.every(check);
const strings = (v: unknown) => arrayOf(v, isStr);

function isCommitment(v: unknown): boolean {
  return (
    isObj(v) &&
    isNonEmpty(v.id) &&
    isNonEmpty(v.title) &&
    isDay(v.day) &&
    isStr(v.start_time) &&
    isStr(v.end_time) &&
    (v.category === "work" || v.category === "personal") &&
    typeof v.is_fixed === "boolean" &&
    (v.description === null || isStr(v.description))
  );
}

export function isDemoCalendar(body: unknown): body is DemoCalendarResponse {
  return (
    isObj(body) &&
    isStr(body.name) &&
    isStr(body.description) &&
    arrayOf(body.commitments, isCommitment)
  );
}

function isDaily(v: unknown): boolean {
  return (
    isObj(v) &&
    isDay(v.day) &&
    isMinutes(v.work_window_minutes) &&
    isMinutes(v.occupied_minutes) &&
    isMinutes(v.free_minutes) &&
    isMinutes(v.reserved_break_minutes) &&
    isMinutes(v.schedulable_focus_minutes) &&
    strings(v.commitment_ids)
  );
}

function isWeekly(v: unknown): boolean {
  return (
    isObj(v) &&
    isMinutes(v.work_window_minutes) &&
    isMinutes(v.occupied_minutes) &&
    isMinutes(v.free_minutes) &&
    isMinutes(v.reserved_break_minutes) &&
    isMinutes(v.schedulable_focus_minutes) &&
    isMinutes(v.protected_personal_target_minutes)
  );
}

function isSignals(v: unknown): boolean {
  return (
    isObj(v) &&
    arrayOf(v.zero_capacity_days, isDay) &&
    arrayOf(v.days_at_focus_cap, isDay) &&
    strings(v.commitments_outside_work_hours) &&
    strings(v.commitments_partially_outside_work_hours) &&
    arrayOf(
      v.overlapping_commitments,
      (p) => isObj(p) && isDay(p.day) && isStr(p.first_id) && isStr(p.second_id),
    )
  );
}

function isOutcome(v: unknown): boolean {
  return isObj(v) && isNonEmpty(v.title) && isNonEmpty(v.reason) && isMinutes(v.estimated_minutes);
}

function isAnalysis(v: unknown): boolean {
  return (
    isObj(v) &&
    (v.classification === "balanced" ||
      v.classification === "tight" ||
      v.classification === "overloaded") &&
    isNonEmpty(v.summary) &&
    isNonEmpty(v.capacity_explanation) &&
    isOutcome(v.work_outcome) &&
    isOutcome(v.personal_outcome) &&
    strings(v.risks) &&
    v.model_provider === "Nebius Token Factory" &&
    isNonEmpty(v.model_name) &&
    (v.source === "nemotron" || v.source === "fallback") &&
    (v.fallback_reason === null || isStr(v.fallback_reason))
  );
}

export function isWeeklyAnalysisResponse(body: unknown): body is WeeklyAnalysisResponse {
  if (!isObj(body) || !isObj(body.capacity)) return false;
  return (
    arrayOf(body.capacity.daily, isDaily) &&
    isWeekly(body.capacity.weekly) &&
    isSignals(body.capacity.signals) &&
    isAnalysis(body.analysis)
  );
}
