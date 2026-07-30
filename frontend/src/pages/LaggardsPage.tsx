import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { downloadCsv } from "../api/csv";
import type { LaggardRow, LaggardsData } from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import DataTable, { type Column } from "../components/DataTable";

const LAGGARD_COLUMNS: Column<LaggardRow>[] = [
  { key: "user", header: "User", type: "text", accessor: (u) => u.display_name },
  { key: "department", header: "Department", type: "text", accessor: (u) => u.department, render: (u) => u.department ?? "—" },
  { key: "office", header: "Office", type: "text", accessor: (u) => u.office_location, render: (u) => u.office_location ?? "—" },
  { key: "prompts_30d", header: "Prompts (30d)", type: "number", accessor: (u) => u.prompts_30d },
  { key: "last_use", header: "Last use", type: "date", accessor: (u) => u.last_use, render: (u) => u.last_use ?? "never" },
  { key: "days_since_last", header: "Days since last", type: "number", accessor: (u) => u.days_since_last, render: (u) => u.days_since_last ?? "—" },
];

export default function LaggardsPage() {
  const [data, setData] = useState<LaggardsData | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setData(await api<LaggardsData>("/metrics/laggards"));
      } catch {
        /* ignore */
      }
    })();
  }, []);

  const users = data?.users ?? [];
  const inactive = users.filter((u) => u.inactive);

  function exportCsv() {
    downloadCsv(
      "laggards.csv",
      ["User", "Department", "Office", "Prompts (30d)", "Last use", "Days since last", "Inactive"],
      users.map((u) => [
        u.display_name,
        u.department ?? "",
        u.office_location ?? "",
        u.prompts_30d,
        u.last_use ?? "",
        u.days_since_last ?? "",
        u.inactive ? "Yes" : "No",
      ]),
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Laggards</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Licensed users with little or no Copilot usage in the last 30 days.
          </p>
        </div>
        <button onClick={exportCsv} className="btn-secondary whitespace-nowrap">
          Export CSV
        </button>
      </div>

      <div className="grid gap-5 sm:grid-cols-3">
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-400">Inactive licensed users</div>
          <div className="mt-1 text-3xl font-bold text-slate-900 dark:text-white">
            {inactive.length}
          </div>
          <div className="mt-1 text-xs text-slate-500">of {users.length} licensed</div>
        </div>
        <div className="lg:col-span-2 grid gap-6 sm:grid-cols-2">
          <IdleBar title="Most inactive departments" rows={data?.top_departments ?? []} />
          <IdleBar title="Most inactive offices" rows={data?.top_offices ?? []} />
        </div>
      </div>

      <div className="card">
        <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Licensed users by inactivity
          </h3>
        </div>
        <DataTable
          rows={users}
          getRowKey={(u) => u.user_id}
          initialSort={{ key: "days_since_last", dir: "desc" }}
          rowClassName={(u) => (u.inactive ? "bg-amber-50/40 dark:bg-amber-900/10" : "")}
          columns={LAGGARD_COLUMNS}
        />
      </div>
    </div>
  );
}

function IdleBar({
  title,
  rows,
}: {
  title: string;
  rows: { name: string; inactive_users: number }[];
}) {
  return (
    <ChartCard title={title} subtitle="Inactive users">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={rows} layout="vertical" margin={{ left: 10, right: 12, top: 4 }}>
          <defs>
            <linearGradient id="idleGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.55} />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity={1} />
            </linearGradient>
          </defs>
          <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} stroke="#94a3b8" width={110} />
          <Tooltip cursor={{ fill: "rgba(245,158,11,0.08)" }} content={<ChartTooltip />} />
          <Bar dataKey="inactive_users" radius={[0, 6, 6, 0]} fill="url(#idleGrad)">
            {rows.map((_, i) => (
              <Cell key={i} fill="url(#idleGrad)" />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
