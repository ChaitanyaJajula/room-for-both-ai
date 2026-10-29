// Mirrors services/api/app/models/{conflict,repair}.py.
// Times are "HH:MM:SS" strings, as the backend serialises datetime.time.
import type { CalendarCommitment, Outcome } from "./analysis";
import type { OutcomeType, PlanResponse } from "./plan";
import type { DayOfWeek, PlanningProfile } from "./planning-profile";

export type ConflictType = "scheduled_block" | "existing_commitment" | "hard_boundary";

export interface ConflictRecord {
  conflict_type: ConflictType;
  conflicting_item_id: string;
  conflicting_item_title: string;
  day: DayOfWeek;
  conflicting_start_time: string;
  conflicting_end_time: string;
  overlap_start_time: string;
  overlap_end_time: string;
  overlap_minutes: number;
  outcome_type: OutcomeType | null;
}

export interface ConflictResponse {
  status: "clear" | "conflict";
  conflict_detected: boolean;
  repair_required: boolean;
  unexpected_commitment: CalendarCommitment;
  conflicts: ConflictRecord[];
  affected_block_ids: string[];
  summary: string;
}

export type RepairStrategy = "move" | "simplify" | "delegate" | "drop";
export type RepairResponseStatus =
  | "not_needed"
  | "manual_resolution_required"
  | "options_ready"
  | "no_valid_options";
export type ReasoningSource = "nemotron" | "fallback" | "not_used";

export interface RepairValidation {
  valid: boolean;
  no_unexpected_commitment_overlap: boolean;
  no_existing_commitment_overlap: boolean;
  no_hard_boundary_overlap: boolean;
  no_internal_block_overlap: boolean;
  targets_consistent: boolean;
  notes: string[];
}

export interface RepairOption {
  id: RepairStrategy;
  strategy: RepairStrategy;
  rank: number;
  title: string;
  explanation: string;
  recommended: boolean;
  revised_plan: PlanResponse;
  original_work_minutes: number;
  original_personal_minutes: number;
  target_work_minutes: number;
  target_personal_minutes: number;
  reduced_work_minutes: number;
  reduced_personal_minutes: number;
  delegated_work_minutes: number;
  dropped_work_minutes: number;
  dropped_personal_minutes: number;
  validation: RepairValidation;
}

export interface RepairRequest {
  profile: PlanningProfile;
  commitments: CalendarCommitment[];
  approved_plan: PlanResponse;
  unexpected_commitment: CalendarCommitment;
  work_outcome: Outcome;
  personal_outcome: Outcome;
}

export interface RepairResponse {
  status: RepairResponseStatus;
  conflict: ConflictResponse;
  options: RepairOption[];
  recommended_option_id: RepairStrategy | null;
  reasoning_source: ReasoningSource;
  model_provider: "Nebius Token Factory";
  model_name: string;
  // Typed for completeness. The UI shows its own fixed fallback text instead.
  fallback_message: string | null;
}
