import ChartCard from "./ChartCard";

export interface PeerSeries {
  prompts: number;
  conversations: number;
  apps: number;
}

export interface PeerComparisonData {
  mine: PeerSeries;
  team: PeerSeries | null;
  team_label: string | null;
  team_size: number;
  organisation: PeerSeries;
  organisation_size: number;
  percentile: Partial<Record<keyof PeerSeries, number | null>>;
  period_from: string | null;
  period_to: string | null;
}

export interface PeerMeasure {
  key: keyof PeerSeries;
  label: string;
}

function fmtPeriod(from: string | null, to: string | null): string {
  if (!from && !to) return "the selected period";
  const d = (s: string) =>
    new Date(`${s}T00:00:00`).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  if (from && to) return `${d(from)} – ${d(to)}`;
  return from ? `since ${d(from)}` : `up to ${d(to as string)}`;
}

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] ?? s[v] ?? s[0]}`;
}

/**
 * You, your team and your organisation on the same measures.
 *
 * Three things this component is careful about, all of them decided in
 * docs/specs/comparisons-and-timelines.md:
 *
 * - The team row is simply **absent** when the server withholds it, never a
 *   zero bar. An empty bar reads as "you are miles ahead of your team" when it
 *   means "that team is too small to show without identifying someone".
 * - The period is named, because three series over different windows would be
 *   arithmetically fine and completely misleading.
 * - The percentile says which population it is measured against.
 */
export default function PeerComparison({
  data,
  measures,
}: {
  data: PeerComparisonData;
  measures: PeerMeasure[];
}) {
  const hasTeam = data.team !== null;
  const subtitle = hasTeam
    ? `You, your team (${data.team_label}) and the organisation · ${fmtPeriod(
        data.period_from,
        data.period_to,
      )}`
    : `You and the organisation · ${fmtPeriod(data.period_from, data.period_to)}`;

  return (
    <ChartCard title="How you compare" subtitle={subtitle}>
      <div className="space-y-5 text-sm">
        {measures.map((m) => {
          const mine = data.mine[m.key] ?? 0;
          const team = data.team ? data.team[m.key] ?? 0 : null;
          const org = data.organisation[m.key] ?? 0;
          const max = Math.max(mine, team ?? 0, org, 1);
          const pct = data.percentile?.[m.key];
          const rows: { label: string; value: number; bar: string }[] = [
            { label: "You", value: mine, bar: "bg-brand-600" },
            ...(team !== null
              ? [{ label: "Your team", value: team, bar: "bg-brand-300" }]
              : []),
            { label: "Organisation", value: org, bar: "bg-slate-400" },
          ];
          return (
            <div key={m.key}>
              <div className="mb-1 flex items-baseline justify-between gap-3">
                <span className="font-medium text-slate-800 dark:text-slate-100">
                  {m.label}
                </span>
                <span className="text-xs text-slate-400 dark:text-slate-500">
                  {mine.toLocaleString()}
                  {pct != null
                    ? ` · ${ordinal(pct)} percentile across the organisation`
                    : ""}
                </span>
              </div>
              <div className="space-y-1">
                {rows.map((r) => (
                  <div key={r.label} className="flex items-center gap-2">
                    <span className="w-28 shrink-0 text-xs text-slate-500 dark:text-slate-400">
                      {r.label}
                    </span>
                    <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
                      <div
                        className={`h-full rounded-full ${r.bar}`}
                        style={{ width: `${Math.max((r.value / max) * 100, 2)}%` }}
                      />
                    </div>
                    <span className="w-12 shrink-0 text-right text-xs tabular-nums text-slate-500 dark:text-slate-400">
                      {r.value.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
      {!hasTeam && (
        <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
          No team comparison:{" "}
          {data.team_size > 0
            ? `your team is too small to show without identifying someone (${data.team_size} other ${
                data.team_size === 1 ? "person" : "people"
              }).`
            : "we don't know which team you're in — your directory record has no department or manager."}
        </p>
      )}
    </ChartCard>
  );
}
