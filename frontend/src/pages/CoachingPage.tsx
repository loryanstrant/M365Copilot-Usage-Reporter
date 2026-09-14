import { useEffect, useState } from "react";
import { api } from "../api/client";
import { downloadCsv } from "../api/csv";
import type {
  CoachingPairsData,
  PeerGroup,
  PeerGroupBy,
  PeerMember,
} from "../api/types";
import FilterBar from "../components/FilterBar";
import {
  filterDeps,
  metricLabel,
  metricsQuery,
  useFilters,
  type Metric,
} from "../filters/FiltersContext";

const GROUP_OPTIONS: { value: PeerGroupBy; label: string }[] = [
  { value: "department", label: "Department" },
  { value: "manager", label: "Manager" },
  { value: "office_location", label: "Office" },
];

export default function CoachingPage() {
  const filters = useFilters();
  const metric = filters.metric;
  const [groupBy, setGroupBy] = useState<PeerGroupBy>("department");
  const [data, setData] = useState<CoachingPairsData | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const q = metricsQuery(filters);
        setData(
          await api<CoachingPairsData>(
            `/metrics/coaching-pairs${q ? q + "&" : "?"}group_by=${groupBy}&metric=${metric}&per_group=3`,
          ),
        );
      } catch {
        /* ignore */
      }
    })();
  }, [filterDeps(filters), groupBy, metric]);

  const groups = data?.groups ?? [];
  const withPairs = groups.filter((g) => g.pairs.length > 0);
  const label = data?.group_label ?? "Department";

  function exportCsv() {
    downloadCsv(
      "coaching-pairs.csv",
      [label, "Leader", `Leader ${metricLabel(metric)}`, "Laggard", `Laggard ${metricLabel(metric)}`, "Gap", "Laggard last use"],
      withPairs.flatMap((g) =>
        g.pairs.map((p) => [
          g.name,
          p.leader.display_name,
          p.leader[metric],
          p.laggard.display_name,
          p.laggard[metric],
          p.gap,
          p.laggard.last_use ?? "never",
        ]),
      ),
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Coaching pairs</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Leaders and laggards side by side <em>within the same team</em> — so you can
            partner someone who has barely started with a colleague who already
            gets value from Copilot.
          </p>
        </div>
        <button onClick={exportCsv} className="btn-secondary whitespace-nowrap">
          Export CSV
        </button>
      </div>

      <FilterBar />

      <div className="card flex flex-wrap items-center gap-4 p-4">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          Compare people within
        </span>
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-1 dark:border-slate-600">
          {GROUP_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setGroupBy(o.value)}
              aria-pressed={groupBy === o.value}
              className={`h-[30px] rounded-md px-3 text-xs font-medium transition-colors ${
                groupBy === o.value
                  ? "bg-brand-600 text-white shadow-sm"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-slate-400">
          Ranked by {metricLabel(metric).toLowerCase()} · switch the measure and date
          range in the filters above
        </span>
      </div>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          label="Pairing opportunities"
          value={data?.totals.pairs ?? 0}
          hint="Laggards with a leader alongside"
          tone="brand"
        />
        <Kpi
          label={`${label}s with a gap`}
          value={data?.totals.groups_with_pairs ?? 0}
          hint={`of ${data?.totals.groups ?? 0} with licensed users`}
        />
        <Kpi
          label="Leaders to learn from"
          value={data?.totals.leaders ?? 0}
          hint="Top users in their own team"
          tone="green"
        />
        <Kpi
          label="Laggards to lift"
          value={data?.totals.laggards ?? 0}
          hint="Well below their team average"
          tone="amber"
        />
      </div>

      {withPairs.length === 0 ? (
        <div className="card p-8 text-center text-sm text-slate-500">
          No coaching pairs for this selection — either usage is evenly spread, or
          the filters are too narrow.
        </div>
      ) : (
        <div className="space-y-6">
          {withPairs.map((g) => (
            <GroupCard key={g.key} group={g} metric={metric} label={label} />
          ))}
        </div>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  hint,
  tone = "slate",
}: {
  label: string;
  value: number;
  hint?: string;
  tone?: "slate" | "brand" | "green" | "amber";
}) {
  const toneClass = {
    slate: "text-slate-900 dark:text-white",
    brand: "text-brand-600 dark:text-brand-400",
    green: "text-emerald-600 dark:text-emerald-400",
    amber: "text-amber-600 dark:text-amber-400",
  }[tone];
  return (
    <div className="card p-5">
      <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
      <div className={`mt-1 text-3xl font-bold ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

function GroupCard({
  group,
  metric,
  label,
}: {
  group: PeerGroup;
  metric: Metric;
  label: string;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-slate-700">
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
          <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">
            {group.name}
          </h3>
        </div>
        <div className="flex items-center gap-5 text-right">
          <Stat value={`${group.adoption_rate}%`} caption="adopted" />
          <Stat value={`${group.active}/${group.licensed}`} caption="active / licensed" />
          <Stat value={group.avg} caption={`avg ${metricLabel(metric).toLowerCase()}`} />
        </div>
      </div>

      <ul className="divide-y divide-slate-100 dark:divide-slate-700">
        {group.pairs.map((p, i) => (
          <li
            key={`${p.leader.user_id}-${p.laggard.user_id}-${i}`}
            className="grid items-center gap-4 px-5 py-4 md:grid-cols-[1fr_auto_1fr]"
          >
            <Person person={p.leader} metric={metric} role="leader" />
            <div className="flex flex-col items-center gap-1 text-center">
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                could coach
              </span>
              <span className="text-[11px] text-slate-400">
                {p.gap} {metricLabel(metric).toLowerCase()} apart
              </span>
            </div>
            <Person person={p.laggard} metric={metric} role="laggard" />
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ value, caption }: { value: string | number; caption: string }) {
  return (
    <div>
      <div className="text-sm font-semibold tabular-nums text-slate-800 dark:text-slate-100">
        {value}
      </div>
      <div className="text-[11px] text-slate-400">{caption}</div>
    </div>
  );
}

function Person({
  person,
  metric,
  role,
}: {
  person: PeerMember;
  metric: Metric;
  role: "leader" | "laggard";
}) {
  const isLeader = role === "leader";
  const accent = isLeader
    ? "border-emerald-200 bg-emerald-50/60 dark:border-emerald-900/40 dark:bg-emerald-900/10"
    : "border-amber-200 bg-amber-50/60 dark:border-amber-900/40 dark:bg-amber-900/10";
  const badge = isLeader
    ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
    : "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300";
  return (
    <div className={`rounded-lg border px-4 py-3 ${accent}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">
            {person.display_name}
          </div>
          <div className="truncate text-xs text-slate-500 dark:text-slate-400">
            {person.job_title ?? person.department ?? "—"}
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${badge}`}>
          {isLeader ? "Leader" : "Laggard"}
        </span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-xl font-bold tabular-nums text-slate-900 dark:text-white">
          {person[metric]}
        </span>
        <span className="text-xs text-slate-500">{metricLabel(metric).toLowerCase()}</span>
        <span className="ml-auto text-[11px] text-slate-400">
          {person.last_use ? `last used ${person.last_use}` : "never used"}
        </span>
      </div>
    </div>
  );
}
