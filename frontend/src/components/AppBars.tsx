import { type ReactNode } from "react";
import { appLogoSrc } from "./AppLabel";

export interface AppBarRow {
  /** App name as Graph reports it. Null renders as an em dash. */
  name: string | null;
  value: number;
  /** Optional node shown after the value — a delta chip, say. */
  trailing?: ReactNode;
}

/**
 * A ranked list of Microsoft 365 apps as labelled bars with their product
 * logos.
 *
 * This is the suite's one treatment for "which apps did Copilot get used in".
 * It reads better than a two-column table at a glance, and keeping it in one
 * component stops the executive briefing and the personal view drifting into
 * two different-looking answers to the same question.
 *
 * Bars are sized against the largest value present, not against a total, so a
 * single dominant app doesn't flatten everything else into invisibility.
 */
export default function AppBars({
  rows,
  emptyMessage = "No app usage to show yet.",
}: {
  rows: AppBarRow[];
  emptyMessage?: string;
}) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">{emptyMessage}</p>
    );
  }
  const max = Math.max(...rows.map((r) => r.value), 1);

  return (
    <div className="space-y-3">
      {rows.map((row) => {
        const src = appLogoSrc(row.name);
        const label = row.name ?? "—";
        return (
          <div key={label} className="flex items-center gap-3">
            {src ? (
              <img
                src={src}
                alt=""
                aria-hidden
                className="h-5 w-5 shrink-0 object-contain"
              />
            ) : (
              // Keeps names aligned when an app has no logo.
              <span className="h-5 w-5 shrink-0" aria-hidden />
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                  {label}
                </span>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="tabular-nums text-sm text-slate-500 dark:text-slate-400">
                    {row.value.toLocaleString()}
                  </span>
                  {row.trailing}
                </div>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
                <div
                  className="h-full rounded-full bg-brand-500"
                  style={{ width: `${Math.max((row.value / max) * 100, 2)}%` }}
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** The two orders offered wherever these bars are sortable. */
export type AppBarSort = "value" | "name";

export function sortAppBars(rows: AppBarRow[], sort: AppBarSort): AppBarRow[] {
  const copy = [...rows];
  if (sort === "name") {
    return copy.sort((a, b) =>
      (a.name ?? "").localeCompare(b.name ?? "", undefined, { sensitivity: "base" }),
    );
  }
  return copy.sort((a, b) => b.value - a.value);
}

/**
 * Sort switch for the bars. Rendered in a ChartCard's `action` slot, which
 * exists for exactly this.
 */
export function AppBarSortToggle({
  sort,
  onChange,
}: {
  sort: AppBarSort;
  onChange: (next: AppBarSort) => void;
}) {
  const options: { key: AppBarSort; label: string }[] = [
    { key: "value", label: "Most used" },
    { key: "name", label: "A–Z" },
  ];
  return (
    <div
      role="group"
      aria-label="Sort apps"
      className="rounded-lg border border-slate-300 p-0.5 text-xs dark:border-slate-600"
    >
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          aria-pressed={sort === o.key}
          onClick={() => onChange(o.key)}
          className={
            sort === o.key
              ? "rounded-md bg-brand-600 px-2 py-1 font-semibold text-white"
              : "rounded-md px-2 py-1 font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
          }
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
