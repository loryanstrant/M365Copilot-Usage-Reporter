import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { downloadCsv } from "../api/csv";
import type { AppRow, CategoryRow, UserRow } from "../api/types";
import ChartCard from "../components/ChartCard";
import FilterBar from "../components/FilterBar";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";

function fmtDate(value: string | null): string {
  return value ?? "—";
}

export default function UsagePage() {
  const filters = useFilters();
  const [apps, setApps] = useState<AppRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [categories, setCategories] = useState<CategoryRow[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const q = metricsQuery(filters);
        const [a, u, c] = await Promise.all([
          api<AppRow[]>(`/metrics/by-app${q}`),
          api<UserRow[]>(`/metrics/by-user${q ? q + "&" : "?"}limit=200`),
          api<CategoryRow[]>("/metrics/categories"),
        ]);
        setApps(a);
        setUsers(u);
        setCategories(c);
      } catch {
        /* ignore */
      }
    })();
  }, [filterDeps(filters)]);

  const shownApps = apps;

  function exportApps() {
    downloadCsv(
      "usage-by-app.csv",
      ["App", "Prompts", "Conversations", "Avg per conversation", "Users", "Last use"],
      shownApps.map((a) => [
        a.app_name ?? "",
        a.prompts,
        a.conversations,
        a.avg_prompts_per_conversation,
        a.users,
        a.last_use ?? "",
      ]),
    );
  }

  function exportUsers() {
    downloadCsv(
      "usage-by-user.csv",
      ["User", "Department", "Prompts", "Conversations", "Avg per conversation", "Days since last"],
      users.map((u) => [
        u.display_name ?? u.user_id,
        u.department ?? "",
        u.prompts,
        u.conversations,
        u.avg_prompts_per_conversation,
        u.days_since_last ?? "",
      ]),
    );
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Usage</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Per-app and per-user breakdown, plus engagement distribution.
        </p>
      </div>

      <FilterBar />

      <ChartCard
        title="Engagement distribution"
        subtitle="Licensed users by prompt count (trailing 30 days)"
      >
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={categories} margin={{ left: -20, right: 8, top: 8 }}>
            <XAxis dataKey="category" tick={{ fontSize: 11 }} stroke="#94a3b8" />
            <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="users" fill="#3b6ef5" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="card">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Usage by app
          </h3>
          <button onClick={exportApps} className="btn-secondary">
            Export CSV
          </button>
        </div>
        <Table
          head={["App", "Prompts", "Conversations", "Avg / conv.", "Users", "Last use"]}
          rows={shownApps.map((a) => [
            a.app_name ?? "—",
            a.prompts,
            a.conversations,
            a.avg_prompts_per_conversation,
            a.users,
            fmtDate(a.last_use),
          ])}
        />
      </div>

      <div className="card">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Top users
          </h3>
          <button onClick={exportUsers} className="btn-secondary">
            Export CSV
          </button>
        </div>
        <Table
          head={["User", "Department", "Prompts", "Conversations", "Avg / conv.", "Days since last"]}
          rows={users.map((u) => [
            u.display_name ?? u.user_id,
            u.department ?? "—",
            u.prompts,
            u.conversations,
            u.avg_prompts_per_conversation,
            u.days_since_last ?? "—",
          ])}
        />
      </div>
    </div>
  );
}

function Table({
  head,
  rows,
}: {
  head: string[];
  rows: (string | number)[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
            {head.map((h, i) => (
              <th key={i} className="px-5 py-3 font-medium">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={head.length}
                className="px-5 py-6 text-center text-slate-400"
              >
                No data yet.
              </td>
            </tr>
          ) : (
            rows.map((row, i) => (
              <tr
                key={i}
                className="border-t border-slate-100 dark:border-slate-700"
              >
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className={`px-5 py-3 ${j === 0 ? "font-medium text-slate-800 dark:text-slate-100" : "tabular-nums text-slate-600 dark:text-slate-300"}`}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
