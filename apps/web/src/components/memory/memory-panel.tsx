"use client";

import { useState } from "react";

import { deletePlanningMemory, usePlanningMemory } from "@/lib/planning-memory";

const formatWhen = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });

const secondaryButton =
  "min-h-10 rounded-full border border-line bg-white px-5 py-2.5 text-sm font-semibold hover:bg-teal-700/5";

export function MemoryPanel() {
  const memory = usePlanningMemory();
  const [message, setMessage] = useState<string | null>(null);

  const remove = () => {
    setMessage(
      deletePlanningMemory()
        ? "Planning memory deleted."
        : "This browser could not delete the saved preference. Please try again.",
    );
  };

  return (
    <section
      aria-labelledby="memory-title"
      className="rounded-2xl border border-line bg-surface p-5 shadow-soft sm:p-6"
    >
      <h2 id="memory-title" className="font-serif text-xl font-semibold">
        Your planning memory
      </h2>
      <p className="mt-1 text-sm text-muted">
        Stored only in this browser. There is no account, no cloud copy and no sync between
        devices. You choose what to remember, and you can delete it anytime.
      </p>

      {memory ? (
        <div className="mt-4 space-y-3">
          <div className="rounded-xl border border-line bg-white p-4">
            <h3 className="font-semibold">{memory.label}</h3>
            <p className="mt-1 text-sm">
              At least {memory.protectedPersonalMinutesPerWeek} minutes per week
            </p>
            <p className="mt-1 text-xs text-muted">
              Stored only in this browser · Saved {formatWhen(memory.createdAt)}
              {memory.updatedAt !== memory.createdAt
                ? ` · Updated ${formatWhen(memory.updatedAt)}`
                : ""}
            </p>
          </div>
          <button type="button" onClick={remove} className={secondaryButton}>
            Delete memory
          </button>
        </div>
      ) : (
        <p className="mt-4 text-sm">No saved planning preferences.</p>
      )}

      <div role="status" aria-live="polite">
        {message && memory === null ? (
          <p className="mt-3 text-sm font-medium text-teal-800">{message}</p>
        ) : null}
      </div>
    </section>
  );
}
