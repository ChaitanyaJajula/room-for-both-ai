"use client";

import { useRef, useState } from "react";

import { clearApprovedPlan, saveApprovedPlan } from "@/lib/approved-plan";
import { generatePlan } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { DAY_LABELS, formatTime } from "@/lib/setup";
import type { CalendarCommitment, Outcome } from "@/types/analysis";
import type { PlanResponse, ScheduledBlock } from "@/types/plan";
import { DAYS_OF_WEEK, type PlanningProfile } from "@/types/planning-profile";
import type { RepairStrategy } from "@/types/repair";

import { MemorySuggestion } from "@/components/memory/memory-suggestion";

import { RepairPanel, strategyLabel } from "./repair-panel";

const LOADING_MESSAGE = "OR-Tools is finding valid time slots for your week…";

type State =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | {
      phase: "ready";
      plan: PlanResponse;
      approvedAt: string | null;
      saved: boolean;
      // The repair strategy behind a revised plan; null while this is the original plan.
      revision: RepairStrategy | null;
    };

const primaryButton =
  "rounded-full bg-teal-700 px-6 py-3 text-base font-semibold text-white shadow-soft hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-70";
const secondaryButton =
  "rounded-full border border-line bg-white px-5 py-2.5 text-sm font-semibold hover:bg-teal-700/5";

// Work and personal differ by a text label, a marker shape and border style, not color alone.
const KIND_STYLE = {
  work: { label: "Work", mark: "◆", box: "border-l-teal-700 bg-surface" },
  personal: {
    label: "Personal",
    mark: "●",
    box: "border-l-terracotta-dark border-dashed bg-terracotta/5",
  },
} as const;

function BlockItem({ block }: { block: ScheduledBlock }) {
  const style = KIND_STYLE[block.outcome_type];
  return (
    <li className={`rounded-xl border border-line border-l-4 p-3 text-sm ${style.box}`}>
      <p className="flex flex-wrap items-center gap-x-2 font-medium">
        <span>
          <span aria-hidden="true">{style.mark} </span>
          {style.label}
        </span>
        <span className="text-muted">
          {formatTime(block.start_time)} – {formatTime(block.end_time)}
        </span>
      </p>
      <p className="mt-1 [overflow-wrap:anywhere]">{block.outcome_title}</p>
      <p className="mt-0.5 text-xs text-muted">
        {formatDuration(block.duration_minutes)}
        {block.inside_preferred_focus_window ? " · in a preferred focus window" : ""}
        {block.uses_soft_boundary ? " · touches a soft boundary" : ""}
      </p>
    </li>
  );
}

function Totals({
  label,
  requested,
  scheduled,
  unscheduled,
}: {
  label: string;
  requested: number;
  scheduled: number;
  unscheduled: number;
}) {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4">
      <dt className="text-sm font-medium text-muted">{label}</dt>
      <dd className="mt-1 text-sm">
        <span className="font-serif text-xl font-semibold">{formatDuration(scheduled)}</span>{" "}
        scheduled of {formatDuration(requested)} requested
        {unscheduled > 0 ? (
          <span className="mt-1 block font-medium text-terracotta-dark">
            {formatDuration(unscheduled)} not scheduled
          </span>
        ) : null}
      </dd>
    </div>
  );
}

function PlanView({ plan }: { plan: PlanResponse }) {
  const days = DAYS_OF_WEEK.map((day) => ({
    day,
    blocks: plan.blocks
      .filter((b) => b.day === day)
      .sort((a, b) => a.start_time.localeCompare(b.start_time)),
  })).filter((d) => d.blocks.length > 0);

  if (plan.status === "infeasible") {
    return (
      <div className="rounded-2xl border border-terracotta/50 bg-terracotta/10 p-5">
        <h3 className="font-serif text-lg font-semibold text-terracotta-dark">
          No valid plan fits right now
        </h3>
        <p className="mt-1 text-sm">
          Your current commitments, boundaries and available hours leave no valid time for these
          outcomes. Try adjusting your boundaries or work hours, then analyze your week again.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {plan.status === "partial" ? (
        <p className="rounded-2xl border border-[#8a6416]/40 bg-[#f4e6c4] p-4 text-sm font-medium text-[#6b4a0f]">
          Only part of your week fits. The blocks below are valid, and the time marked “not
          scheduled” did not fit within your constraints.
        </p>
      ) : null}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {days.map(({ day, blocks }) => (
          <div key={day} className="rounded-2xl border border-line bg-surface p-4 shadow-soft">
            <h3 className="font-serif text-lg font-semibold">{DAY_LABELS[day]}</h3>
            <ul className="mt-2 space-y-2">
              {blocks.map((b) => (
                <BlockItem key={b.id} block={b} />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

export function PlanPanel({
  profile,
  commitments,
  workOutcome,
  personalOutcome,
}: {
  profile: PlanningProfile;
  commitments: CalendarCommitment[];
  workOutcome: Outcome;
  personalOutcome: Outcome;
}) {
  const [state, setState] = useState<State>({ phase: "idle" });
  const inFlight = useRef(false);
  const loading = state.phase === "loading";

  const build = async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    // A new plan replaces, and invalidates, any plan approved earlier.
    clearApprovedPlan();
    setState({ phase: "loading" });
    try {
      const result = await generatePlan({
        profile,
        commitments,
        work_outcome: workOutcome,
        personal_outcome: personalOutcome,
      });
      setState(
        result.ok
          ? { phase: "ready", plan: result.data, approvedAt: null, saved: true, revision: null }
          : { phase: "error", message: result.message },
      );
    } finally {
      inFlight.current = false;
    }
  };

  const approve = () => {
    if (state.phase !== "ready" || state.approvedAt) return;
    const approvedAt = new Date().toISOString();
    const saved = saveApprovedPlan(state.plan, approvedAt);
    setState({ ...state, approvedAt, saved });
  };

  // A verified repair replaces the approved plan. It is saved under the same versioned key
  // with a fresh approval time, so the earlier plan can no longer be restored.
  const applyRevision = (revised: PlanResponse, strategy: RepairStrategy) => {
    if (state.phase !== "ready" || !state.approvedAt || state.revision) return;
    const approvedAt = new Date().toISOString();
    const saved = saveApprovedPlan(revised, approvedAt);
    setState({ phase: "ready", plan: revised, approvedAt, saved, revision: strategy });
  };

  const ready = state.phase === "ready" ? state : null;
  const canApprove = ready !== null && ready.plan.status !== "infeasible";

  return (
    <section aria-labelledby="plan-title" className="space-y-4 border-t border-line pt-8">
      <h2 id="plan-title" className="font-serif text-2xl font-semibold">
        Your weekly plan
      </h2>
      <p className="text-sm text-muted">
        Nemotron proposed the outcomes above. Google OR-Tools then finds valid time slots that
        avoid your commitments and boundaries.
      </p>

      {ready === null ? (
        <button
          type="button"
          onClick={build}
          disabled={loading}
          aria-busy={loading}
          className={`w-full sm:w-auto ${primaryButton}`}
        >
          {loading ? "Building…" : "Build my weekly plan"}
        </button>
      ) : null}

      <div role="status" aria-live="polite">
        {loading ? (
          <p className="rounded-2xl border border-teal-700/40 bg-teal-700/10 p-4 text-sm font-medium text-teal-800">
            {LOADING_MESSAGE}
          </p>
        ) : null}
        {ready?.approvedAt ? (
          <p className="rounded-2xl border border-teal-700/40 bg-teal-700/10 p-4 text-sm font-semibold text-teal-800">
            ✓ {ready.revision ? "Revised plan approved" : "Plan approved"} ·{" "}
            {new Date(ready.approvedAt).toLocaleString()}
            {ready.revision ? (
              <span className="mt-1 block font-normal">
                Applied: {strategyLabel(ready.revision)}
              </span>
            ) : null}
            {ready.saved ? null : (
              <span className="mt-1 block font-normal">
                This browser could not save the approval, so it lasts only while this page is open.
              </span>
            )}
          </p>
        ) : null}
      </div>

      {ready?.approvedAt ? (
        // Keyed by the approval, so approving a revised plan offers a fresh suggestion.
        <MemorySuggestion
          key={ready.approvedAt}
          personalMinutes={ready.plan.scheduled_personal_minutes}
        />
      ) : null}

      {state.phase === "error" ? (
        <div role="alert" className="rounded-2xl border border-terracotta/50 bg-terracotta/10 p-5">
          <h3 className="font-serif text-lg font-semibold text-terracotta-dark">
            We could not build your plan
          </h3>
          <p className="mt-1 text-sm">{state.message}</p>
          <button type="button" onClick={build} className={`mt-3 ${secondaryButton}`}>
            Retry
          </button>
        </div>
      ) : null}

      {ready ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full border border-line bg-surface px-3 py-1 text-sm font-semibold">
              {ready.revision ? "Revised plan" : ready.approvedAt ? "Approved plan" : "Draft plan"}
            </span>
            <span className="text-sm text-muted">
              {ready.plan.status === "partial"
                ? "Partial schedule"
                : ready.plan.status === "infeasible"
                  ? "No valid schedule"
                  : "Complete schedule"}
            </span>
          </div>

          <PlanView plan={ready.plan} />

          <dl className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <Totals
              label="Work"
              requested={ready.plan.requested_work_minutes}
              scheduled={ready.plan.scheduled_work_minutes}
              unscheduled={ready.plan.unscheduled_work_minutes}
            />
            <Totals
              label="Personal"
              requested={ready.plan.requested_personal_minutes}
              scheduled={ready.plan.scheduled_personal_minutes}
              unscheduled={ready.plan.unscheduled_personal_minutes}
            />
          </dl>

          {ready.plan.warnings.length > 0 ? (
            <div className="rounded-2xl border border-line bg-surface p-4">
              <h3 className="text-sm font-semibold">Notes</h3>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
                {ready.plan.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </div>
          ) : null}

          <div className="flex flex-wrap gap-3">
            {canApprove && !ready.revision ? (
              <button
                type="button"
                onClick={approve}
                disabled={ready.approvedAt !== null}
                className={primaryButton}
              >
                {ready.approvedAt ? "Plan approved" : "Approve this plan"}
              </button>
            ) : null}
            <button type="button" onClick={build} className={secondaryButton}>
              Rebuild plan
            </button>
          </div>

          <p className="rounded-2xl border border-teal-700/30 bg-teal-700/5 p-4 text-sm">
            Schedule optimized with Google OR-Tools CP-SAT
            <span className="text-muted">
              {" "}
              · solver {ready.plan.solver.status.toLowerCase()} in{" "}
              {ready.plan.solver.wall_time_seconds}s
            </span>
          </p>

          {ready.approvedAt && ready.plan.status !== "infeasible" ? (
            <RepairPanel
              plan={ready.plan}
              profile={profile}
              commitments={commitments}
              workOutcome={workOutcome}
              personalOutcome={personalOutcome}
              appliedStrategy={ready.revision}
              onApproveRevised={applyRevision}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
