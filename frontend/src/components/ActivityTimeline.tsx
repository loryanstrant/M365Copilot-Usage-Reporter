import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import ChartTooltip from "./ChartTooltip";
import { CHART_COLORS } from "./chartTheme";

export interface TimelinePoint {
  /** ISO date (YYYY-MM-DD), as the metrics endpoints return it. */
  date: string | null;
  [measure: string]: string | number | null;
}

export interface TimelineSeries {
  key: string;
  label: string;
  color?: string;
}

/** Every calendar day between the first and last point, zero-filled. */
function fillDays(
  points: TimelinePoint[],
  series: TimelineSeries[],
): TimelinePoint[] {
  const dated = points.filter((p) => p.date);
  if (dated.length === 0) return [];
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const byDate = new Map(dated.map((p) => [p.date as string, p]));
  const start = new Date(`${dated[0].date}T00:00:00Z`);
  const end = new Date(`${dated[dated.length - 1].date}T00:00:00Z`);

  const out: TimelinePoint[] = [];
  for (let d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const key = iso(d);
    const hit = byDate.get(key);
    if (hit) {
      out.push(hit);
    } else {
      const blank: TimelinePoint = { date: key };
      for (const s of series) blank[s.key] = 0;
      out.push(blank);
    }
  }
  return out;
}

/**
 * Daily bars with a rolling-average line over them.
 *
 * Two deliberate choices:
 *
 * - **Every day in the range gets a slot, including days with nothing.** A
 *   chart that silently skips empty days compresses a fortnight of silence into
 *   nothing, and "I didn't touch it for two weeks" is usually the useful signal
 *   on a personal page.
 * - The trend line is a trailing average, so it never implies knowledge of days
 *   that have not happened yet.
 */
export default function ActivityTimeline({
  points,
  series,
  trendOf,
  trendWindow = 7,
  height = 220,
}: {
  points: TimelinePoint[];
  series: TimelineSeries[];
  /** Which series the trend line averages. Defaults to the first. */
  trendOf?: string;
  trendWindow?: number;
  height?: number;
}) {
  if (points.length === 0) {
    return (
      <p className="text-sm text-slate-500 dark:text-slate-400">
        No activity in this period yet.
      </p>
    );
  }

  const trendKey = trendOf ?? series[0]?.key;

  // The endpoints group by date and therefore return nothing at all for a day
  // with no activity. Rendering those rows as-is would compress a fortnight of
  // silence into a single gridline, so the range is filled in here.
  const filled = fillDays(points, series);

  const data = filled.map((p, i) => {
    const window = filled
      .slice(Math.max(0, i - (trendWindow - 1)), i + 1)
      .map((q) => Number(q[trendKey] ?? 0));
    const avg = window.reduce((a, b) => a + b, 0) / (window.length || 1);
    return { ...p, __trend: Math.round(avg * 10) / 10 };
  });

  const dayLabel = (iso: string) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
          <XAxis
            dataKey="date"
            tickFormatter={dayLabel}
            stroke="#94a3b8"
            fontSize={11}
            minTickGap={24}
          />
          <YAxis stroke="#94a3b8" fontSize={11} allowDecimals={false} />
          <Tooltip
            content={<ChartTooltip />}
            labelFormatter={(v) => dayLabel(String(v))}
          />
          {series.map((s, i) => (
            <Bar
              key={s.key}
              dataKey={s.key}
              name={s.label}
              fill={s.color ?? CHART_COLORS[i % CHART_COLORS.length]}
              radius={[2, 2, 0, 0]}
            />
          ))}
          <Line
            type="monotone"
            dataKey="__trend"
            name={`${trendWindow}-day average`}
            stroke="#64748b"
            strokeWidth={2}
            dot={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
