import Link from "next/link";

import { Principles } from "@/components/home/principles";
import { SiteHeader } from "@/components/site-header";

export default function Home() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="mx-auto w-full max-w-5xl flex-1 px-5 pb-16 sm:px-8">
        <section className="py-12 sm:py-20">
          <h1 className="max-w-3xl font-serif text-4xl font-semibold leading-tight tracking-tight sm:text-6xl">
            Plan a week that makes room for work and life.
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-muted">
            Room for Both measures the real capacity you have, protects your personal
            commitments, and repairs the plan when life changes.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Link
              href="/setup"
              className="rounded-full bg-teal-700 px-7 py-3.5 text-base font-semibold text-white shadow-soft transition-colors hover:bg-teal-800"
            >
              Start your setup
            </Link>
            <span className="rounded-full border border-line bg-surface px-3 py-1 text-xs text-muted">
              Powered by NVIDIA Nemotron on Nebius
            </span>
          </div>
        </section>
        <section aria-labelledby="principles-title">
          <h2 id="principles-title" className="sr-only">
            How it works
          </h2>
          <Principles />
        </section>
      </main>
    </>
  );
}
