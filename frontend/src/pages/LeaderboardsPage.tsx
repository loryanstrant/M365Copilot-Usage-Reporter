import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { downloadCsv } from "../api/csv";
import type { LeaderboardRollups, UserRow } from "../api/types";
import ChartCard from "../components/ChartCard";
import FilterBar from "../components/FilterBar";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";

const BAR = "#3b6ef5";

export default function LeaderboardsPage() {
  const filters = useFilters();
  const [rollups, setRollups] = useState<LeaderboardRollups | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const q = metricsQuery(filters);
        const [r, u] = await Promise.all([
          api<LeaderboardRollups>(`/metrics/leaderboard-rollups${q ? q + "&" : "?"}limit=10`),
          api<UserRow[]>(`/metrics/by-user${q ? q + "&" : "?"}limit=200`),
        ]);
        setRollups(r);
        setUsers(u);
      } catch {
        /* ignore */
      }
    })();
  }, [filterDeps(filters)]);

  function exportCsv() {
    downloadCsv(
      "leaderboard.csv",
      ["User", "Department", "Office", "Prompts", "Conversations", "Avg per conversation", "Days since last"],
      users.map((u) => [
        u.display_name ?? u.user_id,
        u.department ?? "",
        u.office_location ?? "",
        u.prompts,
        u.conversations,
        u.avg_prompts_per_conversation,
        u.days_since_last ?? "",
      ]),
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Leaderboards</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Top Copilot users and organisational rollups by prompt volume.
          </p>
        </div>
        <button onClick={exportCsv} className="btn-secondary whitespace-nowrap">
          Export CSV
        </button>
      </div>

      <FilterBar />

      <div className="grid gap-6 lg:grid-cols-3">
        <RollupBar title="Top departments" rows={rollups?.departments ?? []} />
        <RollupBar title="Top offices" rows={rollups?.offices ?? []} />
        <RollupBar title="Top managers" rows={rollups?.managers ?? []} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <RankedList title="Most active — by prompts" rows={users} metric="prompts" />
        <RankedList
          title="Most active — by conversations"
          rows={[...users].sort((a, b) => b.conversations - a.conversations)}
          metric="conversations"
        />
      </div>
    </div>
  );
}

function RollupBar({
  title,
  rows,
}: {
  title: string;
  rows: { name: string | null; prompts: number }[];
}) {
  const data = rows.map((r) => ({ name: r.name ?? "—", prompts: r.prompts }));
  return (
    <ChartCard title={title} subtitle="Prompts">
      <ResponsiveContainer width="100%" height={230}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 12, top: 4 }}>
          <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} stroke="#94a3b8" width={110} />
          <Tooltip />
          <Bar dataKey="prompts" radius={[0, 4, 4, 0]}>
            {data.map((_, i) => (
              <Cell key={i} fill={BAR} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function RankedList({
  title,
  rows,
  metric,
}: {
  title: string;
  rows: UserRow[];
  metric: "prompts" | "conversations";
}) {
  const top = rows.slice(0, 15);
  const max = top.length ? top[0][metric] : 0;
  return (
    <div className="card p-5">
      <h3 className="mb-4 text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h3>
      <ol className="space-y-3">
        {top.length === 0 && <li className="text-sm text-slate-400">No data yet.</li>}
        {top.map((u, i) => (
          <li key={u.user_id} className="flex items-center gap-3">
            <span className="w-5 text-right text-xs font-semibold text-slate-400">{i + 1}</span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                  {u.display_name ?? u.user_id}
                </span>
                <span className="tabular-nums text-sm text-slate-500 dark:text-slate-400">
                  {u[metric]}
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
                <div
                  className="h-full rounded-full bg-brand-500"
                  style={{ width: `${max ? (u[metric] / max) * 100 : 0}%` }}
                />
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
