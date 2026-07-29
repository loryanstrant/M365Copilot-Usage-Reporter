import { CHART_COLORS, barGradId, gradId } from "./chartTheme";

/**
 * A single hidden SVG holding every chart gradient + shadow filter, rendered
 * once at the app root. SVG paint references (`url(#id)`) resolve document-wide,
 * so any Recharts surface can use these without embedding its own <defs> (a
 * custom <defs> component gets filtered out by Recharts — this avoids that).
 */
export default function SvgDefs() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
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
            <stop offset="100%" stopColor={c} stopOpacity={0.5} />
          </linearGradient>
        ))}
      </defs>
    </svg>
  );
}
