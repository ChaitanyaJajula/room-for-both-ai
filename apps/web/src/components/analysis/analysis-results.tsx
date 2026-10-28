import type { ReactNode } from "react";

import { formatDuration } from "@/lib/format";
import { DAY_LABELS, formatTime } from "@/lib/setup";
import type {
  CalendarCommitment,
  Classification,
  Outcome,
  WeeklyAnalysisResponse,
} from "@/types/analysis";
import { DAYS_OF_WEEK } from "@/types/planning-profile";

const FALLBACK_NOTICE =
  "Nemotron was temporarily unavailable. Showing a verified rule-based analysis.";

const STATUS_STYLES: Record<Classification, { label: string; badge: string; mark: string }> = {
  balanced: {
    label: "Balanced",
    badge: "border-teal-800/40 bg-teal-700/10 text-teal-800",
    mark: "●",
  },
  tight: {
    label: "Tight",
    badge: "border-[#8a6416]/40 bg-[#f4e6c4] text-[#6b4a0f]",
    mark: "◐",
  },
  overloaded: {
    label: "Overloaded",
    badge: "border-terracotta-dark/40 bg-terracotta/15 text-terracotta-dark",
    mark: "▲",
  },
};

function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-line bg-surface p-5 shadow-soft ${className}`}>
      {children}
    </div>
  );
}

function WeekStatus({ analysis }: { analysis: WeeklyAnalysisResponse["analysis"] }) {
  const style = STATUS_STYLES[analysis.classification];
  return (
    <section aria-labelledby="week-status-title" className="space-y-3">
      <div role="status" className="flex flex-wrap items-center gap-3">
        <h2 id="week-status-title" className="font-serif text-2xl font-semibold">
          Your week
        </h2>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm font-semibold ${style.badge}`}
        >
          <span aria-hidden="true">{style.mark}</span>
          {style.label}
        </span>
      </div>
      <p className="text-lg leading-relaxed">{analysis.summary}</p>
      <p className="text-sm leading-relaxed text-muted">{analysis.capacity_explanation}</p>
    </section>
  );
}

function CapacityCards({ weekly }: { weekly: WeeklyAnalysisResponse["capacity"]["weekly"] }) {
  const items: { label: string; minutes: number }[] = [
    { label: "Work window", minutes: weekly.work_window_minutes },
    { label: "Already committed", minutes: weekly.occupied_minutes },
    { label: "Free inside work hours", minutes: weekly.free_minutes },
    { label: "Focus capacity", minutes: weekly.schedulable_focus_minutes },
    { label: "Protected personal target", minutes: weekly.protected_personal_target_minutes },
  ];
  return (
    <section aria-labelledby="capacity-title" className="space-y-3">
      <h2 id="capacity-title" className="font-serif text-2xl font-semibold">
        Verified capacity
      </h2>
      <p className="inline-block rounded-full border border-teal-800/40 bg-teal-700/10 px-3 py-1 text-sm font-medium text-teal-800">
        Capacity calculated deterministically in Python
      </p>
      <dl className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <Card key={item.label}>
            <dt className="text-sm font-medium text-muted">{item.label}</dt>
            <dd className="mt-1 font-serif text-2xl font-semibold">
              {formatDuration(item.minutes)}
            </dd>
          </Card>
        ))}
      </dl>
    </section>
  );
}

function OutcomeCard({ heading, outcome }: { heading: string; outcome: Outcome }) {
  return (
    <Card>
      <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">{heading}</h3>
      <p className="mt-2 font-serif text-xl font-semibold">{outcome.title}</p>
      <p className="mt-2 text-sm leading-relaxed">{outcome.reason}</p>
      <p className="mt-3 text-sm font-medium text-teal-800">
        {formatDuration(outcome.estimated_minutes)}
      </p>
    </Card>
  );
}

function RiskList({ risks }: { risks: string[] }) {
  return (
    <section aria-labelledby="risks-title" className="space-y-3">
      <h2 id="risks-title" className="font-serif text-2xl font-semibold">
        Risks to keep in mind
      </h2>
      {risks.length === 0 ? (
        <p className="rounded-2xl border border-line bg-surface p-4 text-sm">
          No major capacity risks detected.
        </p>
      ) : (
        <ul className="space-y-2">
          {risks.map((risk, i) => (
            <li
              key={i}
              className="rounded-2xl border border-line bg-surface p-4 text-sm leading-relaxed"
            >
              {risk}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DemoCalendar({ commitments }: { commitments: CalendarCommitment[] }) {
  const days = DAYS_OF_WEEK.map((day) => ({
    day,
    items: commitments
      .filter((c) => c.day === day)
      .sort((a, b) => a.start_time.localeCompare(b.start_time)),
  })).filter((d) => d.items.length > 0);

  return (
    <section aria-labelledby="calendar-title" className="space-y-3">
      <h2 id="calendar-title" className="font-serif text-2xl font-semibold">
        Prepared demo calendar
      </h2>
      <p className="text-sm text-muted">
        This public demo uses prepared commitments and does not require access to your private
        calendar.
      </p>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {days.map(({ day, items }) => (
          <Card key={day}>
            <h3 className="font-serif text-lg font-semibold">{DAY_LABELS[day]}</h3>
            <ul className="mt-2 divide-y divide-line">
              {items.map((c) => (
                <li key={c.id} className="py-2 text-sm">
                  <p className="font-medium [overflow-wrap:anywhere]">{c.title}</p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-muted">
                    <span>
                      {formatTime(c.start_time)} – {formatTime(c.end_time)}
                    </span>
                    <span className="rounded-full border border-line px-2 py-0.5 text-xs capitalize">
                      {c.category}
                    </span>
                  </p>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>
    </section>
  );
}

function AnalysisAttribution({ analysis }: { analysis: WeeklyAnalysisResponse["analysis"] }) {
  const isNemotron = analysis.source === "nemotron";
  return (
    <section
      aria-labelledby="attribution-title"
      className="rounded-2xl border border-teal-700/30 bg-teal-700/5 p-5"
    >
      <h2 id="attribution-title" className="font-serif text-lg font-semibold">
        {isNemotron
          ? "Reasoning powered by NVIDIA Nemotron on Nebius Token Factory"
          : "Verified rule-based analysis"}
      </h2>
      <p className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">{isNemotron ? "Model:" : "Configured model:"}</span>
        <span className="font-medium [overflow-wrap:anywhere]">{analysis.model_name}</span>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
            isNemotron
              ? "border-teal-800/40 bg-teal-700/10 text-teal-800"
              : "border-[#8a6416]/40 bg-[#f4e6c4] text-[#6b4a0f]"
          }`}
        >
          {isNemotron ? "Nemotron analysis" : "Rule-based analysis"}
        </span>
      </p>
      {isNemotron ? null : <p className="mt-2 text-sm">{FALLBACK_NOTICE}</p>}
    </section>
  );
}

export function AnalysisResults({
  result,
  commitments,
}: {
  result: WeeklyAnalysisResponse;
  commitments: CalendarCommitment[];
}) {
  const { analysis, capacity } = result;
  return (
    <div className="space-y-8">
      <WeekStatus analysis={analysis} />
      <CapacityCards weekly={capacity.weekly} />
      <section aria-labelledby="outcomes-title" className="space-y-3">
        <h2 id="outcomes-title" className="font-serif text-2xl font-semibold">
          Recommended outcomes
        </h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <OutcomeCard heading="Work outcome" outcome={analysis.work_outcome} />
          <OutcomeCard heading="Personal outcome" outcome={analysis.personal_outcome} />
        </div>
      </section>
      <RiskList risks={analysis.risks} />
      <DemoCalendar commitments={commitments} />
      <AnalysisAttribution analysis={analysis} />
    </div>
  );
}
