import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
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
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={points} margin={{ left: -20, right: 8, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" opacity={0.4} />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="#94a3b8" />
              <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" allowDecimals={false} />
              <Tooltip />
              <Line type="monotone" dataKey="enabled" stroke="#2f5ae0" strokeWidth={2} />
              <Line type="monotone" dataKey="allocated" stroke="#f59e0b" strokeWidth={2} />
              <Line type="monotone" dataKey="available" stroke="#10b981" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </ChartCard>
    </div>
  );
}
