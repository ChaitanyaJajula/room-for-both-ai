"use client";

import { useRef, useState } from "react";

import { runEvaluation } from "@/lib/api";
import type { EvaluationCategory, EvaluationReport } from "@/types/evaluation";

type State =
  | { phase: "idle" }
  | { phase: "running" }
  | { phase: "error"; message: string }
  | { phase: "done"; report: EvaluationReport };

const primaryButton =
  "min-h-11 rounded-full bg-teal-700 px-6 py-3 text-base font-semibold text-white shadow-soft hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-70";
const secondaryButton =
  "min-h-10 rounded-full border border-line bg-white px-5 py-2.5 text-sm font-semibold hover:bg-teal-700/5";

const CATEGORY_LABEL: Record<EvaluationCategory, string> = {
  capacity: "Capacity",
  scheduling: "Scheduling",
  conflict_detection: "Conflict detection",
  repair_validation: "Repair validation",
};

const ARCHITECTURE = [
  { who: "NVIDIA Nemotron", what: "Structured reasoning and ranking of options Python has verified." },
  { who: "Python", what: "Capacity calculation, conflict detection and validation." },
  { who: "Google OR-Tools CP-SAT", what: "Constraint-based scheduling of work and personal time." },
  {
    who: "Safety boundary",
    what: "Deterministic checks reject or fall back from invalid model output.",
  },
];

function formatRuntime(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

const formatRate = (percent: number) => `${Number(percent.toFixed(1))}%`;

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4 shadow-soft">
      <dt className="text-sm font-medium text-muted">{label}</dt>
      <dd className="mt-1 font-serif text-2xl font-semibold">{value}</dd>
    </div>
  );
}

function Results({ report }: { report: EvaluationReport }) {
  const { summary } = report;
  const passed = report.status === "passed";
  return (
    <div className="space-y-6">
      <div
        className={`rounded-2xl border p-5 ${
          passed ? "border-teal-700/40 bg-teal-700/10" : "border-terracotta/50 bg-terracotta/10"
        }`}
      >
        <h3
          className={`font-serif text-xl font-semibold ${
            passed ? "text-teal-800" : "text-terracotta-dark"
          }`}
        >
          <span aria-hidden="true">{passed ? "✓ " : "⚠ "}</span>
          {passed ? "All deterministic safeguards passed" : "Some safeguards need attention"}
        </h3>
        <p className="mt-1 text-sm text-muted">
          {report.suite_name} · {new Date(report.generated_at).toLocaleString()}
        </p>
      </div>

      <dl className="grid grid-cols-1 gap-3 min-[480px]:grid-cols-2 lg:grid-cols-3">
        <SummaryCard label="Passed cases" value={`${summary.passed_cases} / ${summary.total_cases}`} />
        <SummaryCard
          label="Verified checks"
          value={`${summary.passed_checks} / ${summary.total_checks}`}
        />
        <SummaryCard label="Pass rate" value={formatRate(summary.pass_rate_percent)} />
        <SummaryCard label="Model calls" value={String(report.model_calls_made)} />
        <SummaryCard label="Runtime" value={formatRuntime(summary.total_duration_ms)} />
      </dl>

      <section aria-labelledby="cases-title" className="space-y-3">
        <h3 id="cases-title" className="font-serif text-xl font-semibold">
          Cases
        </h3>
        <ul className="space-y-3">
          {report.cases.map((c) => (
            <li key={c.id} className="rounded-2xl border border-line bg-surface p-4 shadow-soft">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-line bg-white px-2.5 py-0.5 text-xs font-semibold">
                  {CATEGORY_LABEL[c.category]}
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                    c.passed
                      ? "bg-teal-700 text-white"
                      : "border border-terracotta-dark bg-terracotta/15 text-terracotta-dark"
                  }`}
                >
                  <span aria-hidden="true">{c.passed ? "✓ " : "✗ "}</span>
                  {c.passed ? "Pass" : "Fail"}
                </span>
              </div>
              <h4 className="mt-2 font-semibold [overflow-wrap:anywhere]">{c.name}</h4>
              <p className="mt-1 text-sm [overflow-wrap:anywhere]">{c.summary}</p>
              <p className="mt-2 text-xs text-muted">
                {c.checks_passed} / {c.checks_total} checks · {formatRuntime(c.duration_ms)}
              </p>
            </li>
          ))}
        </ul>
      </section>

      {report.architecture_guarantees.length > 0 ? (
        <section aria-labelledby="guarantees-title" className="space-y-2">
          <h3 id="guarantees-title" className="font-serif text-xl font-semibold">
            Guarantees of this run
          </h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {report.architecture_guarantees.map((g) => (
              <li key={g}>{g}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function EvaluationDashboard() {
  const [state, setState] = useState<State>({ phase: "idle" });
  const inFlight = useRef(false);
  const running = state.phase === "running";

  const run = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setState({ phase: "running" });
    try {
      const result = await runEvaluation();
      setState(
        result.ok ? { phase: "done", report: result.data } : { phase: "error", message: result.message },
      );
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <div className="space-y-8">
      <div className="space-y-4">
        <button
          type="button"
          onClick={run}
          disabled={running}
          aria-busy={running}
          className={`w-full sm:w-auto ${primaryButton}`}
        >
          {running ? "Running evaluation…" : "Run verified evaluation"}
        </button>

        <div role="status" aria-live="polite">
          {running ? (
            <p className="rounded-2xl border border-teal-700/40 bg-teal-700/10 p-4 text-sm font-medium text-teal-800">
              Running evaluation…
            </p>
          ) : null}
          {state.phase === "done" ? (
            <p className="text-sm font-medium">
              Evaluation finished: {state.report.summary.passed_cases} of{" "}
              {state.report.summary.total_cases} cases passed.
            </p>
          ) : null}
        </div>

        {state.phase === "error" ? (
          <div role="alert" className="rounded-2xl border border-terracotta/50 bg-terracotta/10 p-5">
            <h3 className="font-serif text-lg font-semibold text-terracotta-dark">
              We could not run the evaluation
            </h3>
            <p className="mt-1 text-sm">{state.message}</p>
            <button type="button" onClick={run} className={`mt-3 ${secondaryButton}`}>
              Retry
            </button>
          </div>
        ) : null}
      </div>

      {state.phase === "done" ? <Results report={state.report} /> : null}

      <section aria-labelledby="architecture-title" className="space-y-3">
        <h2 id="architecture-title" className="font-serif text-2xl font-semibold">
          Who does what
        </h2>
        <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {ARCHITECTURE.map((item) => (
            <div key={item.who} className="rounded-2xl border border-line bg-surface p-4">
              <dt className="font-semibold">{item.who}</dt>
              <dd className="mt-1 text-sm text-muted">{item.what}</dd>
            </div>
          ))}
        </dl>
      </section>
    </div>
  );
}
