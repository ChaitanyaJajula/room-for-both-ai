"use client";

import { useState } from "react";

import { MEMORY_LIMITS, savePlanningMemory } from "@/lib/planning-memory";

type State = "asking" | "saved" | "failed" | "dismissed";

const primaryButton =
  "min-h-10 rounded-full bg-teal-700 px-5 py-2.5 text-sm font-semibold text-white shadow-soft hover:bg-teal-800";
const secondaryButton =
  "min-h-10 rounded-full border border-line bg-white px-5 py-2.5 text-sm font-semibold hover:bg-teal-700/5";

/**
 * Offers to remember the approved plan's personal time. Nothing is saved until the user clicks
 * "Remember this preference". The number is the approved plan's scheduled personal minutes.
 */
export function MemorySuggestion({ personalMinutes }: { personalMinutes: number }) {
  const [state, setState] = useState<State>("asking");

  const valid =
    Number.isInteger(personalMinutes) &&
    personalMinutes > 0 &&
    personalMinutes <= MEMORY_LIMITS.max;
  if (!valid || state === "dismissed") return null;

  const remember = () => setState(savePlanningMemory(personalMinutes) ? "saved" : "failed");

  return (
    <section
      aria-labelledby="memory-suggestion-title"
      className="space-y-3 rounded-2xl border border-teal-700/30 bg-teal-700/5 p-4"
    >
      <h3 id="memory-suggestion-title" className="font-serif text-lg font-semibold">
        Memory suggestion
      </h3>
      <p className="text-sm">
        Protect at least {personalMinutes} minutes of personal time each week.
      </p>
      <p className="text-xs text-muted">
        Stored only in this browser. You can view or delete it anytime.
      </p>

      {state === "asking" || state === "failed" ? (
        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={remember} className={primaryButton}>
            Remember this preference
          </button>
          <button type="button" onClick={() => setState("dismissed")} className={secondaryButton}>
            Not now
          </button>
        </div>
      ) : null}

      <div role="status" aria-live="polite">
        {state === "saved" ? (
          <p className="text-sm font-semibold text-teal-800">
            <span aria-hidden="true">✓ </span>Preference remembered on this device.
          </p>
        ) : null}
        {state === "failed" ? (
          <p className="text-sm font-medium text-terracotta-dark">
            This browser could not save the preference, so nothing was remembered.
          </p>
        ) : null}
      </div>
    </section>
  );
}
