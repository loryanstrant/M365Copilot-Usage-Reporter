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
    chart.current.setOption(
      {
        textStyle: { color: axisColor, fontFamily: "inherit" },
        ...option,
      },
      true,
    );
  }, [option, theme]);

  return <div ref={ref} style={{ width: "100%", height }} />;
}
