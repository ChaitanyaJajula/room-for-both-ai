// Mirrors services/api/app/models/{calendar,capacity,analysis}.py.
// Times are "HH:MM:SS" strings, as the backend serialises datetime.time.
import type { DayOfWeek, PlanningProfile } from "./planning-profile";

export type CommitmentCategory = "work" | "personal";

export interface CalendarCommitment {
  id: string;
  title: string;
  day: DayOfWeek;
  start_time: string;
  end_time: string;
  category: CommitmentCategory;
  is_fixed: boolean;
  description: string | null;
}

export interface DemoCalendarResponse {
  name: string;
  description: string;
  commitments: CalendarCommitment[];
}

export interface DailyCapacity {
  day: DayOfWeek;
  work_window_minutes: number;
  occupied_minutes: number;
  free_minutes: number;
  reserved_break_minutes: number;
  schedulable_focus_minutes: number;
  commitment_ids: string[];
}

export interface WeeklyCapacitySummary {
  work_window_minutes: number;
  occupied_minutes: number;
  free_minutes: number;
  reserved_break_minutes: number;
  schedulable_focus_minutes: number;
  protected_personal_target_minutes: number;
}

export interface OverlappingPair {
  day: DayOfWeek;
  first_id: string;
  second_id: string;
}

export interface CapacitySignals {
  zero_capacity_days: DayOfWeek[];
  days_at_focus_cap: DayOfWeek[];
  commitments_outside_work_hours: string[];
  commitments_partially_outside_work_hours: string[];
  overlapping_commitments: OverlappingPair[];
}

export interface CapacityResponse {
  daily: DailyCapacity[];
  weekly: WeeklyCapacitySummary;
  signals: CapacitySignals;
}

export type Classification = "balanced" | "tight" | "overloaded";

export interface Outcome {
  title: string;
  reason: string;
  estimated_minutes: number;
}

export interface WeeklyAnalysis {
  classification: Classification;
  summary: string;
  capacity_explanation: string;
  work_outcome: Outcome;
  personal_outcome: Outcome;
  risks: string[];
  model_provider: "Nebius Token Factory";
  model_name: string;
  source: "nemotron" | "fallback";
  // Typed for debugging only. Never render this in the UI.
  fallback_reason: string | null;
}

export interface WeeklyAnalysisRequest {
  profile: PlanningProfile;
  commitments: CalendarCommitment[];
}

export interface WeeklyAnalysisResponse {
  capacity: CapacityResponse;
  analysis: WeeklyAnalysis;
}
