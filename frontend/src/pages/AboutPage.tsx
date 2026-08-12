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
          className="h-16 w-16 rounded-full object-cover"
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
          <div className="mt-1">
            <a
              href="https://github.com/loryanstrant/M365Copilot-Usage-Reporter"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-slate-500 hover:text-brand-600 hover:underline dark:text-slate-400 dark:hover:text-brand-500"
            >
              <svg
                viewBox="0 0 16 16"
                aria-hidden="true"
                className="h-4 w-4 fill-current"
              >
                <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
              </svg>
              View on GitHub
            </a>
          </div>
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
