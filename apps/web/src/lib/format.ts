// Display formatting only. All capacity numbers come from the backend.

/** 60 → "1 hr", 90 → "1 hr 30 min", 120 → "2 hrs", 45 → "45 min". */
export function formatDuration(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) return `${minutes} min`;
  const hourText = `${hours} ${hours === 1 ? "hr" : "hrs"}`;
  return minutes === 0 ? hourText : `${hourText} ${minutes} min`;
}
