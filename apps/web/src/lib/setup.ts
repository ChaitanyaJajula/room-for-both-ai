import {
  DAYS_OF_WEEK,
  type DayOfWeek,
  type PlanningProfile,
  type RecurringTimeWindow,
} from "@/types/planning-profile";

export const DAY_LABELS: Record<DayOfWeek, string> = {
  monday: "Monday",
  tuesday: "Tuesday",
  wednesday: "Wednesday",
  thursday: "Thursday",
  friday: "Friday",
  saturday: "Saturday",
  sunday: "Sunday",
};

export const LIMITS = {
  maxDailyFocus: { min: 30, max: 480 },
  minBreak: { min: 5, max: 120 },
  protectedPersonal: { min: 0, max: 10080 },
} as const;

/** Raw form state: everything the inputs hold, before conversion to a profile. */
export interface SetupFormValues {
  timezone: string;
  workDays: DayOfWeek[];
  workStart: string;
  workEnd: string;
  focusStart: string;
  focusEnd: string;
  maxDailyFocusMinutes: number;
  minimumBreakMinutes: number;
  protectedPersonalMinutesPerWeek: number;
  boundaryName: string;
  boundaryDay: DayOfWeek;
  boundaryStart: string;
  boundaryEnd: string;
  boundaryIsHard: boolean;
}

export const DEFAULT_VALUES: SetupFormValues = {
  timezone: "UTC",
  workDays: ["monday", "tuesday", "wednesday", "thursday", "friday"],
  workStart: "09:00",
  workEnd: "17:00",
  focusStart: "09:00",
  focusEnd: "11:30",
  maxDailyFocusMinutes: 240,
  minimumBreakMinutes: 15,
  protectedPersonalMinutesPerWeek: 180,
  boundaryName: "Family dinner",
  boundaryDay: "monday",
  boundaryStart: "18:00",
  boundaryEnd: "19:30",
  boundaryIsHard: true,
};

export type SetupErrors = Partial<Record<keyof SetupFormValues, string>>;

function isKnownTimezone(tz: string): boolean {
  try {
    new Intl.DateTimeFormat("en", { timeZone: tz });
    return true;
  } catch {
    return false;
  }
}

export function validateSetup(v: SetupFormValues): SetupErrors {
  const errors: SetupErrors = {};
  if (!v.timezone.trim()) {
    errors.timezone = "Enter a timezone, e.g. Europe/London.";
  } else if (!isKnownTimezone(v.timezone.trim())) {
    errors.timezone = "That does not look like a valid IANA timezone.";
  }
  if (v.workDays.length === 0) errors.workDays = "Choose at least one working day.";
  if (!v.workStart || !v.workEnd || v.workEnd <= v.workStart) {
    errors.workEnd = "Work should end after it starts.";
  }
  if (!v.focusStart || !v.focusEnd || v.focusEnd <= v.focusStart) {
    errors.focusEnd = "Focus time should end after it starts.";
  }
  const range = (
    key: keyof SetupFormValues,
    value: number,
    { min, max }: { min: number; max: number },
  ) => {
    if (!Number.isInteger(value) || value < min || value > max) {
      errors[key] = `Enter a whole number from ${min} to ${max}.`;
    }
  };
  range("maxDailyFocusMinutes", v.maxDailyFocusMinutes, LIMITS.maxDailyFocus);
  range("minimumBreakMinutes", v.minimumBreakMinutes, LIMITS.minBreak);
  range(
    "protectedPersonalMinutesPerWeek",
    v.protectedPersonalMinutesPerWeek,
    LIMITS.protectedPersonal,
  );
  if (!v.boundaryName.trim()) errors.boundaryName = "Give this boundary a name.";
  if (!v.boundaryStart || !v.boundaryEnd || v.boundaryEnd <= v.boundaryStart) {
    errors.boundaryEnd = "The boundary should end after it starts.";
  }
  return errors;
}

const withSeconds = (t: string) => (t.length === 5 ? `${t}:00` : t);

function windowsFor(days: DayOfWeek[], start: string, end: string): RecurringTimeWindow[] {
  return DAYS_OF_WEEK.filter((d) => days.includes(d)).map((day) => ({
    day,
    start_time: withSeconds(start),
    end_time: withSeconds(end),
  }));
}

export function toPlanningProfile(v: SetupFormValues): PlanningProfile {
  return {
    timezone: v.timezone.trim(),
    work_hours: windowsFor(v.workDays, v.workStart, v.workEnd),
    preferred_focus_windows: windowsFor(v.workDays, v.focusStart, v.focusEnd),
    boundaries: [
      {
        name: v.boundaryName.trim(),
        windows: windowsFor([v.boundaryDay], v.boundaryStart, v.boundaryEnd),
        is_hard: v.boundaryIsHard,
      },
    ],
    max_daily_focus_minutes: v.maxDailyFocusMinutes,
    minimum_break_minutes: v.minimumBreakMinutes,
    protected_personal_minutes_per_week: v.protectedPersonalMinutesPerWeek,
  };
}

export function formatTime(t: string): string {
  const [h, m] = t.split(":").map(Number);
  const suffix = h >= 12 ? "pm" : "am";
  const hour = h % 12 === 0 ? 12 : h % 12;
  return `${hour}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function formatMinutes(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m} min`;
  return m === 0 ? `${h} h` : `${h} h ${m} min`;
}
