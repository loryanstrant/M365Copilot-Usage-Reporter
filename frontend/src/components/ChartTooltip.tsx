import type { TooltipProps } from "recharts";

/**
 * A single tooltip style shared by every Recharts surface. Uses Tailwind classes
 * so it switches automatically between light and dark, with one consistent font,
 * size and colour (the built-in Recharts tooltip renders a fixed white box with
 * inconsistent text colours that are unreadable in dark mode).
 */
export default function ChartTooltip({
  active,
  payload,
  label,
}: TooltipProps<number | string, string>) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-800">
      {label !== undefined && label !== "" && (
        <div className="mb-1 font-medium text-slate-500 dark:text-slate-400">{label}</div>
      )}
      <div className="space-y-1">
        {payload.map((entry, i) => {
          const raw =
            (entry.color as string) ||
            (entry.payload && (entry.payload.fill || entry.payload.color)) ||
            "#3b6ef5";
          // Bars can be filled with a gradient url(#...); use a solid dot instead.
          const dot = typeof raw === "string" && raw.startsWith("url(") ? "#3b6ef5" : raw;
          const value =
            typeof entry.value === "number" ? entry.value.toLocaleString() : entry.value;
          return (
            <div
              key={i}
              className="flex items-center gap-2 text-slate-700 dark:text-slate-200"
            >
              <span
                className="inline-block h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: dot }}
              />
              {entry.name !== undefined && (
                <span className="text-slate-500 dark:text-slate-400">{entry.name}</span>
              )}
              <span className="ml-auto pl-3 font-semibold tabular-nums">{value}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
