import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
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
import ChartTooltip from "../components/ChartTooltip";
import { CHART_COLORS, barGradId, gradId } from "../components/chartTheme";
import { AppAxisTick } from "../components/AppLabel";
import FilterBar from "../components/FilterBar";
import KpiCard from "../components/KpiCard";
import { filterDeps, metricLabel, metricsQuery, useFilters } from "../filters/FiltersContext";

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

// "2025-09" -> "Sep 2025" for the month axis.
function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    year: "numeric",
  });
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
  const m = filters.metric;
  const mLabel = metricLabel(m);
  // Overview keeps the app chart to the top 5 surfaces by the selected measure;
  // the full per-app breakdown lives on the Usage page.
  const topApps = useMemo(
    () => [...apps].sort((a, b) => b[m] - a[m]).slice(0, 5),
    [apps, m],
  );
  // Usage over time is aggregated to year+month so a long history stays legible.
  const monthly = useMemo(() => {
    const byMonth = new Map<
      string,
      { key: string; label: string; prompts: number; conversations: number }
    >();
    for (const d of daily) {
      const key = d.date.slice(0, 7); // YYYY-MM
      const cur =
        byMonth.get(key) ?? { key, label: monthLabel(key), prompts: 0, conversations: 0 };
      cur.prompts += d.prompts;
      cur.conversations += d.conversations;
      byMonth.set(key, cur);
    }
    return [...byMonth.values()].sort((a, b) => a.key.localeCompare(b.key));
  }, [daily]);
  const activityData = activity
    ? [
        { name: "Active", value: activity.active },
        { name: "Inactive", value: activity.inactive },
      ]
    : [];
  const convLocData = (splits?.conversation_locations ?? []).map((r) => ({
    name: r.name ?? "Unknown",
    value: r[m],
  }));
  const chatTypeData = (splits?.chat_types ?? []).map((r) => ({
    name: r.name ?? "Unknown",
    value: r[m],
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
          title="Usage over time"
          subtitle="Prompts and conversations per month"
          className="lg:col-span-2"
        >
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={monthly} margin={{ left: -20, right: 8, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.35} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#94a3b8" tickMargin={8} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} />
              <Legend />
              <Area
                type="monotone"
                dataKey="prompts"
                name="Prompts"
                stroke={BAR_COLOR}
                fill={`url(#${gradId(0)})`}
                strokeWidth={2.5}
              />
              <Area
                type="monotone"
                dataKey="conversations"
                name="Conversations"
                stroke="#06b6d4"
                fill={`url(#${gradId(5)})`}
                strokeWidth={2}
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
              <Tooltip content={<ChartTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <ChartCard title={`Where ${mLabel.toLowerCase()} happen`} subtitle="App vs Chat">
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={convLocData} dataKey="value" nameKey="name" outerRadius={80}>
                {convLocData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Legend />
              <Tooltip content={<ChartTooltip />} />
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
              <Tooltip content={<ChartTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Top 5 apps" subtitle={`${mLabel} per surface`}>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={topApps} margin={{ left: -20, right: 8, top: 8 }}>
              <XAxis dataKey="app_name" tick={<AppAxisTick />} stroke="#94a3b8" interval={0} height={44} />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey={m} name={mLabel} fill={`url(#${barGradId(0)})`} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </div>
  );
}
