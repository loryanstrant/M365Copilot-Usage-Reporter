import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type {
  BackfillCoverage,
  BackfillProgress,
  BackfillRun,
  IngestRunResult,
} from "../api/types";

function fmtDate(v: string | null): string {
  if (!v) return "—";
  try {
    return new Date(v).toLocaleString();
  } catch {
    return v;
  }
}

const LOOKBACK_OPTIONS = [
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 180, label: "6 months" },
  { days: 365, label: "1 year" },
  { days: 730, label: "2 years" },
];

export default function BackfillPage() {
  const [coverage, setCoverage] = useState<BackfillCoverage | null>(null);
  const [progress, setProgress] = useState<BackfillProgress | null>(null);
  const [history, setHistory] = useState<BackfillRun[]>([]);
  const [lookback, setLookback] = useState(365);
  const [confirming, setConfirming] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);

  async function refresh() {
    try {
      const [c, p, h] = await Promise.all([
        api<BackfillCoverage>("/admin/backfill/coverage"),
        api<BackfillProgress>("/admin/backfill/progress"),
        api<BackfillRun[]>("/admin/backfill/history"),
      ]);
      setCoverage(c);
      setProgress(p);
      setHistory(h);
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  const running = progress?.status === "running";
  // Discourage re-running when we already cover at least as far back as asked.
  const alreadyCovered =
    (coverage?.lookback_days ?? 0) >= lookback && (coverage?.total_prompts ?? 0) > 0;

  async function start() {
    setBanner(null);
    setConfirming(false);
    try {
      const res = await api<IngestRunResult>(
        `/admin/backfill/run?lookback_days=${lookback}`,
        { method: "POST" },
      );
      setBanner(res.detail);
      await refresh();
    } catch (err) {
      setBanner(err instanceof ApiError ? err.message : "Backfill failed to start");
    }
  }

  function onRunClick() {
    if (alreadyCovered && !confirming) {
      setConfirming(true);
      return;
    }
    start();
  }

  async function cancel() {
    try {
      await api<IngestRunResult>("/admin/backfill/cancel", { method: "POST" });
      await refresh();
    } catch {
      /* ignore */
    }
  }

  const pctUsers = progress?.users_total
    ? Math.round((progress.users_done / progress.users_total) * 100)
    : 0;

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Historical backfill</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Pull older Copilot history in one intelligent, resumable pass. Normally a
            one-time operation — the recurring refresh keeps things current afterwards.
          </p>
        </div>
        <Link to="/settings" className="btn-secondary whitespace-nowrap">
          ← Back to settings
        </Link>
      </div>

      {banner && (
        <div className="rounded-lg bg-brand-50 px-4 py-3 text-sm text-brand-700 dark:bg-brand-900/20 dark:text-brand-400">
          {banner}
        </div>
      )}

      {/* Coverage summary */}
      <div className="grid gap-5 sm:grid-cols-3">
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-400">History stored</div>
          <div className="mt-1 text-3xl font-bold tabular-nums text-slate-900 dark:text-white">
            {coverage?.lookback_days != null ? `${coverage.lookback_days}d` : "—"}
          </div>
          <div className="mt-1 text-xs text-slate-500">
            back to {coverage?.earliest_prompt ?? coverage?.earliest_covered ?? "—"}
          </div>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-400">Prompts stored</div>
          <div className="mt-1 text-3xl font-bold tabular-nums text-slate-900 dark:text-white">
            {coverage?.total_prompts?.toLocaleString() ?? "—"}
          </div>
        </div>
        <div className="card p-5">
          <div className="text-xs uppercase tracking-wide text-slate-400">Last backfill</div>
          <div className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">
            {coverage?.has_run ? fmtDate(coverage.last_run_at) : "Never run"}
          </div>
        </div>
      </div>

      {/* Run controls */}
      <div className="card space-y-4 p-6">
        <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Run a backfill
        </h3>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">
              How far back
            </label>
            <select
              value={lookback}
              onChange={(e) => {
                setLookback(Number(e.target.value));
                setConfirming(false);
              }}
              className="input w-48"
              disabled={running}
            >
              {LOOKBACK_OPTIONS.map((o) => (
                <option key={o.days} value={o.days}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={onRunClick}
            disabled={running}
            className={
              confirming
                ? "btn-primary bg-amber-600 hover:bg-amber-700"
                : "btn-primary"
            }
          >
            {running
              ? "Running…"
              : confirming
                ? "Yes, run it anyway"
                : "Run backfill"}
          </button>
          {running && (
            <button onClick={cancel} className="btn-secondary">
              Cancel
            </button>
          )}
        </div>

        {alreadyCovered && !running && (
          <div className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
            You already have <strong>{coverage?.lookback_days} days</strong> of history
            stored ({coverage?.total_prompts?.toLocaleString()} prompts). Re-running for{" "}
            {lookback} days will re-scan data you already hold and usually isn't needed —
            the scheduled refresh keeps everything current. Pick a longer range to extend
            further back, or confirm above to proceed anyway.
          </div>
        )}

        {progress && progress.status !== "idle" && (
          <div className="space-y-2 border-t border-slate-100 pt-4 text-sm dark:border-slate-700">
            <div className="flex justify-between">
              <span className="text-slate-500 dark:text-slate-400">Status</span>
              <span className="font-semibold text-slate-700 dark:text-slate-200">
                {progress.status}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
              <div
                className="h-full rounded-full bg-gradient-to-r from-brand-500 to-brand-600 transition-all"
                style={{ width: `${pctUsers}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-slate-500 dark:text-slate-400">
              <span>
                {progress.users_done}/{progress.users_total} users
              </span>
              <span>{progress.prompts.toLocaleString()} prompts</span>
            </div>
          </div>
        )}
      </div>

      {/* History */}
      <div className="card">
        <div className="border-b border-slate-100 px-5 py-4 dark:border-slate-700">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Backfill history
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                {["Started", "Status", "Lookback", "Prompts", "Finished"].map((h) => (
                  <th key={h} className="px-5 py-3 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-6 text-center text-slate-400">
                    No backfill has run yet.
                  </td>
                </tr>
              ) : (
                history.map((r) => (
                  <tr key={r.id} className="border-t border-slate-100 dark:border-slate-700">
                    <td className="px-5 py-3 text-slate-700 dark:text-slate-200">
                      {fmtDate(r.started_at)}
                    </td>
                    <td className="px-5 py-3">
                      <StatusPill status={r.status} />
                    </td>
                    <td className="px-5 py-3 tabular-nums text-slate-600 dark:text-slate-300">
                      {(r.stats?.lookback_days as number) ?? "—"}d
                    </td>
                    <td className="px-5 py-3 tabular-nums text-slate-600 dark:text-slate-300">
                      {((r.stats?.prompts as number) ?? 0).toLocaleString()}
                    </td>
                    <td className="px-5 py-3 text-slate-600 dark:text-slate-300">
                      {fmtDate(r.finished_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const cls =
    {
      completed: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
      running: "bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-400",
      failed: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
      cancelled: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300",
    }[status] ?? "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300";
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>
  );
}
