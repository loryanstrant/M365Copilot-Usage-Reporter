import { useMemo } from "react";
import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AppDailyPoint } from "../api/types";
import { metricLabel, type Metric } from "../filters/FiltersContext";
import { appLogoSrc } from "./AppLabel";
import ChartTooltip from "./ChartTooltip";

// Per-app small multiples: one mini area chart per product surface showing
// prompts and conversations over time, each with a dashed linear trendline.
// Data is aggregated by month so the sparklines stay readable, and every panel
// shares the same month axis so they can be compared at a glance.

const PROMPT_STROKE = "#2f5ae0";
const PROMPT_FILL = "rgba(47,90,224,0.16)";
const CONV_STROKE = "#38bdf8";
const CONV_FILL = "rgba(56,189,248,0.22)";
const TREND_STROKE = "#64748b";

interface MonthRow {
  month: string;
  prompts: number;
  conversations: number;
  trend: number;
}

interface AppPanel {
  app: string;
  total: number;
  data: MonthRow[];
}

function monthKey(iso: string): string {
  return iso.slice(0, 7); // YYYY-MM
}

function monthLabel(key: string): string {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
    month: "short",
    year: "2-digit",
  });
}

// Every YYYY-MM key from min..max inclusive so all panels share one axis.
function monthRange(minKey: string, maxKey: string): string[] {
  const [y0, m0] = minKey.split("-").map(Number);
  const [y1, m1] = maxKey.split("-").map(Number);
  const out: string[] = [];
  let y = y0;
  let m = m0;
  while (y < y1 || (y === y1 && m <= m1)) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

// Least-squares linear trend over the values, clamped to >= 0.
function trendline(values: number[]): number[] {
  const n = values.length;
  if (n < 2) return values.slice();
  const xs = values.map((_, i) => i);
  const xbar = xs.reduce((a, b) => a + b, 0) / n;
  const ybar = values.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - xbar) * (values[i] - ybar);
    den += (xs[i] - xbar) ** 2;
  }
  const slope = den === 0 ? 0 : num / den;
  const intercept = ybar - slope * xbar;
  return xs.map((x) => Math.max(0, intercept + slope * x));
}

export default function AppTrendGrid({
  rows,
  metric,
  maxApps = 15,
}: {
  rows: AppDailyPoint[];
  metric: Metric;
  maxApps?: number;
}) {
  const panels = useMemo<AppPanel[]>(() => {
    if (rows.length === 0) return [];
    const allMonths = rows.map((r) => monthKey(r.date)).sort();
    const months = monthRange(allMonths[0], allMonths[allMonths.length - 1]);

    const byApp = new Map<string, Map<string, { p: number; c: number }>>();
    for (const r of rows) {
      const app = r.app_name ?? "Unknown";
      const mk = monthKey(r.date);
      const m = byApp.get(app) ?? new Map<string, { p: number; c: number }>();
      const cur = m.get(mk) ?? { p: 0, c: 0 };
      cur.p += r.prompts;
      cur.c += r.conversations;
      m.set(mk, cur);
      byApp.set(app, m);
    }

    const result: AppPanel[] = [];
    for (const [app, m] of byApp.entries()) {
      const prompts = months.map((mk) => m.get(mk)?.p ?? 0);
      const conversations = months.map((mk) => m.get(mk)?.c ?? 0);
      const metricVals = metric === "prompts" ? prompts : conversations;
      const trend = trendline(metricVals);
      const data: MonthRow[] = months.map((mk, i) => ({
        month: monthLabel(mk),
        prompts: prompts[i],
        conversations: conversations[i],
        trend: Math.round(trend[i] * 10) / 10,
      }));
      const total = metricVals.reduce((a, b) => a + b, 0);
      result.push({ app, total, data });
    }
    result.sort((a, b) => b.total - a.total);
    return result.slice(0, maxApps);
  }, [rows, metric, maxApps]);

  if (panels.length === 0) {
    return <div className="py-16 text-center text-sm text-slate-400">No data.</div>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {panels.map((panel) => {
        const src = appLogoSrc(panel.app);
        return (
          <div
            key={panel.app}
            className="rounded-lg border border-slate-100 p-3 dark:border-slate-700"
          >
            <div className="mb-1 flex items-center gap-2">
              {src ? (
                <img
                  src={src}
                  alt=""
                  aria-hidden="true"
                  className="h-4 w-4 shrink-0 object-contain"
                  loading="lazy"
                />
              ) : (
                <span className="h-4 w-4 shrink-0" aria-hidden="true" />
              )}
              <span className="truncate text-xs font-semibold text-slate-700 dark:text-slate-200">
                {panel.app}
              </span>
              <span className="ml-auto shrink-0 tabular-nums text-[11px] text-slate-400">
                {panel.total.toLocaleString()}
              </span>
            </div>
            <ResponsiveContainer width="100%" height={110}>
              <ComposedChart data={panel.data} margin={{ left: 0, right: 4, top: 4, bottom: 0 }}>
                <XAxis dataKey="month" hide />
                <YAxis hide />
                <Tooltip content={<ChartTooltip />} />
                <Area
                  type="monotone"
                  dataKey="conversations"
                  name="Conversations"
                  stroke={CONV_STROKE}
                  strokeWidth={1.5}
                  fill={CONV_FILL}
                />
                <Area
                  type="monotone"
                  dataKey="prompts"
                  name="Prompts"
                  stroke={PROMPT_STROKE}
                  strokeWidth={1.5}
                  fill={PROMPT_FILL}
                />
                <Line
                  type="linear"
                  dataKey="trend"
                  name={`${metricLabel(metric)} trend`}
                  stroke={TREND_STROKE}
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  dot={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        );
      })}
    </div>
  );
}
