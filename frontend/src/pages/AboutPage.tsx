import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Freshness } from "../api/types";
import KpiCard from "../components/KpiCard";

function fmt(value: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function fmtDay(value: string | null): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString();
  } catch {
    return value;
  }
}

export default function AboutPage() {
  const [fresh, setFresh] = useState<Freshness | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setFresh(await api<Freshness>("/metrics/freshness"));
      } catch {
        /* ignore */
      }
    })();
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">About</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Data freshness and methodology.
        </p>
      </div>

      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Prompts" value={fresh?.prompts ?? "—"} />
        <KpiCard label="Conversations" value={fresh?.conversations ?? "—"} />
        <KpiCard label="Licensed users" value={fresh?.licensed_users ?? "—"} />
        <KpiCard label="Directory users" value={fresh?.directory_users ?? "—"} />
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Data freshness
        </h3>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <Row label="Earliest data" value={fmtDay(fresh?.earliest_prompt ?? null)} />
          <Row label="Most recent data" value={fmtDay(fresh?.latest_prompt ?? null)} />
          <Row
            label="Last refreshed"
            value={fresh?.last_run ? fmt(fresh.last_run.finished_at) : "—"}
          />
          <Row
            label="Refresh status"
            value={fresh?.last_run?.status ?? "No refresh yet"}
          />
        </dl>
      </div>

      <div className="card p-6 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Methodology
        </h3>
        <ul className="list-inside list-disc space-y-1">
          <li>
            <span className="font-medium">Conversations</span> are distinct Copilot
            sessions; <span className="font-medium">Prompts</span> are individual
            interactions within them.
          </li>
          <li>Active users are those with at least one prompt in the last 30 days.</li>
          <li>
            Data is sourced from Microsoft Graph enterprise interaction history and
            refreshed on a schedule.
          </li>
        </ul>
      </div>

      <div className="card flex items-center gap-4 p-6">
        <img
          src="/loryan-cyborg.png"
          alt="Loryan Strant"
          className="h-16 w-16 rounded-full object-cover ring-2 ring-brand-500/30"
        />
        <div>
          <div className="text-xs uppercase tracking-wide text-slate-400">
            Created by
          </div>
          <a
            href="https://www.loryanstrant.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-lg font-semibold text-brand-600 hover:underline dark:text-brand-500"
          >
            Loryan Strant
          </a>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 pb-2 dark:border-slate-700">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-medium text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  );
}
