import { useEffect, useMemo, useState } from "react";
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
import type { LocationsData, NamedCount } from "../api/types";
import ChartCard from "../components/ChartCard";
import FilterBar from "../components/FilterBar";
import { filterDeps, metricsQuery, useFilters } from "../filters/FiltersContext";

const COLORS = ["#2f5ae0", "#22c55e", "#f59e0b", "#a855f7", "#ef4444", "#06b6d4"];

export default function LocationsPage() {
  const filters = useFilters();
  const [data, setData] = useState<LocationsData | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setData(await api<LocationsData>(`/metrics/locations${metricsQuery(filters)}`));
      } catch {
        /* ignore */
      }
    })();
  }, [filterDeps(filters)]);

  // Pivot daily_by_chat_type -> wide rows for the streamgraph.
  const { streamData, chatKeys } = useMemo(() => {
    const rows = data?.daily_by_chat_type ?? [];
    const keys = Array.from(new Set(rows.map((r) => r.chat_type)));
    const byDate = new Map<string, Record<string, number | string>>();
    for (const r of rows) {
      const row = byDate.get(r.date) ?? { date: r.date };
      row[r.chat_type] = (Number(row[r.chat_type] ?? 0) || 0) + r.prompts;
      byDate.set(r.date, row);
    }
    return {
      streamData: Array.from(byDate.values()).sort((a, b) =>
        String(a.date).localeCompare(String(b.date)),
      ),
      chatKeys: keys,
    };
  }, [data]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Where Copilot is used</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Conversation locations, chat types, and the Teams &amp; file surfaces prompts touch.
        </p>
      </div>

      <FilterBar />

      <ChartCard title="Chat types over time" subtitle="Daily prompt volume by chat type (streamgraph)">
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={streamData} stackOffset="silhouette" margin={{ left: -20, right: 8, top: 8 }}>
            <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" tickMargin={8} />
            <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" />
            <Tooltip />
            <Legend />
            {chatKeys.map((k, i) => (
              <Area
                key={k}
                type="monotone"
                dataKey={k}
                stackId="1"
                stroke={COLORS[i % COLORS.length]}
                fill={COLORS[i % COLORS.length]}
                fillOpacity={0.7}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </ChartCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <SplitPie title="Conversation location" subtitle="App vs Chat" rows={data?.conversation_locations ?? []} />
        <SplitPie title="Chat types" subtitle="Work / Web / Temporary" rows={data?.chat_types ?? []} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <LocBar title="Top Teams locations" rows={data?.teams_locations ?? []} />
        <LocBar title="Top file locations" rows={data?.file_locations ?? []} />
      </div>
    </div>
  );
}

function SplitPie({ title, subtitle, rows }: { title: string; subtitle: string; rows: NamedCount[] }) {
  const d = rows.map((r) => ({ name: r.name ?? "Unknown", value: r.prompts }));
  return (
    <ChartCard title={title} subtitle={subtitle}>
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie data={d} dataKey="value" nameKey="name" outerRadius={90}>
            {d.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Legend />
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}

function LocBar({ title, rows }: { title: string; rows: NamedCount[] }) {
  const d = rows.map((r) => ({ name: r.name ?? "—", prompts: r.prompts }));
  return (
    <ChartCard title={title} subtitle="Prompts">
      {d.length === 0 ? (
        <div className="py-10 text-center text-sm text-slate-400">No data.</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={d} layout="vertical" margin={{ left: 10, right: 12, top: 4 }}>
            <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
            <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} stroke="#94a3b8" width={140} />
            <Tooltip />
            <Bar dataKey="prompts" fill="#2f5ae0" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </ChartCard>
  );
}
