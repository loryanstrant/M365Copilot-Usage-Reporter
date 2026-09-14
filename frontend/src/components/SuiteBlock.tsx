import { CURRENT_SOLUTION_ID, SUITE, type SuiteSolution } from "../lib/suite";

function Tile({ s }: { s: SuiteSolution }) {
  const isCurrent = s.id === CURRENT_SOLUTION_ID;

  const inner = (
    <>
      <div className="relative overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
        <img
          src={`/suite/${s.id}.png`}
          alt={`${s.eyebrow} ${s.name}`}
          loading="lazy"
          className="block aspect-[4/3] w-full bg-slate-100 object-cover object-top dark:bg-slate-900"
        />
        {isCurrent && (
          <span className="absolute right-2 top-2 rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
            You are here
          </span>
        )}
      </div>
      <div className="mt-3">
        <div className="text-xs font-semibold text-brand-600 dark:text-brand-500">
          {s.eyebrow}
        </div>
        <div className="text-sm font-semibold text-slate-900 dark:text-white">{s.name}</div>
        <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          {s.description}
        </p>
      </div>
    </>
  );

  if (isCurrent) {
    return (
      <div className="rounded-xl p-2 ring-2 ring-brand-600 ring-offset-2 ring-offset-white dark:ring-offset-slate-800">
        {inner}
      </div>
    );
  }

  return (
    <a
      href={s.repo}
      target="_blank"
      rel="noopener noreferrer"
      className="group rounded-xl p-2 transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/50"
    >
      {inner}
      <span className="mt-2 inline-block text-xs font-medium text-brand-600 group-hover:underline dark:text-brand-500">
        View on GitHub →
      </span>
    </a>
  );
}

export default function SuiteBlock() {
  return (
    <div className="card p-6">
      <h3 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-200">
        Part of a suite of Copilot reporting tools
      </h3>
      <p className="mb-5 text-sm text-slate-500 dark:text-slate-400">
        Four self-hosted, containerised solutions that report on different corners of
        Microsoft 365 Copilot and Copilot Studio. Each runs independently — use one, or
        run them side by side.
      </p>
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        {SUITE.map((s) => (
          <Tile key={s.id} s={s} />
        ))}
      </div>
    </div>
  );
}
