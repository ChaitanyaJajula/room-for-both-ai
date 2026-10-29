// Picks the demo "unexpected meeting" deterministically. The choice depends only on the
// approved plan, the fixed commitments and the hard boundaries, never on a day or clock time.
import type { CalendarCommitment } from "@/types/analysis";
import type { PlanResponse } from "@/types/plan";
import { DAYS_OF_WEEK, type PlanningProfile } from "@/types/planning-profile";

export const MEETING_TITLE = "Urgent customer meeting";
const BASE_ID = "unexpected-urgent-customer-meeting";
const GRID = 15;
// Longest first: a realistic interruption is preferred, a shorter one is the fallback.
const DURATIONS = [45, 30, 15];

type Interval = [start: number, end: number];

function toMinutes(time: string): number {
  const [h, m] = time.split(":").map(Number);
  return h * 60 + m;
}

function toTime(minutes: number): string {
  const h = String(Math.floor(minutes / 60)).padStart(2, "0");
  const m = String(minutes % 60).padStart(2, "0");
  return `${h}:${m}:00`;
}

const overlaps = (a: Interval, b: Interval) => a[0] < b[1] && b[0] < a[1];

function uniqueId(commitments: CalendarCommitment[]): string {
  const taken = new Set(commitments.map((c) => c.id));
  if (!taken.has(BASE_ID)) return BASE_ID;
  let n = 2;
  while (taken.has(`${BASE_ID}-${n}`)) n += 1;
  return `${BASE_ID}-${n}`;
}

/** The first safe window inside an approved work block, or null when none exists. */
export function selectDemoMeeting(
  plan: PlanResponse,
  commitments: CalendarCommitment[],
  profile: PlanningProfile,
): CalendarCommitment | null {
  const workBlocks = plan.blocks
    .filter((b) => b.outcome_type === "work")
    .sort(
      (a, b) =>
        DAYS_OF_WEEK.indexOf(a.day) - DAYS_OF_WEEK.indexOf(b.day) ||
        toMinutes(a.start_time) - toMinutes(b.start_time),
    );

  const fixed = commitments.filter((c) => c.is_fixed);
  const hardWindows = profile.boundaries.filter((b) => b.is_hard).flatMap((b) => b.windows);

  const isSafe = (day: string, window: Interval) =>
    !fixed.some(
      (c) => c.day === day && overlaps([toMinutes(c.start_time), toMinutes(c.end_time)], window),
    ) &&
    !hardWindows.some(
      (w) => w.day === day && overlaps([toMinutes(w.start_time), toMinutes(w.end_time)], window),
    );

  for (const duration of DURATIONS) {
    for (const block of workBlocks) {
      const blockEnd = toMinutes(block.end_time);
      const firstSlot = Math.ceil(toMinutes(block.start_time) / GRID) * GRID;
      for (let start = firstSlot; start + duration <= blockEnd; start += GRID) {
        if (!isSafe(block.day, [start, start + duration])) continue;
        return {
          id: uniqueId(commitments),
          title: MEETING_TITLE,
          day: block.day,
          start_time: toTime(start),
          end_time: toTime(start + duration),
          category: "work",
          is_fixed: true,
          description: null,
        };
      }
    }
  }
  return null;
}
