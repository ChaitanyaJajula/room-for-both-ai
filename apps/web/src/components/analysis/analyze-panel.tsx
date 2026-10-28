"use client";

import { useEffect, useRef, useState } from "react";

import { PlanPanel } from "@/components/plan/plan-panel";
import { analyzeWeek, getDemoCalendar } from "@/lib/api";
import { clearApprovedPlan } from "@/lib/approved-plan";
import type { CalendarCommitment, WeeklyAnalysisResponse } from "@/types/analysis";
import type { PlanningProfile } from "@/types/planning-profile";

import { AnalysisResults } from "./analysis-results";

const LOADING_MESSAGE = "Python is calculating capacity and Nemotron is reviewing your week…";

type State =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | {
      phase: "done";
      runId: number;
      result: WeeklyAnalysisResponse;
      commitments: CalendarCommitment[];
    };

const primaryButton =
  "rounded-full bg-teal-700 px-6 py-3 text-base font-semibold text-white shadow-soft hover:bg-teal-800 disabled:cursor-wait disabled:opacity-70";
const secondaryButton =
  "rounded-full border border-line bg-white px-5 py-2.5 text-sm font-semibold hover:bg-teal-700/5";

export function AnalyzePanel({
  profile,
  onEditPreferences,
}: {
  profile: PlanningProfile;
  onEditPreferences: () => void;
}) {
  const [state, setState] = useState<State>({ phase: "idle" });
  const inFlight = useRef(false);
  const runCount = useRef(0);
  const resultRef = useRef<HTMLDivElement>(null);
  const loading = state.phase === "loading";

  // Move the reader to the outcome of a request once it settles.
  useEffect(() => {
    if (state.phase === "done" || state.phase === "error") {
      resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [state.phase]);

  const run = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    // A fresh analysis proposes new outcomes, so an earlier approved plan no longer applies.
    clearApprovedPlan();
    setState({ phase: "loading" });
    try {
      const calendar = await getDemoCalendar();
      if (!calendar.ok) {
        setState({ phase: "error", message: calendar.message });
        return;
      }
      const commitments = calendar.data.commitments;
      const analysis = await analyzeWeek(profile, commitments);
      setState(
        analysis.ok
          ? { phase: "done", runId: ++runCount.current, result: analysis.data, commitments }
          : { phase: "error", message: analysis.message },
      );
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <section aria-labelledby="analyze-title" className="space-y-6">
      <div className="rounded-2xl border border-line bg-surface p-5 shadow-soft sm:p-6">
        <h2 id="analyze-title" className="font-serif text-2xl font-semibold">
          See how your week holds up
        </h2>
        <p className="mt-1 text-sm text-muted">
          We use a prepared demo calendar, so no account or private calendar is needed.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          {state.phase === "done" ? (
            <>
              <button type="button" onClick={run} className={primaryButton}>
                Analyze again
              </button>
              <button type="button" onClick={onEditPreferences} className={secondaryButton}>
                Edit preferences
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={run}
                disabled={loading}
                aria-busy={loading}
                className={`w-full sm:w-auto ${primaryButton}`}
              >
                {loading ? "Analyzing…" : "Analyze my week"}
              </button>
              {loading ? null : (
                <button type="button" onClick={onEditPreferences} className={secondaryButton}>
                  Edit preferences
                </button>
              )}
            </>
          )}
        </div>
      </div>

      <div ref={resultRef} className="scroll-mt-6 space-y-6">
        <div role="status" aria-live="polite">
          {loading ? (
            <p className="rounded-2xl border border-teal-700/40 bg-teal-700/10 p-4 text-sm font-medium text-teal-800">
              {LOADING_MESSAGE}
            </p>
          ) : null}
        </div>
        {state.phase === "error" ? (
          <div role="alert" className="rounded-2xl border border-terracotta/50 bg-terracotta/10 p-5">
            <h2 className="font-serif text-lg font-semibold text-terracotta-dark">
              We could not analyze your week
            </h2>
            <p className="mt-1 text-sm">{state.message}</p>
            <button type="button" onClick={run} className={`mt-3 ${secondaryButton}`}>
              Retry
            </button>
          </div>
        ) : null}
        {state.phase === "done" ? (
          <>
            <AnalysisResults result={state.result} commitments={state.commitments} />
            <PlanPanel
              key={state.runId}
              profile={profile}
              commitments={state.commitments}
              workOutcome={state.result.analysis.work_outcome}
              personalOutcome={state.result.analysis.personal_outcome}
            />
          </>
        ) : null}
      </div>
    </section>
  );
}
