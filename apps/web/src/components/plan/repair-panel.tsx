"use client";

import { useRef, useState } from "react";

import { requestRepairOptions } from "@/lib/api";
import { formatDuration } from "@/lib/format";
import { MEETING_TITLE, selectDemoMeeting } from "@/lib/meeting";
import { DAY_LABELS, formatTime } from "@/lib/setup";
import type { CalendarCommitment, Outcome } from "@/types/analysis";
import type { PlanResponse } from "@/types/plan";
import type { PlanningProfile } from "@/types/planning-profile";
import type {
  ConflictRecord,
  RepairOption,
  RepairResponse,
  RepairStrategy,
} from "@/types/repair";

const LOADING_MESSAGE =
  "Python is checking the conflict, OR-Tools is validating repairs, and Nemotron is ranking the safe options…";
const NO_SAFE_MEETING =
  "We could not find a safe time for a demo meeting inside your approved work blocks, so nothing was changed.";
const FALLBACK_TEXT = "Nemotron was temporarily unavailable. Showing a verified rule-based ranking.";

type State =
  | { phase: "idle"; notice: string | null }
  | { phase: "loading" }
  | { phase: "error"; message: string }
  | { phase: "done"; meeting: CalendarCommitment; result: RepairResponse };

const primaryButton =
  "min-h-11 rounded-full bg-teal-700 px-6 py-3 text-base font-semibold text-white shadow-soft hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-70";
const secondaryButton =
  "min-h-10 rounded-full border border-line bg-white px-5 py-2.5 text-sm font-semibold hover:bg-teal-700/5";

// Strategy is named in text and marked with a distinct glyph, never by color alone.
const STRATEGY: Record<RepairStrategy, { label: string; mark: string }> = {
  move: { label: "Move", mark: "⇄" },
  simplify: { label: "Simplify", mark: "✂" },
  delegate: { label: "Delegate", mark: "➜" },
  drop: { label: "Drop", mark: "✕" },
};

const CONFLICT_LABEL = {
  scheduled_block: "Planned block",
  existing_commitment: "Existing commitment",
  hard_boundary: "Hard boundary",
} as const;

export function strategyLabel(strategy: RepairStrategy): string {
  return STRATEGY[strategy].label;
}

function meetingTime(meeting: CalendarCommitment): string {
  return `${DAY_LABELS[meeting.day]}, ${formatTime(meeting.start_time)} – ${formatTime(meeting.end_time)}`;
}

function ConflictRow({ record }: { record: ConflictRecord }) {
  const kind =
    record.conflict_type === "scheduled_block" && record.outcome_type
      ? `${record.outcome_type === "work" ? "Work" : "Personal"} block`
      : CONFLICT_LABEL[record.conflict_type];
  return (
    <li className="rounded-xl border border-line bg-surface p-3 text-sm">
      <p className="font-medium">{kind}</p>
      <p className="mt-0.5 [overflow-wrap:anywhere]">{record.conflicting_item_title}</p>
      <p className="mt-0.5 text-xs text-muted">
        {formatTime(record.conflicting_start_time)} – {formatTime(record.conflicting_end_time)} ·
        overlap {formatDuration(record.overlap_minutes)}
      </p>
    </li>
  );
}

function ConflictView({ meeting, result }: { meeting: CalendarCommitment; result: RepairResponse }) {
  const { conflict } = result;
  return (
    <div className="space-y-3 rounded-2xl border border-terracotta/50 bg-terracotta/5 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-serif text-lg font-semibold text-terracotta-dark">
          {conflict.conflict_detected ? "Conflict detected by Python" : "No conflict found"}
        </h3>
      </div>
      <p className="text-sm">
        <span className="font-semibold [overflow-wrap:anywhere]">{meeting.title}</span> ·{" "}
        {meetingTime(meeting)}
      </p>
      <p className="text-sm [overflow-wrap:anywhere]">{conflict.summary}</p>
      {conflict.conflicts.length > 0 ? (
        <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {conflict.conflicts.map((record, i) => (
            <ConflictRow key={`${record.conflicting_item_id}-${i}`} record={record} />
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium text-muted">{label}</dt>
      <dd className="text-sm font-medium">{value}</dd>
    </div>
  );
}

function OptionCard({
  option,
  selected,
  disabled,
  onSelect,
}: {
  option: RepairOption;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  const style = STRATEGY[option.strategy];
  const plan = option.revised_plan;
  return (
    <li>
      <label
        className={`flex cursor-pointer gap-3 rounded-2xl border p-4 shadow-soft has-[:focus-visible]:outline has-[:focus-visible]:outline-[3px] has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-teal-700 ${
          selected ? "border-2 border-teal-700 bg-teal-700/5" : "border-line bg-surface"
        } ${disabled ? "cursor-not-allowed opacity-80" : ""}`}
      >
        <input
          type="radio"
          name="repair-option"
          value={option.id}
          checked={selected}
          disabled={disabled}
          onChange={onSelect}
          className="mt-1 h-5 w-5 shrink-0 accent-teal-700"
        />
        <span className="min-w-0 flex-1 space-y-3">
          <span className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-line bg-white px-2.5 py-0.5 text-xs font-semibold">
              Rank {option.rank}
            </span>
            <span className="rounded-full border border-line bg-white px-2.5 py-0.5 text-xs font-semibold">
              <span aria-hidden="true">{style.mark} </span>
              {style.label}
            </span>
            {option.recommended ? (
              <span className="rounded-full bg-teal-700 px-2.5 py-0.5 text-xs font-semibold text-white">
                <span aria-hidden="true">★ </span>Recommended
              </span>
            ) : null}
            {selected ? (
              <span className="text-xs font-semibold text-teal-800">
                <span aria-hidden="true">✓ </span>Selected
              </span>
            ) : null}
          </span>
          <span className="block font-serif text-lg font-semibold [overflow-wrap:anywhere]">
            {option.title}
          </span>
          <span className="block text-sm [overflow-wrap:anywhere]">{option.explanation}</span>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
            <Fact label="Revised plan" value={plan.status === "partial" ? "Partial" : "Complete"} />
            <Fact label="Work target" value={formatDuration(option.target_work_minutes)} />
            <Fact label="Personal target" value={formatDuration(option.target_personal_minutes)} />
            {option.reduced_work_minutes > 0 ? (
              <Fact label="Work reduced" value={formatDuration(option.reduced_work_minutes)} />
            ) : null}
            {option.reduced_personal_minutes > 0 ? (
              <Fact
                label="Personal reduced"
                value={formatDuration(option.reduced_personal_minutes)}
              />
            ) : null}
            {option.delegated_work_minutes > 0 ? (
              <Fact label="Work delegated" value={formatDuration(option.delegated_work_minutes)} />
            ) : null}
            {option.dropped_work_minutes > 0 ? (
              <Fact label="Work dropped" value={formatDuration(option.dropped_work_minutes)} />
            ) : null}
            {option.dropped_personal_minutes > 0 ? (
              <Fact
                label="Personal dropped"
                value={formatDuration(option.dropped_personal_minutes)}
              />
            ) : null}
            <Fact
              label="Work not scheduled"
              value={formatDuration(plan.unscheduled_work_minutes)}
            />
            <Fact
              label="Personal not scheduled"
              value={formatDuration(plan.unscheduled_personal_minutes)}
            />
          </dl>
          <span className="inline-block rounded-full border border-teal-700/40 bg-teal-700/10 px-2.5 py-0.5 text-xs font-semibold text-teal-800">
            <span aria-hidden="true">✓ </span>Python + OR-Tools verified
          </span>
        </span>
      </label>
    </li>
  );
}

function Attribution({ result }: { result: RepairResponse }) {
  return (
    <p className="rounded-2xl border border-teal-700/30 bg-teal-700/5 p-4 text-sm">
      {result.reasoning_source === "nemotron" ? (
        <>
          Repair options ranked by NVIDIA Nemotron on Nebius Token Factory
          <span className="text-muted"> · {result.model_name}</span>
        </>
      ) : (
        FALLBACK_TEXT
      )}
    </p>
  );
}

function StatusMessage({ result }: { result: RepairResponse }) {
  const box = "rounded-2xl border border-line bg-surface p-4 text-sm";
  if (result.status === "not_needed") {
    return (
      <p className={box}>
        This meeting did not disrupt your approved plan, so no repair is needed.
      </p>
    );
  }
  if (result.status === "manual_resolution_required") {
    return (
      <div className={box}>
        <p className="font-semibold">Two fixed obligations conflict</p>
        <p className="mt-1">
          Your new meeting overlaps something that cannot be moved automatically. You will need to
          change or decline one of those fixed obligations. No schedule repair is offered for this.
        </p>
      </div>
    );
  }
  if (result.status === "no_valid_options") {
    return (
      <div className={box}>
        <p className="font-semibold">No valid repair found</p>
        <p className="mt-1">
          Your current constraints leave no valid repair for this meeting. Try editing your
          availability or boundaries, then analyze your week again.
        </p>
      </div>
    );
  }
  return null;
}

export function RepairPanel({
  plan,
  profile,
  commitments,
  workOutcome,
  personalOutcome,
  appliedStrategy,
  onApproveRevised,
}: {
  plan: PlanResponse;
  profile: PlanningProfile;
  commitments: CalendarCommitment[];
  workOutcome: Outcome;
  personalOutcome: Outcome;
  /** Set once a revised plan has replaced the approved one; locks every repair control. */
  appliedStrategy: RepairStrategy | null;
  onApproveRevised: (plan: PlanResponse, strategy: RepairStrategy) => void;
}) {
  const [state, setState] = useState<State>({ phase: "idle", notice: null });
  const [selected, setSelected] = useState<RepairStrategy | null>(null);
  const inFlight = useRef(false);
  const loading = state.phase === "loading";
  const locked = appliedStrategy !== null;

  const run = async () => {
    if (inFlight.current || locked) return;
    const meeting = selectDemoMeeting(plan, commitments, profile);
    if (meeting === null) {
      setState({ phase: "idle", notice: NO_SAFE_MEETING });
      return;
    }
    inFlight.current = true;
    setSelected(null);
    setState({ phase: "loading" });
    try {
      const result = await requestRepairOptions({
        profile,
        commitments,
        approved_plan: plan,
        unexpected_commitment: meeting,
        work_outcome: workOutcome,
        personal_outcome: personalOutcome,
      });
      setState(
        result.ok
          ? { phase: "done", meeting, result: result.data }
          : { phase: "error", message: result.message },
      );
    } finally {
      inFlight.current = false;
    }
  };

  const approve = () => {
    if (locked || state.phase !== "done" || selected === null) return;
    const option = state.result.options.find((o) => o.id === selected);
    if (option) onApproveRevised(option.revised_plan, option.strategy);
  };

  const result = state.phase === "done" ? state.result : null;
  const options = result ? [...result.options].sort((a, b) => a.rank - b.rank) : [];

  return (
    <section aria-labelledby="repair-title" className="space-y-4 border-t border-line pt-8">
      <h2 id="repair-title" className="font-serif text-2xl font-semibold">
        Something changed?
      </h2>
      <p className="text-sm text-muted">
        Add a realistic interruption to see how your personal AI repairs the week.
      </p>

      {state.phase === "idle" || state.phase === "loading" ? (
        <button
          type="button"
          onClick={run}
          disabled={loading || locked}
          aria-busy={loading}
          className={`w-full sm:w-auto ${primaryButton}`}
        >
          {loading ? "Checking…" : "Add unexpected meeting"}
        </button>
      ) : null}

      <div role="status" aria-live="polite" className="space-y-3">
        {loading ? (
          <p className="rounded-2xl border border-teal-700/40 bg-teal-700/10 p-4 text-sm font-medium text-teal-800">
            {LOADING_MESSAGE}
          </p>
        ) : null}
        {state.phase === "idle" && state.notice ? (
          <p className="rounded-2xl border border-line bg-surface p-4 text-sm">{state.notice}</p>
        ) : null}
        {result?.status === "options_ready" ? (
          <p className="text-sm font-medium">
            {options.length} verified repair {options.length === 1 ? "option is" : "options are"}{" "}
            ready. Choose one, then approve it.
          </p>
        ) : null}
      </div>

      {state.phase === "error" ? (
        <div role="alert" className="rounded-2xl border border-terracotta/50 bg-terracotta/10 p-5">
          <h3 className="font-serif text-lg font-semibold text-terracotta-dark">
            We could not check the interruption
          </h3>
          <p className="mt-1 text-sm">{state.message}</p>
          <button type="button" onClick={run} className={`mt-3 ${secondaryButton}`}>
            Retry
          </button>
        </div>
      ) : null}

      {state.phase === "done" ? (
        <div className="space-y-4">
          <ConflictView meeting={state.meeting} result={state.result} />
          <StatusMessage result={state.result} />

          {state.result.status === "options_ready" ? (
            <>
              <Attribution result={state.result} />
              <fieldset className="space-y-3" disabled={locked}>
                <legend className="font-serif text-lg font-semibold">Verified repair options</legend>
                <ul className="space-y-3">
                  {options.map((option) => (
                    <OptionCard
                      key={option.id}
                      option={option}
                      selected={(appliedStrategy ?? selected) === option.id}
                      disabled={locked}
                      onSelect={() => setSelected(option.id)}
                    />
                  ))}
                </ul>
              </fieldset>
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={approve}
                  disabled={locked || selected === null}
                  className={primaryButton}
                >
                  {locked ? "Revised plan approved" : "Approve revised plan"}
                </button>
                {locked || selected !== null ? null : (
                  <span className="text-sm text-muted">Choose an option to approve it.</span>
                )}
              </div>
              {locked ? (
                <p className="text-sm text-muted">
                  {strategyLabel(appliedStrategy)} was applied to “{MEETING_TITLE}”. This
                  interruption cannot be applied again.
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
