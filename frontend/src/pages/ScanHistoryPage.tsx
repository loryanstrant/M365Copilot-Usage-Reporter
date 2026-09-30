import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import ChartCard from "../components/ChartCard";
import DataTable, { type Column } from "../components/DataTable";

interface ScanRun {
  id: number;
  kind: string;
  raw_kind: string;
  state: string;
  raw_status: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  error: string | null;
  stats: Record<string, unknown>;
}

/** Shape plus word, never colour alone. */
const STATE: Record<string, { mark: string; word: string }> = {
  succeeded: { mark: "●", word: "Succeeded" },
  running: { mark: "◐", word: "In progress" },
  failed: { mark: "○", word: "Failed" },
  cancelled: { mark: "○", word: "Cancelled" },
};

function fmtWhen(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m < 60 ? `${m}m ${String(s).padStart(2, "0")}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

// The stats blob is keyed by internal table names. Left raw it reads as
// "40 entra users", which is the schema talking rather than the product.
const STAT_LABEL: Record<string, [string, string]> = {
  prompts: ["prompt", "prompts"],
  conversations: ["conversation", "conversations"],
  entra_users: ["directory user", "directory users"],
  licensed_users: ["licensed user", "licensed users"],
  license_counts: ["licence total", "licence totals"],
  copilot_skus: ["Copilot subscription", "Copilot subscriptions"],
  days: ["day", "days"],
};

/** The interesting numbers a run wrote, as a short phrase. */
function fmtStats(stats: Record<string, unknown>): string {
  const parts = Object.entries(stats)
    .filter(([, v]) => typeof v === "number" && v !== 0)
    .map(([k, v]) => {
      const n = Number(v);
      const words = STAT_LABEL[k];
      const word = words
        ? n === 1
          ? words[0]
          : words[1]
        : k.replace(/_/g, " ");
      return `${n.toLocaleString()} ${word}`;
    });
  return parts.length ? parts.join(" · ") : "—";
}

/**
 * Every collection this report has run.
 *
 * job_runs has recorded this since the first release and nothing ever showed
 * it, so "did last night's pull actually work?" had no answer in the UI.
 */
export default function ScanHistoryPage() {
  const [runs, setRuns] = useState<ScanRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const rows = await api<ScanRun[]>("/admin/scan-history");
        if (active) setRuns(rows);
      } catch {
        if (active) setError("We couldn't load the run history just now.");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const columns: Column<ScanRun>[] = useMemo(
    () => [
      {
        key: "started_at",
        header: "Started",
        type: "date",
        accessor: (r) => r.started_at,
        render: (r) => fmtWhen(r.started_at),
      },
      { key: "kind", header: "Kind", accessor: (r) => r.kind },
      {
        key: "state",
        header: "Status",
        accessor: (r) => STATE[r.state]?.word ?? r.raw_status,
        render: (r) => {
          const s = STATE[r.state];
          return (
            <span className="whitespace-nowrap">
              <span aria-hidden>{s ? `${s.mark} ` : ""}</span>
              {s ? s.word : r.raw_status}
            </span>
          );
        },
      },
      {
        key: "duration_seconds",
        header: "Duration",
        type: "number",
        align: "right",
        accessor: (r) => r.duration_seconds,
        render: (r) => fmtDuration(r.duration_seconds),
        filterable: false,
      },
      {
        key: "stats",
        header: "Wrote",
        accessor: (r) => fmtStats(r.stats),
      },
      {
        key: "error",
        header: "Detail",
        accessor: (r) => r.error ?? "",
        render: (r) =>
          r.error ? (
            <span className="text-rose-700 dark:text-rose-400">{r.error}</span>
          ) : (
            <span className="text-slate-400">—</span>
          ),
      },
    ],
    [],
  );

  if (loading) {
    return <div className="text-slate-500 dark:text-slate-400">Loading…</div>;
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
        Scan history
      </h1>
      <p className="mb-5 mt-1 text-sm text-slate-500 dark:text-slate-400">
        Every collection this report has run, newest first.
      </p>

      {error && (
        <div className="card mb-5 p-5 text-sm text-amber-700 dark:text-amber-300">
          {error}
        </div>
      )}

      <ChartCard
        title={`${runs.length.toLocaleString()} ${runs.length === 1 ? "run" : "runs"}`}
        subtitle="Scheduled, manual, user syncs and historical backfills"
        className="px-0"
      >
        <DataTable
          columns={columns}
          rows={runs}
          getRowKey={(r) => r.id}
          initialSort={{ key: "started_at", dir: "desc" }}
          filterable
          maxBodyHeight={620}
          emptyMessage="Nothing has run yet. Open Settings and use Run now, or wait for the next scheduled collection."
        />
      </ChartCard>
    </div>
  );
}
