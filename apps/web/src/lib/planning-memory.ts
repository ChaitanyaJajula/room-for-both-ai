// Browser-local planning memory. One versioned localStorage record, written only when the user
// explicitly asks. Every access is guarded: storage can be missing (server render, private mode),
// full, or hold bad data, and bad data is ignored and removed rather than trusted.
import { useEffect, useMemo, useSyncExternalStore } from "react";

import type { PlanningMemory } from "@/types/memory";

export const MEMORY_KEY = "room-for-both:planning-memory:v1";
// localStorage's own "storage" event only fires in other tabs, so changes made in this tab
// announce themselves with this event.
export const MEMORY_EVENT = "room-for-both:planning-memory-changed";

export const MEMORY_LIMITS = { min: 0, max: 10080 } as const;

const FIELDS = [
  "id",
  "version",
  "label",
  "protectedPersonalMinutesPerWeek",
  "explanation",
  "createdAt",
  "updatedAt",
];

const isIso = (v: unknown): v is string =>
  typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v) && !Number.isNaN(Date.parse(v));

const isMinutes = (v: unknown): v is number =>
  typeof v === "number" &&
  Number.isInteger(v) &&
  v >= MEMORY_LIMITS.min &&
  v <= MEMORY_LIMITS.max;

export function isPlanningMemory(v: unknown): v is PlanningMemory {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return false;
  const r = v as Record<string, unknown>;
  const keys = Object.keys(r);
  return (
    keys.length === FIELDS.length &&
    FIELDS.every((k) => keys.includes(k)) &&
    r.id === "protected-personal-time" &&
    r.version === 1 &&
    r.label === "Protect personal time" &&
    isMinutes(r.protectedPersonalMinutesPerWeek) &&
    typeof r.explanation === "string" &&
    r.explanation.trim().length > 0 &&
    isIso(r.createdAt) &&
    isIso(r.updatedAt)
  );
}

function readRaw(): string | null {
  try {
    return window.localStorage.getItem(MEMORY_KEY);
  } catch {
    return null;
  }
}

function parseMemory(raw: string | null): PlanningMemory | null {
  if (raw === null) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    return isPlanningMemory(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function announce(): void {
  window.dispatchEvent(new Event(MEMORY_EVENT));
}

function removeRaw(): boolean {
  try {
    window.localStorage.removeItem(MEMORY_KEY);
    return true;
  } catch {
    return false;
  }
}

/** The saved preference, or null. Invalid, unsupported or out-of-range data is removed. */
export function loadPlanningMemory(): PlanningMemory | null {
  const raw = readRaw();
  const memory = parseMemory(raw);
  if (raw !== null && memory === null && removeRaw()) announce();
  return memory;
}

/** Create the record, or update the existing one in place (createdAt is kept). */
export function savePlanningMemory(minutes: number): PlanningMemory | null {
  if (!isMinutes(minutes)) return null;
  const now = new Date().toISOString();
  const existing = loadPlanningMemory();
  const record: PlanningMemory = {
    id: "protected-personal-time",
    version: 1,
    label: "Protect personal time",
    protectedPersonalMinutesPerWeek: minutes,
    explanation: `Protect at least ${minutes} minutes of personal time each week.`,
    createdAt: existing?.createdAt ?? now,
    updatedAt: now,
  };
  try {
    window.localStorage.setItem(MEMORY_KEY, JSON.stringify(record));
  } catch {
    return null;
  }
  announce();
  return record;
}

export function deletePlanningMemory(): boolean {
  const removed = removeRaw();
  if (removed) announce();
  return removed;
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener("storage", onChange);
  window.addEventListener(MEMORY_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(MEMORY_EVENT, onChange);
  };
}

/** The saved preference, kept current across components, tabs and refreshes. Null on the server. */
export function usePlanningMemory(): PlanningMemory | null {
  const raw = useSyncExternalStore(subscribe, readRaw, () => null);
  const memory = useMemo(() => parseMemory(raw), [raw]);
  useEffect(() => {
    if (raw !== null && memory === null && removeRaw()) announce();
  }, [raw, memory]);
  return memory;
}
