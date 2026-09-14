import { useState } from "react";
import { api, ApiError } from "../api/client";

interface Result {
  status: string;
  detail: string;
}

/**
 * Explicit demo-data controls. Nothing is ever seeded on deploy or wiped when
 * configuration is saved — loading and clearing are both deliberate actions, so
 * a mistyped credential can never leave someone staring at an empty dashboard.
 */
export default function DemoDataCard() {
  const [busy, setBusy] = useState<"seed" | "clear" | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function call(kind: "seed" | "clear") {
    const path = kind === "seed" ? "/admin/seed-demo" : "/admin/clear-demo";
    const confirmText =
      kind === "seed"
        ? "Load demo data? This replaces any data currently in the reporting tables."
        : "Clear demo data? This removes all rows from the reporting tables.";
    if (!window.confirm(confirmText)) return;

    setBusy(kind);
    setError(null);
    setResult(null);
    try {
      setResult(await api<Result>(path, { method: "POST" }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Request failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="card p-6">
      <h3 className="mb-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
        Demo data
      </h3>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
        Load plausible fictional data to explore the dashboards before connecting a
        tenant. Clear it before your first live run so demo numbers can't be mistaken for
        real ones. Neither action touches your credentials or sign-in accounts.
      </p>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => call("seed")}
          disabled={busy !== null}
          className="btn-secondary"
        >
          {busy === "seed" ? "Loading…" : "Load demo data"}
        </button>
        <button
          type="button"
          onClick={() => call("clear")}
          disabled={busy !== null}
          className="btn-secondary"
        >
          {busy === "clear" ? "Clearing…" : "Clear demo data"}
        </button>
      </div>

      {result && (
        <div className="mt-4 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300">
          {result.detail}
        </div>
      )}
      {error && (
        <div className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          {error}
        </div>
      )}
    </div>
  );
}
