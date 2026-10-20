import type { Metadata } from "next";

import { SetupForm } from "@/components/setup/setup-form";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "Setup",
  description: "Tell Room for Both what your week needs to respect.",
};

export default function SetupPage() {
  return (
    <>
      <SiteHeader step="Step 1 of 4" />
      <main id="main" className="mx-auto w-full max-w-3xl flex-1 px-5 pb-16 sm:px-8">
        <h1 className="py-6 font-serif text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
          Tell us what your week needs to respect
        </h1>
        <SetupForm />
      </main>
    </>
  );
}
