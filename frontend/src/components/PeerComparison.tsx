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
  organisation: PeerSeries | null;
  organisation_size: number;
  percentile: Partial<Record<keyof PeerSeries, number | null>>;
  period_from: string | null;
  period_to: string | null;
  /** Why the team series is or is not drawn. Stated, never inferred. */
  team_state: "shown" | "too_small" | "unknown";
  /** The organisation series is withheld on the same floor, for the same
   * arithmetic — a mean over four people plus your own figure is a disclosure
   * whatever the group is called. */
  organisation_state: "shown" | "too_small";
  /** The disclosure floor, owned and enforced by the server. */
  min_team_peers: number;
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

function withheldNote(data: PeerComparisonData): string {
  if (data.team_state === "too_small") {
    const who =
      data.team_size === 0
        ? `you are the only person on file in ${data.team_label ?? "your team"}`
        : `${data.team_label ?? "your team"} has ${data.team_size} other ${
            data.team_size === 1 ? "person" : "people"
          } on file`;
    return `No team comparison — ${who}, and a team average is only shown from ${data.min_team_peers}. Below that, the average and your own figure together would give an individual's number away.`;
  }
  return "No team comparison — we don't know which team you're in, because your directory record has no department and no manager. Populating either in Entra will fill this in.";
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
 * - The two withheld cases are told apart by `team_state` rather than guessed
 *   at from a zero peer count, because a department of one and a record with
 *   no department both have no peers and are not the same situation. Saying
 *   "we don't know which team you're in" to somebody whose department is on
 *   file is a false statement about their own data, and it points an
 *   administrator at the wrong problem.
 * - The floor is read from the response, so the sentence cannot drift away
 *   from the rule the endpoint actually applies.
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
  const hasOrg = data.organisation !== null;
  const who = hasTeam
    ? `You, your team (${data.team_label}) and the organisation`
    : hasOrg
      ? "You and the organisation"
      : "You only";
  const subtitle = `${who} · ${fmtPeriod(data.period_from, data.period_to)}`;

  return (
    <ChartCard title="How you compare" subtitle={subtitle}>
      <div className="space-y-5 text-sm">
        {measures.map((m) => {
          const mine = data.mine[m.key] ?? 0;
          const team = data.team ? data.team[m.key] ?? 0 : null;
          const org = data.organisation ? data.organisation[m.key] ?? 0 : null;
          const max = Math.max(mine, team ?? 0, org ?? 0, 1);
          const pct = data.percentile?.[m.key];
          const rows: { label: string; value: number; bar: string }[] = [
            { label: "You", value: mine, bar: "bg-brand-600" },
            ...(team !== null
              ? [{ label: "Your team", value: team, bar: "bg-brand-300" }]
              : []),
            ...(org !== null
              ? [{ label: "Organisation", value: org, bar: "bg-slate-400" }]
              : []),
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
          {withheldNote(data)}
        </p>
      )}
      {!hasOrg && (
        <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
          No organisation comparison either — only {data.organisation_size} other{" "}
          {data.organisation_size === 1 ? "person has" : "people have"} activity on
          file, which is below the same floor of {data.min_team_peers}. An average
          over a group that small is an individual's figure in disguise.
        </p>
      )}
    </ChartCard>
  );
}
