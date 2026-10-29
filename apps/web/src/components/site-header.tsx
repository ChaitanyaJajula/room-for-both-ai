import Link from "next/link";

export function SiteHeader({ step, current }: { step?: string; current?: "evaluation" }) {
  return (
    <header className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-x-4 gap-y-2 px-5 py-5 sm:px-8">
      <Link
        href="/"
        className="flex items-center gap-2.5 font-serif text-lg font-semibold tracking-tight"
      >
        <span
          aria-hidden="true"
          className="grid h-8 w-8 place-items-center rounded-full bg-teal-700 text-sm text-white"
        >
          R
        </span>
        Room for Both
      </Link>
      <nav aria-label="Primary" className="flex items-center gap-2">
        <Link
          href="/evaluation"
          aria-current={current === "evaluation" ? "page" : undefined}
          className={`inline-flex min-h-10 items-center rounded-full px-3.5 text-sm font-medium hover:bg-teal-700/5 ${
            current === "evaluation" ? "border border-teal-700 text-teal-800" : "text-muted"
          }`}
        >
          Reliability
        </Link>
        {step ? (
          <p className="rounded-full border border-line bg-surface px-3 py-1 text-sm text-muted">
            {step}
          </p>
        ) : null}
      </nav>
    </header>
  );
}
