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

// A gradient id for a series index (defs live in <SvgDefs/>, rendered once).
export function gradId(i: number): string {
  return `grad-${i % CHART_COLORS.length}`;
}

export function barGradId(i: number): string {
  return `bargrad-${i % CHART_COLORS.length}`;
}
