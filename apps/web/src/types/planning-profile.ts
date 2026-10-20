// Mirrors services/api/app/models/planning_profile.py.
// Times are "HH:MM:SS" strings, as the backend serialises datetime.time.

export const DAYS_OF_WEEK = [
  "monday",
  "tuesday",
  "wednesday",
  "thursday",
  "friday",
  "saturday",
  "sunday",
] as const;

export type DayOfWeek = (typeof DAYS_OF_WEEK)[number];

export interface RecurringTimeWindow {
  day: DayOfWeek;
  start_time: string;
  end_time: string;
}

export interface Boundary {
  name: string;
  windows: RecurringTimeWindow[];
  is_hard: boolean;
}

export interface PlanningProfile {
  timezone: string;
  work_hours: RecurringTimeWindow[];
  preferred_focus_windows: RecurringTimeWindow[];
  boundaries: Boundary[];
  max_daily_focus_minutes: number;
  minimum_break_minutes: number;
  protected_personal_minutes_per_week: number;
}
