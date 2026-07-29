// Shared chart styling: a coherent gradient palette + reusable <defs> so every
// Recharts surface gets depth (fills, soft shadows) instead of flat 2D colour.

export const CHART_COLORS = [
  "#3b6ef5", // brand blue
  "#22c55e", // green
  "#f59e0b", // amber
  "#a855f7", // purple
  "#ef4444", // red
  "#06b6d4", // cyan
  "#ec4899", // pink
  "#14b8a6", // teal
];

// A gradient id for a series index (see <ChartGradients/> below).
export function gradId(i: number): string {
  return `grad-${i % CHART_COLORS.length}`;
}

export function barGradId(i: number): string {
  return `bargrad-${i % CHART_COLORS.length}`;
}

/**
 * Drop this once inside any Recharts chart to register vertical area gradients
 * (top colour → transparent) and bar gradients (solid → lighter), plus a soft
 * drop shadow filter, all keyed by series index.
 */
export function ChartGradients() {
  return (
    <defs>
      {CHART_COLORS.map((c, i) => (
        <linearGradient key={`a${i}`} id={gradId(i)} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity={0.45} />
          <stop offset="100%" stopColor={c} stopOpacity={0.02} />
        </linearGradient>
      ))}
      {CHART_COLORS.map((c, i) => (
        <linearGradient key={`b${i}`} id={barGradId(i)} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={c} stopOpacity={1} />
          <stop offset="100%" stopColor={c} stopOpacity={0.55} />
        </linearGradient>
      ))}
      <filter id="chartShadow" x="-20%" y="-20%" width="140%" height="140%">
        <feDropShadow dx="0" dy="2" stdDeviation="3" floodColor="#0f172a" floodOpacity="0.18" />
      </filter>
    </defs>
  );
}
