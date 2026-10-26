"use client";

import { useRef, useState, type ChangeEvent, type FormEvent } from "react";

import {
  DAY_LABELS,
  DEFAULT_VALUES,
  LIMITS,
  toPlanningProfile,
  validateSetup,
  type SetupErrors,
  type SetupFormValues,
} from "@/lib/setup";
import { validatePlanningProfile } from "@/lib/api";
import { DAYS_OF_WEEK, type DayOfWeek, type PlanningProfile } from "@/types/planning-profile";

import { Field, Section, SelectInput, TextInput } from "./fields";
import { ReviewCard } from "./review-card";

const COMMON_TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Kolkata",
  "Asia/Tokyo",
  "Australia/Sydney",
];

type NumericKey =
  | "maxDailyFocusMinutes"
  | "minimumBreakMinutes"
  | "protectedPersonalMinutesPerWeek";

type SubmitStatus =
  | { state: "idle" }
  | { state: "submitting" }
  | { state: "success" }
  | { state: "error"; title: string; messages: string[] };

export function SetupForm() {
  const [values, setValues] = useState<SetupFormValues>(DEFAULT_VALUES);
  const [errors, setErrors] = useState<SetupErrors>({});
  const [profile, setProfile] = useState<PlanningProfile | null>(null);
  const [status, setStatus] = useState<SubmitStatus>({ state: "idle" });
  const inFlight = useRef(false);
  const statusRef = useRef<HTMLDivElement>(null);
  const submitting = status.state === "submitting";

  const set = <K extends keyof SetupFormValues>(key: K, value: SetupFormValues[K]) =>
    setValues((prev) => ({ ...prev, [key]: value }));

  const text = (key: keyof SetupFormValues) => (e: ChangeEvent<HTMLInputElement>) =>
    set(key, e.target.value as never);

  const num = (key: NumericKey) => (e: ChangeEvent<HTMLInputElement>) =>
    set(key, e.target.valueAsNumber);

  const numValue = (n: number) => (Number.isNaN(n) ? "" : n);

  const toggleDay = (day: DayOfWeek) =>
    set(
      "workDays",
      values.workDays.includes(day)
        ? values.workDays.filter((d) => d !== day)
        : [...values.workDays, day],
    );

  const useMyTimezone = () => set("timezone", Intl.DateTimeFormat().resolvedOptions().timeZone);

  const showStatus = (next: SubmitStatus) => {
    setStatus(next);
    requestAnimationFrame(() =>
      statusRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
    );
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (inFlight.current) return;

    const found = validateSetup(values);
    setErrors(found);
    if (Object.keys(found).length > 0) {
      setProfile(null);
      setStatus({ state: "idle" });
      return;
    }

    inFlight.current = true;
    setProfile(null);
    setStatus({ state: "submitting" });
    try {
      const result = await validatePlanningProfile(toPlanningProfile(values));
      if (result.ok) {
        // Keep the backend's normalized profile, not the locally built one.
        setProfile(result.profile);
        showStatus({ state: "success" });
      } else if (result.kind === "validation") {
        showStatus(
          {
            state: "error",
            title: "The service found something to fix",
            messages: result.messages,
          },
        );
      } else {
        showStatus(
          {
            state: "error",
            title:
              result.kind === "network" ? "Could not reach the service" : "Something went wrong",
            messages: [result.message],
          },
        );
      }
    } finally {
      inFlight.current = false;
    }
  };

  return (
    <div className="space-y-6">
      <form onSubmit={onSubmit} noValidate className="space-y-6">
        <Section title="Your clock" description="So every time we show is in your local week.">
          <Field label="Timezone" htmlFor="timezone" error={errors.timezone}>
            <TextInput
              id="timezone"
              list="timezones"
              value={values.timezone}
              onChange={text("timezone")}
              placeholder="e.g. Europe/London"
              autoComplete="off"
              aria-invalid={Boolean(errors.timezone)}
            />
            <datalist id="timezones">
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz} value={tz} />
              ))}
            </datalist>
          </Field>
          <div className="flex items-end">
            <button
              type="button"
              onClick={useMyTimezone}
              className="rounded-xl border border-line px-3.5 py-2.5 text-sm font-medium hover:bg-teal-700/5"
            >
              Use my timezone
            </button>
          </div>
        </Section>

        <Section title="Working time" description="Pick your working days, then your usual hours.">
          <div className="sm:col-span-2">
            <p id="days-label" className="mb-2 text-sm font-medium">
              Working days
            </p>
            <div role="group" aria-labelledby="days-label" className="flex flex-wrap gap-2">
              {DAYS_OF_WEEK.map((day) => {
                const on = values.workDays.includes(day);
                return (
                  <label
                    key={day}
                    className={`cursor-pointer rounded-full border px-3.5 py-1.5 text-sm font-medium has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-teal-700 ${
                      on
                        ? "border-teal-700 bg-teal-700 text-white"
                        : "border-line bg-white text-ink hover:bg-teal-700/5"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={on}
                      onChange={() => toggleDay(day)}
                    />
                    {DAY_LABELS[day].slice(0, 3)}
                  </label>
                );
              })}
            </div>
            {errors.workDays ? (
              <p role="alert" className="mt-1.5 text-xs font-medium text-terracotta-dark">
                {errors.workDays}
              </p>
            ) : null}
          </div>
          <Field label="Work starts" htmlFor="workStart">
            <TextInput id="workStart" type="time" value={values.workStart} onChange={text("workStart")} />
          </Field>
          <Field label="Work ends" htmlFor="workEnd" error={errors.workEnd}>
            <TextInput id="workEnd" type="time" value={values.workEnd} onChange={text("workEnd")} aria-invalid={Boolean(errors.workEnd)} />
          </Field>
        </Section>

        <Section title="Focus and rest" description="When you think best, and how much is enough.">
          <Field label="Preferred focus starts" htmlFor="focusStart">
            <TextInput id="focusStart" type="time" value={values.focusStart} onChange={text("focusStart")} />
          </Field>
          <Field label="Preferred focus ends" htmlFor="focusEnd" error={errors.focusEnd}>
            <TextInput id="focusEnd" type="time" value={values.focusEnd} onChange={text("focusEnd")} aria-invalid={Boolean(errors.focusEnd)} />
          </Field>
          <Field
            label="Max focus per day (minutes)"
            htmlFor="maxFocus"
            hint={`${LIMITS.maxDailyFocus.min}–${LIMITS.maxDailyFocus.max}`}
            error={errors.maxDailyFocusMinutes}
          >
            <TextInput
              id="maxFocus"
              type="number"
              inputMode="numeric"
              min={LIMITS.maxDailyFocus.min}
              max={LIMITS.maxDailyFocus.max}
              value={numValue(values.maxDailyFocusMinutes)}
              onChange={num("maxDailyFocusMinutes")}
              aria-invalid={Boolean(errors.maxDailyFocusMinutes)}
            />
          </Field>
          <Field
            label="Minimum break (minutes)"
            htmlFor="minBreak"
            hint={`${LIMITS.minBreak.min}–${LIMITS.minBreak.max}`}
            error={errors.minimumBreakMinutes}
          >
            <TextInput
              id="minBreak"
              type="number"
              inputMode="numeric"
              min={LIMITS.minBreak.min}
              max={LIMITS.minBreak.max}
              value={numValue(values.minimumBreakMinutes)}
              onChange={num("minimumBreakMinutes")}
              aria-invalid={Boolean(errors.minimumBreakMinutes)}
            />
          </Field>
          <Field
            label="Protected personal time per week (minutes)"
            htmlFor="personal"
            hint={`${LIMITS.protectedPersonal.min}–${LIMITS.protectedPersonal.max}`}
            error={errors.protectedPersonalMinutesPerWeek}
          >
            <TextInput
              id="personal"
              type="number"
              inputMode="numeric"
              min={LIMITS.protectedPersonal.min}
              max={LIMITS.protectedPersonal.max}
              value={numValue(values.protectedPersonalMinutesPerWeek)}
              onChange={num("protectedPersonalMinutesPerWeek")}
              aria-invalid={Boolean(errors.protectedPersonalMinutesPerWeek)}
            />
          </Field>
        </Section>

        <Section title="A first boundary" description="Something your plan should never quietly take over.">
          <Field label="Name" htmlFor="bName" error={errors.boundaryName}>
            <TextInput id="bName" value={values.boundaryName} onChange={text("boundaryName")} aria-invalid={Boolean(errors.boundaryName)} />
          </Field>
          <Field label="Day" htmlFor="bDay">
            <SelectInput
              id="bDay"
              value={values.boundaryDay}
              onChange={(e) => set("boundaryDay", e.target.value as DayOfWeek)}
            >
              {DAYS_OF_WEEK.map((d) => (
                <option key={d} value={d}>
                  {DAY_LABELS[d]}
                </option>
              ))}
            </SelectInput>
          </Field>
          <Field label="Starts" htmlFor="bStart">
            <TextInput id="bStart" type="time" value={values.boundaryStart} onChange={text("boundaryStart")} />
          </Field>
          <Field label="Ends" htmlFor="bEnd" error={errors.boundaryEnd}>
            <TextInput id="bEnd" type="time" value={values.boundaryEnd} onChange={text("boundaryEnd")} aria-invalid={Boolean(errors.boundaryEnd)} />
          </Field>
          <Field
            label="How firm is it?"
            htmlFor="bFirm"
            hint="Hard boundaries are never scheduled over; soft ones can flex if needed."
          >
            <SelectInput
              id="bFirm"
              value={values.boundaryIsHard ? "hard" : "soft"}
              onChange={(e) => set("boundaryIsHard", e.target.value === "hard")}
            >
              <option value="hard">Hard</option>
              <option value="soft">Soft</option>
            </SelectInput>
          </Field>
        </Section>

        <button
          type="submit"
          disabled={submitting}
          aria-busy={submitting}
          className="w-full rounded-full bg-teal-700 px-6 py-3 text-base font-semibold text-white shadow-soft hover:bg-teal-800 disabled:cursor-wait disabled:opacity-70 sm:w-auto"
        >
          {submitting ? "Checking your setup…" : "Review setup"}
        </button>
      </form>

      <div ref={statusRef} aria-live="polite" className="scroll-mt-6">
        {status.state === "error" ? (
          <div
            role="alert"
            className="rounded-2xl border border-terracotta/50 bg-terracotta/10 p-5"
          >
            <h2 className="font-serif text-lg font-semibold text-terracotta-dark">
              {status.title}
            </h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {status.messages.map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {status.state === "success" ? (
          <p className="rounded-2xl border border-teal-700/40 bg-teal-700/10 p-4 text-sm font-medium text-teal-800">
            Your setup is valid. The service accepted it.
          </p>
        ) : null}
      </div>

      <div>
        {profile ? <ReviewCard profile={profile} /> : null}
      </div>
    </div>
  );
}
