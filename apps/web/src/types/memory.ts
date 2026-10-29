// The one reusable planning preference Room for Both can remember, kept only in this browser.
export interface PlanningMemory {
  id: "protected-personal-time";
  version: 1;
  label: "Protect personal time";
  /** A whole number from 0 to 10080 (minutes in a week). */
  protectedPersonalMinutesPerWeek: number;
  explanation: string;
  /** ISO timestamps. */
  createdAt: string;
  updatedAt: string;
}
