import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { downloadCsv } from "../api/csv";
import type {
  AppDailyPoint,
  AppRow,
  BreakdownRow,
  CategoryRow,
  UserRow,
} from "../api/types";
import ChartCard from "../components/ChartCard";
import ChartTooltip from "../components/ChartTooltip";
import { barGradId } from "../components/chartTheme";
import AppLabel from "../components/AppLabel";
import AppTrendGrid, { type AppSort } from "../components/AppTrendGrid";
import DataTable, { type Column } from "../components/DataTable";
import FilterBar from "../components/FilterBar";
import SegmentedControl from "../components/SegmentedControl";
import { filterDeps, metricLabel, metricsQuery, useFilters } from "../filters/FiltersContext";
import { useTheme } from "../theme/ThemeContext";

const RADAR_COLORS = ["#2f5ae0", "#22c55e", "#f59e0b", "#a855f7", "#ef4444", "#06b6d4"];

const APP_COLUMNS: Column<AppRow>[] = [
  { key: "app_name", header: "App", type: "text", accessor: (a) => a.app_name, render: (a) => <AppLabel name={a.app_name} /> },
  { key: "prompts", header: "Prompts", type: "number", accessor: (a) => a.prompts },
  { key: "conversations", header: "Conversations", type: "number", accessor: (a) => a.conversations },
  { key: "avg", header: "Avg / conv.", type: "number", accessor: (a) => a.avg_prompts_per_conversation },
  { key: "users", header: "Users", type: "number", accessor: (a) => a.users },
  { key: "last_use", header: "Last use", type: "date", accessor: (a) => a.last_use, render: (a) => a.last_use ?? "—" },
];

const USER_COLUMNS: Column<UserRow>[] = [
  { key: "user", header: "User", type: "text", accessor: (u) => u.display_name ?? u.user_id },
  { key: "department", header: "Department", type: "text", accessor: (u) => u.department, render: (u) => u.department ?? "—" },
  { key: "prompts", header: "Prompts", type: "number", accessor: (u) => u.prompts },
  { key: "conversations", header: "Conversations", type: "number", accessor: (u) => u.conversations },
  { key: "avg", header: "Avg / conv.", type: "number", accessor: (u) => u.avg_prompts_per_conversation },
  { key: "days_since_last", header: "Days since last", type: "number", accessor: (u) => u.days_since_last, render: (u) => u.days_since_last ?? "—" },
];

export default function UsagePage() {
  const filters = useFilters();
  const { theme } = useTheme();
  const metric = filters.metric;
  const [apps, setApps] = useState<AppRow[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [radar, setRadar] = useState<BreakdownRow[]>([]);
  const [appDaily, setAppDaily] = useState<AppDailyPoint[]>([]);
  const [appSort, setAppSort] = useState<AppSort>("usage");

  useEffect(() => {
    (async () => {
      try {
        const q = metricsQuery(filters);
        const [a, u, c, r, ad] = await Promise.all([
          api<AppRow[]>(`/metrics/by-app${q}`),
          api<UserRow[]>(`/metrics/by-user${q ? q + "&" : "?"}limit=200`),
          api<CategoryRow[]>("/metrics/categories"),
          api<BreakdownRow[]>(
            `/metrics/breakdown${q ? q + "&" : "?"}dim1=department&dim2=app_name`,
          ),
          api<AppDailyPoint[]>(`/metrics/by-app-daily${q}`),
        ]);
        setApps(a);
        setUsers(u);
        setCategories(c);
        setRadar(r);
        setAppDaily(ad);
      } catch {
        /* ignore */
      }
    })();
  }, [filterDeps(filters)]);

  const shownApps = apps;

  // Radar: usage profile of the top apps across departments. Recharts needs one
  // row per axis (app) with a series key per department, rather than ECharts'
  // indicator/value-array shape.
  const { radarData, radarDepts } = useMemo(() => {
    const apps = [...new Set(radar.map((r) => r.d2 ?? "Unknown"))].slice(0, 6);
    const depts = [...new Set(radar.map((r) => r.d1 ?? "Unknown"))].slice(0, 5);
    const lookup = new Map(radar.map((r) => [`${r.d1}|${r.d2}`, r[metric]]));
    const data = apps.map((app) => {
      const row: Record<string, string | number> = { app };
      depts.forEach((d) => {
        row[d] = lookup.get(`${d}|${app}`) ?? 0;
      });
      return row;
    });
    return { radarData: data, radarDepts: depts };
  }, [radar, metric]);

  const radarAxisColor = theme === "dark" ? "#cbd5e1" : "#475569";
  const radarGridColor =
    theme === "dark" ? "rgba(148,163,184,0.25)" : "rgba(100,116,139,0.25)";

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
        title="Conversations & prompts by app"
        subtitle={`Monthly trend per app · ${metricLabel(metric).toLowerCase()} trendline`}
        action={
          <SegmentedControl
            ariaLabel="Sort app charts"
            value={appSort}
            onChange={setAppSort}
            options={[
              { value: "usage", label: `By ${metricLabel(metric).toLowerCase()}` },
              { value: "name", label: "By app" },
            ]}
          />
        }
      >
        <AppTrendGrid rows={appDaily} metric={metric} sortBy={appSort} />
      </ChartCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <ChartCard
          title="Engagement distribution"
          subtitle="Licensed users by prompt count (trailing 30 days)"
        >
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={categories} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="category" tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(59,110,245,0.06)" }} content={<ChartTooltip />} />
              <Bar dataKey="users" fill={`url(#${barGradId(0)})`} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Usage profile by department" subtitle={`App mix across departments · ${metricLabel(metric)}`}>
          {radar.length === 0 ? (
            <div className="py-16 text-center text-sm text-slate-400">No data.</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <RadarChart data={radarData} outerRadius="68%">
                <PolarGrid stroke={radarGridColor} />
                <PolarAngleAxis
                  dataKey="app"
                  tick={{ fontSize: 11, fill: radarAxisColor }}
                />
                <PolarRadiusAxis tick={{ fontSize: 10, fill: radarAxisColor }} />
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {radarDepts.map((d, i) => (
                  <Radar
                    key={d}
                    name={d}
                    dataKey={d}
                    stroke={RADAR_COLORS[i % RADAR_COLORS.length]}
                    fill={RADAR_COLORS[i % RADAR_COLORS.length]}
                    fillOpacity={0.12}
                    strokeWidth={2}
                  />
                ))}
              </RadarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      <div className="card">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Usage by app
          </h3>
          <button onClick={exportApps} className="btn-secondary">
            Export CSV
          </button>
        </div>
        <DataTable
          rows={shownApps}
          getRowKey={(a) => a.app_name ?? "—"}
          initialSort={{ key: "prompts", dir: "desc" }}
          columns={APP_COLUMNS}
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
        <DataTable
          rows={users}
          getRowKey={(u) => u.user_id}
          initialSort={{ key: "prompts", dir: "desc" }}
          columns={USER_COLUMNS}
        />
      </div>
    </div>
  );
}
