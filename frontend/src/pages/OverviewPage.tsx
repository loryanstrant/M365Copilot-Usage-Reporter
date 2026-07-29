import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type {
  ActiveInactive,
  AppRow,
  DailyPoint,
  MetricsSummary,
  NamedCount,
} from "../api/types";
import ChartCard from "../components/ChartCard";
import { CHART_COLORS, ChartGradients, barGradId, gradId } from "../components/chartTheme";
import FilterBar from "../components/FilterBar";
import KpiCard from "../components/KpiCard";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";

const PIE_COLORS = CHART_COLORS;
const BAR_COLOR = "#3b6ef5";

// chat-types endpoint payload
interface ChatTypeData {
  chat_types: NamedCount[];
  conversation_locations: NamedCount[];
}

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

export default function OverviewPage() {
  const filters = useFilters();
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [daily, setDaily] = useState<DailyPoint[]>([]);
  const [apps, setApps] = useState<AppRow[]>([]);
  const [activity, setActivity] = useState<ActiveInactive | null>(null);
  const [splits, setSplits] = useState<ChatTypeData | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const q = metricsQuery(filters);
        const [s, d, a, ai, ct] = await Promise.all([
          api<MetricsSummary>(`/metrics/summary${q}`),
          api<DailyPoint[]>(`/metrics/daily${q}`),
          api<AppRow[]>(`/metrics/by-app${q}`),
          api<ActiveInactive>("/metrics/active-inactive"),
          api<ChatTypeData>(`/metrics/chat-types${q}`),
        ]);
        setSummary(s);
        setDaily(d);
        setApps(a);
        setActivity(ai);
        setSplits(ct);
      } catch {
        /* ignore */
      } finally {
        setLoaded(true);
      }
    })();
  }, [filterDeps(filters)]);

  const hasData = (summary?.prompts ?? 0) > 0;
  const activityData = activity
    ? [
        { name: "Active", value: activity.active },
        { name: "Inactive", value: activity.inactive },
      ]
    : [];
  const convLocData = (splits?.conversation_locations ?? []).map((r) => ({
    name: r.name ?? "Unknown",
    value: r.prompts,
  }));
  const chatTypeData = (splits?.chat_types ?? []).map((r) => ({
    name: r.name ?? "Unknown",
    value: r.prompts,
  }));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Overview</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Microsoft 365 Copilot usage at a glance.
        </p>
      </div>

      <FilterBar />

      {loaded && !hasData && (
        <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800">
          No usage data for this selection. Adjust the filters, or configure
          Microsoft Graph in <span className="font-semibold">Settings</span> and run an ingest.
        </div>
      )}

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-5">
        <KpiCard label="Prompts" value={summary?.prompts ?? "—"} />
        <KpiCard label="Conversations" value={summary?.conversations ?? "—"} />
        <KpiCard
          label="Avg prompts / conversation"
          value={summary?.avg_prompts_per_conversation ?? "—"}
        />
        <KpiCard
          label="Adoption"
          value={summary ? pct(summary.adoption_rate) : "—"}
          hint={
            summary
              ? `${summary.active_users} active of ${summary.licensed_users} licensed`
              : undefined
          }
        />
        <KpiCard
          label="Copilot score"
          value={summary?.copilot_score ?? "—"}
          hint="0–100, from daily volume"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <ChartCard
          title="Prompts over time"
          subtitle="Daily prompt volume"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={daily} margin={{ left: -20, right: 8, top: 8 }}>
              <ChartGradients />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" tickMargin={8} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="prompts"
                stroke={BAR_COLOR}
                fill={`url(#${gradId(0)})`}
                strokeWidth={2.5}
              />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Active vs inactive" subtitle="Licensed users, last 30 days">
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={activityData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
                {activityData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <ChartCard title="Where prompts happen" subtitle="App vs Chat">
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={convLocData} dataKey="value" nameKey="name" outerRadius={80}>
                {convLocData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Chat types" subtitle="Work / Web / Temporary">
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={chatTypeData} dataKey="value" nameKey="name" outerRadius={80}>
                {chatTypeData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Usage by app" subtitle="Prompts per surface">
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={apps} margin={{ left: -20, right: 8, top: 8 }}>
              <ChartGradients />
              <XAxis dataKey="app_name" tick={{ fontSize: 10 }} stroke="#94a3b8" interval={0} angle={-30} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="prompts" fill={`url(#${barGradId(0)})`} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
