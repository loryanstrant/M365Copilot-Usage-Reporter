import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { downloadCsv } from "../api/csv";
import type { LaggardsData } from "../api/types";
import ChartCard from "../components/ChartCard";

const IDLE = "#f59e0b";

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
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                {["User", "Department", "Office", "Prompts (30d)", "Last use", "Days since last"].map(
                  (h) => (
                    <th key={h} className="px-5 py-3 font-medium">
                      {h}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-6 text-center text-slate-400">
                    No data yet.
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                  <tr
                    key={u.user_id}
                    className={`border-t border-slate-100 dark:border-slate-700 ${u.inactive ? "bg-amber-50/40 dark:bg-amber-900/10" : ""}`}
                  >
                    <td className="px-5 py-3 font-medium text-slate-800 dark:text-slate-100">
                      {u.display_name}
                    </td>
                    <td className="px-5 py-3 text-slate-600 dark:text-slate-300">
                      {u.department ?? "—"}
                    </td>
                    <td className="px-5 py-3 text-slate-600 dark:text-slate-300">
                      {u.office_location ?? "—"}
                    </td>
                    <td className="px-5 py-3 tabular-nums text-slate-600 dark:text-slate-300">
                      {u.prompts_30d}
                    </td>
                    <td className="px-5 py-3 tabular-nums text-slate-600 dark:text-slate-300">
                      {u.last_use ?? "never"}
                    </td>
                    <td className="px-5 py-3 tabular-nums text-slate-600 dark:text-slate-300">
                      {u.days_since_last ?? "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
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
          <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} stroke="#94a3b8" width={110} />
          <Tooltip />
          <Bar dataKey="inactive_users" radius={[0, 4, 4, 0]}>
            {rows.map((_, i) => (
              <Cell key={i} fill={IDLE} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
