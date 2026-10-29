// Runtime checks for backend JSON, so a malformed response never reaches rendering.
import type { DemoCalendarResponse, WeeklyAnalysisResponse } from "@/types/analysis";
import type { ApprovedPlanRecord, PlanResponse } from "@/types/plan";
import type { EvaluationReport } from "@/types/evaluation";
import type { ConflictResponse, RepairResponse } from "@/types/repair";
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

function isBlock(v: unknown): boolean {
  return (
    isObj(v) &&
    isNonEmpty(v.id) &&
    (v.outcome_type === "work" || v.outcome_type === "personal") &&
    isNonEmpty(v.outcome_title) &&
    isDay(v.day) &&
    isStr(v.start_time) &&
    isStr(v.end_time) &&
    isMinutes(v.duration_minutes) &&
    typeof v.inside_preferred_focus_window === "boolean" &&
    typeof v.uses_soft_boundary === "boolean"
  );
}

function isConstraintsSummary(v: unknown): boolean {
  return (
    isObj(v) &&
    isMinutes(v.candidate_slots) &&
    isMinutes(v.slots_blocked_by_commitments) &&
    isMinutes(v.slots_blocked_by_hard_boundaries) &&
    isMinutes(v.soft_boundary_slots) &&
    isMinutes(v.preferred_focus_slots) &&
    isMinutes(v.max_daily_work_minutes) &&
    isMinutes(v.minimum_break_minutes) &&
    strings(v.rules)
  );
}

function isSolver(v: unknown): boolean {
  return (
    isObj(v) &&
    v.name === "Google OR-Tools CP-SAT" &&
    isNonEmpty(v.status) &&
    (v.objective_value === null ||
      (typeof v.objective_value === "number" && Number.isFinite(v.objective_value))) &&
    isMinutes(v.wall_time_seconds)
  );
}

export function isPlanResponse(body: unknown): body is PlanResponse {
  return (
    isObj(body) &&
    (body.status === "optimal" ||
      body.status === "feasible" ||
      body.status === "partial" ||
      body.status === "infeasible") &&
    body.slot_minutes === 15 &&
    arrayOf(body.blocks, isBlock) &&
    isMinutes(body.requested_work_minutes) &&
    isMinutes(body.target_work_minutes) &&
    isMinutes(body.scheduled_work_minutes) &&
    isMinutes(body.unscheduled_work_minutes) &&
    isMinutes(body.requested_personal_minutes) &&
    isMinutes(body.target_personal_minutes) &&
    isMinutes(body.scheduled_personal_minutes) &&
    isMinutes(body.unscheduled_personal_minutes) &&
    isSolver(body.solver) &&
    isConstraintsSummary(body.constraints_summary) &&
    strings(body.warnings)
  );
}

export function isApprovedPlanRecord(body: unknown): body is ApprovedPlanRecord {
  return (
    isObj(body) &&
    body.version === 1 &&
    isStr(body.approved_at) &&
    !Number.isNaN(Date.parse(body.approved_at)) &&
    isPlanResponse(body.plan)
  );
}

// --- Conflict detection and repair options ---------------------------------------------------

const TIME = /^\d{2}:\d{2}(:\d{2})?$/;
const isTime = (v: unknown) => isStr(v) && TIME.test(v);
const STRATEGIES = ["move", "simplify", "delegate", "drop"];
const isStrategy = (v: unknown) => isStr(v) && STRATEGIES.includes(v);

function isConflictRecord(v: unknown): boolean {
  return (
    isObj(v) &&
    (v.conflict_type === "scheduled_block" ||
      v.conflict_type === "existing_commitment" ||
      v.conflict_type === "hard_boundary") &&
    isNonEmpty(v.conflicting_item_id) &&
    isNonEmpty(v.conflicting_item_title) &&
    isDay(v.day) &&
    isTime(v.conflicting_start_time) &&
    isTime(v.conflicting_end_time) &&
    isTime(v.overlap_start_time) &&
    isTime(v.overlap_end_time) &&
    isMinutes(v.overlap_minutes) &&
    (v.outcome_type === null || v.outcome_type === "work" || v.outcome_type === "personal")
  );
}

export function isConflictResponse(body: unknown): body is ConflictResponse {
  if (
    !isObj(body) ||
    !(body.status === "clear" || body.status === "conflict") ||
    typeof body.conflict_detected !== "boolean" ||
    typeof body.repair_required !== "boolean" ||
    body.repair_required !== body.conflict_detected ||
    body.conflict_detected !== (body.status === "conflict") ||
    !isCommitment(body.unexpected_commitment) ||
    !isTime((body.unexpected_commitment as Obj).start_time) ||
    !isTime((body.unexpected_commitment as Obj).end_time) ||
    !arrayOf(body.conflicts, isConflictRecord) ||
    !arrayOf(body.affected_block_ids, isNonEmpty) ||
    !isNonEmpty(body.summary)
  ) {
    return false;
  }
  const affected = body.affected_block_ids as string[];
  const conflicts = body.conflicts as unknown[];
  if (new Set(affected).size !== affected.length) return false;
  // A clear result has nothing in it; a conflict result names at least one record.
  return body.status === "clear"
    ? conflicts.length === 0 && affected.length === 0
    : conflicts.length > 0;
}

const VALIDATION_FLAGS = [
  "valid",
  "no_unexpected_commitment_overlap",
  "no_existing_commitment_overlap",
  "no_hard_boundary_overlap",
  "no_internal_block_overlap",
  "targets_consistent",
];

// Only fully verified options are ever returned by the backend, so every flag must be true.
function isVerifiedValidation(v: unknown): boolean {
  return isObj(v) && VALIDATION_FLAGS.every((flag) => v[flag] === true) && strings(v.notes);
}

function isRepairOption(v: unknown): boolean {
  return (
    isObj(v) &&
    isStrategy(v.id) &&
    v.strategy === v.id &&
    typeof v.rank === "number" &&
    Number.isInteger(v.rank) &&
    v.rank >= 1 &&
    isNonEmpty(v.title) &&
    isNonEmpty(v.explanation) &&
    typeof v.recommended === "boolean" &&
    isPlanResponse(v.revised_plan) &&
    v.revised_plan.status !== "infeasible" &&
    isMinutes(v.original_work_minutes) &&
    isMinutes(v.original_personal_minutes) &&
    isMinutes(v.target_work_minutes) &&
    isMinutes(v.target_personal_minutes) &&
    isMinutes(v.reduced_work_minutes) &&
    isMinutes(v.reduced_personal_minutes) &&
    isMinutes(v.delegated_work_minutes) &&
    isMinutes(v.dropped_work_minutes) &&
    isMinutes(v.dropped_personal_minutes) &&
    isVerifiedValidation(v.validation)
  );
}

export function isRepairResponse(body: unknown): body is RepairResponse {
  if (
    !isObj(body) ||
    !(
      body.status === "not_needed" ||
      body.status === "manual_resolution_required" ||
      body.status === "options_ready" ||
      body.status === "no_valid_options"
    ) ||
    !(
      body.reasoning_source === "nemotron" ||
      body.reasoning_source === "fallback" ||
      body.reasoning_source === "not_used"
    ) ||
    body.model_provider !== "Nebius Token Factory" ||
    !isNonEmpty(body.model_name) ||
    !(body.recommended_option_id === null || isStrategy(body.recommended_option_id)) ||
    !(body.fallback_message === null || isStr(body.fallback_message)) ||
    !isConflictResponse(body.conflict) ||
    !arrayOf(body.options, isRepairOption)
  ) {
    return false;
  }

  const options = body.options as Obj[];
  const ids = new Set(options.map((o) => o.id));
  const ranks = options.map((o) => o.rank as number).sort((a, b) => a - b);
  if (ids.size !== options.length || !ranks.every((rank, i) => rank === i + 1)) return false;
  // not_needed means a clear result; every other status is reached only after a conflict.
  if ((body.status === "not_needed") !== (body.conflict.status === "clear")) return false;

  // Only options_ready involves a ranking, so every other status carries no model source.
  if (body.status !== "options_ready") {
    return (
      options.length === 0 &&
      body.recommended_option_id === null &&
      body.reasoning_source === "not_used"
    );
  }
  const recommended = options.filter((o) => o.recommended === true);
  return (
    options.length > 0 &&
    (body.reasoning_source === "nemotron" || body.reasoning_source === "fallback") &&
    recommended.length === 1 &&
    recommended[0].id === body.recommended_option_id
  );
}

// --- Reliability evaluation ------------------------------------------------------------------

const isCount = (v: unknown): v is number => isMinutes(v) && Number.isInteger(v);
const CATEGORIES = ["capacity", "scheduling", "conflict_detection", "repair_validation"];
const UTC_ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$/;

function isEvaluationCase(v: unknown): boolean {
  return (
    isObj(v) &&
    isNonEmpty(v.id) &&
    isStr(v.category) &&
    CATEGORIES.includes(v.category) &&
    isNonEmpty(v.name) &&
    typeof v.passed === "boolean" &&
    isMinutes(v.duration_ms) &&
    isCount(v.checks_passed) &&
    isCount(v.checks_total) &&
    v.checks_total > 0 &&
    v.checks_passed <= v.checks_total &&
    v.passed === (v.checks_passed === v.checks_total) &&
    isNonEmpty(v.summary)
  );
}

export function isEvaluationReport(body: unknown): body is EvaluationReport {
  if (
    !isObj(body) ||
    !(body.status === "passed" || body.status === "failed") ||
    body.suite_name !== "Room for Both deterministic reliability suite" ||
    !isStr(body.generated_at) ||
    !UTC_ISO.test(body.generated_at) ||
    Number.isNaN(Date.parse(body.generated_at)) ||
    body.model_calls_made !== 0 ||
    !isObj(body.summary) ||
    !Array.isArray(body.cases) ||
    !body.cases.every(isEvaluationCase) ||
    !arrayOf(body.architecture_guarantees, isNonEmpty)
  ) {
    return false;
  }

  const s = body.summary;
  const cases = body.cases as Obj[];
  const ids = new Set(cases.map((c) => c.id));
  const passed = cases.filter((c) => c.passed === true).length;
  const sum = (key: string) => cases.reduce((total, c) => total + (c[key] as number), 0);
  if (
    !isCount(s.total_cases) ||
    !isCount(s.passed_cases) ||
    !isCount(s.failed_cases) ||
    !isMinutes(s.pass_rate_percent) ||
    !isCount(s.total_checks) ||
    !isCount(s.passed_checks) ||
    !isMinutes(s.total_duration_ms)
  ) {
    return false;
  }
  const expectedRate = s.total_cases === 0 ? 0 : (100 * s.passed_cases) / s.total_cases;
  return (
    ids.size === cases.length &&
    s.total_cases === cases.length &&
    s.passed_cases === passed &&
    s.passed_cases + s.failed_cases === s.total_cases &&
    s.passed_checks <= s.total_checks &&
    s.total_checks === sum("checks_total") &&
    s.passed_checks === sum("checks_passed") &&
    s.pass_rate_percent <= 100 &&
    Math.abs(s.pass_rate_percent - expectedRate) <= 0.01 &&
    Math.abs(s.total_duration_ms - sum("duration_ms")) <= 0.05 &&
    body.status === (cases.length > 0 && passed === cases.length ? "passed" : "failed")
  );
}
