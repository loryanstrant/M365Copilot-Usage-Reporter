import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { useTheme } from "../theme/ThemeContext";

/**
 * Minimal ECharts wrapper. Re-renders on option/theme change, disposes on
 * unmount, and resizes with its container. Used for the richer visuals
 * (sunburst, radar) that Recharts doesn't cover.
 */
export default function EChart({
  option,
  height = 320,
}: {
  option: echarts.EChartsOption;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    if (!ref.current) return;
    chart.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const onResize = () => chart.current?.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.current?.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chart.current) return;
    const axisColor = theme === "dark" ? "#94a3b8" : "#475569";
    // A single tooltip style matching the Recharts tooltip, theme-aware.
    const tooltipTheme = {
      backgroundColor: theme === "dark" ? "#1e293b" : "#ffffff",
      borderColor: theme === "dark" ? "#334155" : "#e2e8f0",
      borderWidth: 1,
      textStyle: {
        color: theme === "dark" ? "#e2e8f0" : "#334155",
        fontSize: 12,
        fontFamily: "inherit",
      },
      extraCssText: "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.18);",
    };
    const merged: echarts.EChartsOption = {
      textStyle: { color: axisColor, fontFamily: "inherit" },
      ...option,
      tooltip: { ...tooltipTheme, ...(option.tooltip as object) },
    };
    chart.current.setOption(merged, true);
  }, [option, theme]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
