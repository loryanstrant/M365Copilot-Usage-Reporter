import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { LicensePoint } from "../api/types";
import ChartCard from "../components/ChartCard";
import KpiCard from "../components/KpiCard";

export default function LicensesPage() {
  const [points, setPoints] = useState<LicensePoint[]>([]);

  useEffect(() => {
    (async () => {
      try {
        setPoints(await api<LicensePoint[]>("/metrics/licenses"));
      } catch {
        /* ignore */
      }
    })();
  }, []);

  const latest = points.length ? points[points.length - 1] : null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Licenses</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Copilot license allocation over time.
        </p>
      </div>

      <div className="grid gap-5 sm:grid-cols-3">
        <KpiCard label="Enabled" value={latest?.enabled ?? "—"} />
        <KpiCard label="Allocated" value={latest?.allocated ?? "—"} />
        <KpiCard label="Available" value={latest?.available ?? "—"} />
      </div>

      <ChartCard title="Licenses over time" subtitle="Enabled vs allocated vs available">
        {points.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-400">
            No license history yet.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={320}>
            <AreaChart data={points} margin={{ left: -20, right: 8, top: 8 }}>
              <defs>
                <linearGradient id="licEnabled" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#2f5ae0" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#2f5ae0" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="licAllocated" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#f59e0b" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="licAvailable" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#10b981" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#10b981" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.35} />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip />
              <Area type="monotone" dataKey="enabled" stroke="#2f5ae0" strokeWidth={2.5} fill="url(#licEnabled)" />
              <Area type="monotone" dataKey="allocated" stroke="#f59e0b" strokeWidth={2.5} fill="url(#licAllocated)" />
              <Area type="monotone" dataKey="available" stroke="#10b981" strokeWidth={2.5} fill="url(#licAvailable)" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </ChartCard>
    </div>
  );
}
