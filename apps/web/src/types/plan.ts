// Mirrors services/api/app/models/schedule.py.
// Times are "HH:MM:SS" strings, as the backend serialises datetime.time.
import type { CalendarCommitment, Outcome } from "./analysis";
import type { DayOfWeek, PlanningProfile } from "./planning-profile";

export type OutcomeType = "work" | "personal";
export type PlanStatus = "optimal" | "feasible" | "partial" | "infeasible";

export interface PlanRequest {
  profile: PlanningProfile;
  commitments: CalendarCommitment[];
  work_outcome: Outcome;
  personal_outcome: Outcome;
}

export interface ScheduledBlock {
  id: string;
  outcome_type: OutcomeType;
  outcome_title: string;
  day: DayOfWeek;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  inside_preferred_focus_window: boolean;
  uses_soft_boundary: boolean;
}

export interface SolverInfo {
  name: "Google OR-Tools CP-SAT";
  status: string;
  objective_value: number | null;
  wall_time_seconds: number;
}

export interface ConstraintsSummary {
  candidate_slots: number;
  slots_blocked_by_commitments: number;
  slots_blocked_by_hard_boundaries: number;
  soft_boundary_slots: number;
  preferred_focus_slots: number;
  max_daily_work_minutes: number;
  minimum_break_minutes: number;
  rules: string[];
}

export interface PlanResponse {
  status: PlanStatus;
  slot_minutes: 15;
  blocks: ScheduledBlock[];
  requested_work_minutes: number;
  target_work_minutes: number;
  scheduled_work_minutes: number;
  unscheduled_work_minutes: number;
  requested_personal_minutes: number;
  target_personal_minutes: number;
  scheduled_personal_minutes: number;
  unscheduled_personal_minutes: number;
  solver: SolverInfo;
  constraints_summary: ConstraintsSummary;
  warnings: string[];
}

// What is kept in sessionStorage once the user approves a plan.
export interface ApprovedPlanRecord {
  version: 1;
  approved_at: string;
  plan: PlanResponse;
}
