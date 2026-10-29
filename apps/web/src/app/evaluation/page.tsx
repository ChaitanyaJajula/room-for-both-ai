import type { Metadata } from "next";

import { EvaluationDashboard } from "@/components/evaluation/evaluation-dashboard";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "Reliability evaluation",
  description:
    "A fixed, deterministic suite that verifies the Python and OR-Tools safeguards around model output.",
};

export default function EvaluationPage() {
  return (
    <>
      <SiteHeader current="evaluation" />
      <main id="main" className="mx-auto w-full max-w-3xl flex-1 px-5 pb-16 sm:px-8">
        <h1 className="py-6 font-serif text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          Reliability evaluation
        </h1>
        <div className="mb-8 space-y-3 text-base leading-relaxed">
          <p>
            Room for Both uses an LLM for structured reasoning, then relies on Python and Google
            OR-Tools to verify capacity, schedules, conflicts and repair options.
          </p>
          <p className="text-sm text-muted">
            This fixed evaluation suite makes no model calls and does not measure Nemotron’s general
            intelligence. It verifies the deterministic safeguards around model output.
          </p>
        </div>
        <EvaluationDashboard />
      </main>
    </>
  );
}
