import type { ReactNode } from "react";

import { DAY_LABELS, formatMinutes, formatTime } from "@/lib/setup";
import type { PlanningProfile, RecurringTimeWindow } from "@/types/planning-profile";

function WindowList({ windows }: { windows: RecurringTimeWindow[] }) {
  return (
    <ul className="space-y-0.5 text-sm">
      {windows.map((w) => (
        <li key={`${w.day}-${w.start_time}`}>
          <span className="font-medium">{DAY_LABELS[w.day]}</span>{" "}
          <span className="text-muted">
            {formatTime(w.start_time)} – {formatTime(w.end_time)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="border-t border-line py-3 first:border-t-0 sm:grid sm:grid-cols-[12rem_1fr] sm:gap-4">
      <dt className="text-sm font-medium text-muted">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export function ReviewCard({ profile }: { profile: PlanningProfile }) {
  return (
    <section
      aria-labelledby="review-title"
      className="rounded-2xl border border-teal-700/30 bg-surface p-5 shadow-soft sm:p-6"
    >
      <h2 id="review-title" className="font-serif text-2xl font-semibold">
        Here is what your week will respect
      </h2>
      <p className="mt-1 text-sm text-muted">
        Checked by the Room for Both service. Not saved yet.
      </p>
      <dl className="mt-4">
        <Row label="Timezone">{profile.timezone}</Row>
        <Row label="Work hours">
          <WindowList windows={profile.work_hours} />
        </Row>
        <Row label="Preferred focus">
          <WindowList windows={profile.preferred_focus_windows} />
        </Row>
        <Row label="Daily limits">
          Up to {formatMinutes(profile.max_daily_focus_minutes)} of focus, with breaks of at
          least {formatMinutes(profile.minimum_break_minutes)}
        </Row>
        <Row label="Protected personal time">
          {formatMinutes(profile.protected_personal_minutes_per_week)} each week
        </Row>
        {profile.boundaries.map((b) => (
          <Row key={b.name} label="Boundary">
            <p className="mb-1 font-medium">
              {b.name}{" "}
              <span
                className={`ml-1 rounded-full px-2 py-0.5 text-xs ${
                  b.is_hard
                    ? "bg-terracotta/15 text-terracotta-dark"
                    : "bg-teal-700/10 text-teal-800"
                }`}
              >
                {b.is_hard ? "Hard" : "Soft"}
              </span>
            </p>
            <WindowList windows={b.windows} />
          </Row>
        ))}
      </dl>
    </section>
  );
}
