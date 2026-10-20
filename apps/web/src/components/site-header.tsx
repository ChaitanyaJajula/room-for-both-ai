import Link from "next/link";

export function SiteHeader({ step }: { step?: string }) {
  return (
    <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-5 py-5 sm:px-8">
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
      {step ? (
        <p className="rounded-full border border-line bg-surface px-3 py-1 text-sm text-muted">
          {step}
        </p>
      ) : null}
    </header>
  );
}
