const PRINCIPLES = [
  { name: "See", text: "Measure the capacity you really have this week." },
  { name: "Choose", text: "Decide what matters before the calendar fills itself." },
  { name: "Make Room", text: "Protect personal time as firmly as deadlines." },
  { name: "Adjust", text: "Repair the plan gently when life changes." },
];

export function Principles() {
  return (
    <ol className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {PRINCIPLES.map((p, i) => (
        <li key={p.name} className="rounded-2xl border border-line bg-surface p-5 shadow-soft">
          <span className="font-serif text-sm text-terracotta-dark" aria-hidden="true">
            0{i + 1}
          </span>
          <h3 className="mt-1 font-serif text-xl font-semibold">{p.name}</h3>
          <p className="mt-2 text-sm leading-relaxed text-muted">{p.text}</p>
        </li>
      ))}
    </ol>
  );
}
