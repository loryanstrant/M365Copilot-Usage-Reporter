import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../api/client";
import type {
  AppConfig,
  BackfillProgress,
  IngestRunResult,
  StatusResult,
  TestConnectionResult,
} from "../api/types";

const DEFAULT_SKU = "639dec6b-bb19-468b-871c-c5c441c4b0cb";

interface Banner {
  kind: "ok" | "error" | "info";
  text: string;
}

function bannerClass(kind: Banner["kind"]): string {
  return {
    ok: "bg-green-50 text-green-700",
    error: "bg-red-50 text-red-700",
    info: "bg-brand-50 text-brand-700",
  }[kind];
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);
  const [test, setTest] = useState<TestConnectionResult | null>(null);
  const [status, setStatus] = useState<StatusResult | null>(null);

  const [tenantId, setTenantId] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [hasSecret, setHasSecret] = useState(false);
  const [skuIds, setSkuIds] = useState(DEFAULT_SKU);
  const [backfillDays, setBackfillDays] = useState(30);
  const [scheduleCron, setScheduleCron] = useState("");
  const [groupId, setGroupId] = useState("");

  const [backfillLookback, setBackfillLookback] = useState(90);
  const [backfill, setBackfill] = useState<BackfillProgress | null>(null);

  async function refreshBackfill() {
    try {
      setBackfill(await api<BackfillProgress>("/admin/backfill/progress"));
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    refreshBackfill();
    const timer = setInterval(refreshBackfill, 3000);
    return () => clearInterval(timer);
  }, []);

  async function onRunBackfill() {
    setBanner(null);
    try {
      const res = await api<IngestRunResult>(
        `/admin/backfill/run?lookback_days=${backfillLookback}`,
        { method: "POST" },
      );
      setBanner({ kind: "info", text: res.detail });
      await refreshBackfill();
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Backfill failed to start",
      });
    }
  }

  async function onCancelBackfill() {
    try {
      await api<IngestRunResult>("/admin/backfill/cancel", { method: "POST" });
      await refreshBackfill();
    } catch {
      /* ignore */
    }
  }

  function applyConfig(cfg: AppConfig) {
    setTenantId(cfg.tenant_id ?? "");
    setClientId(cfg.client_id ?? "");
    setHasSecret(cfg.has_client_secret);
    setSkuIds((cfg.copilot_sku_ids ?? []).join(", ") || DEFAULT_SKU);
    setBackfillDays(cfg.backfill_days ?? 30);
    setScheduleCron(cfg.schedule_cron ?? "");
    setGroupId(cfg.report_access_group_id ?? "");
  }

  async function refreshStatus() {
    try {
      setStatus(await api<StatusResult>("/admin/status"));
    } catch {
      /* ignore transient status errors */
    }
  }

  useEffect(() => {
    (async () => {
      try {
        applyConfig(await api<AppConfig>("/admin/config"));
        await refreshStatus();
      } catch (err) {
        setBanner({
          kind: "error",
          text: err instanceof ApiError ? err.message : "Failed to load settings",
        });
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setBanner(null);
    try {
      const payload: Record<string, unknown> = {
        tenant_id: tenantId,
        client_id: clientId,
        copilot_sku_ids: skuIds
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        backfill_days: backfillDays,
        schedule_cron: scheduleCron,
        report_access_group_id: groupId,
      };
      if (clientSecret) payload.client_secret = clientSecret;
      const cfg = await api<AppConfig>("/admin/config", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      applyConfig(cfg);
      setClientSecret("");
      setBanner({ kind: "ok", text: "Settings saved." });
      await refreshStatus();
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Save failed",
      });
    } finally {
      setSaving(false);
    }
  }

  async function onTest() {
    setTesting(true);
    setTest(null);
    setBanner(null);
    try {
      const result = await api<TestConnectionResult>("/admin/test-connection", {
        method: "POST",
      });
      setTest(result);
      setBanner(
        result.ok
          ? { kind: "ok", text: "Connection successful." }
          : { kind: "error", text: result.detail ?? "Connection failed." },
      );
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Test failed",
      });
    } finally {
      setTesting(false);
    }
  }

  async function onRunIngest() {
    setIngesting(true);
    setBanner(null);
    try {
      const res = await api<IngestRunResult>("/admin/ingest/run", { method: "POST" });
      setBanner({ kind: "info", text: res.detail });
      // Poll status a handful of times so the counters move without a refresh.
      let ticks = 0;
      const timer = setInterval(async () => {
        ticks += 1;
        await refreshStatus();
        if (ticks >= 20) clearInterval(timer);
      }, 3000);
    } catch (err) {
      setBanner({
        kind: "error",
        text: err instanceof ApiError ? err.message : "Ingest failed to start",
      });
    } finally {
      setIngesting(false);
    }
  }

  if (loading) {
    return <div className="text-slate-500">Loading settings…</div>;
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Settings</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Connect Microsoft Graph and run ingestion. The client secret is stored
          encrypted and never shown again.
        </p>
      </div>

      {banner && (
        <div className={`rounded-lg px-4 py-3 text-sm ${bannerClass(banner.kind)}`}>
          {banner.text}
        </div>
      )}

      <div className="grid gap-8 lg:grid-cols-3">
        <form
          onSubmit={onSave}
          className="card space-y-5 p-6 lg:col-span-2"
        >
          <h2 className="text-lg font-semibold">Microsoft Graph</h2>

          <Field label="Tenant ID">
            <input
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className={inputClass}
            />
          </Field>

          <Field label="Client ID (application ID)">
            <input
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              placeholder="00000000-0000-0000-0000-000000000000"
              className={inputClass}
            />
          </Field>

          <Field
            label="Client secret"
            hint={
              hasSecret
                ? "A secret is stored. Leave blank to keep it, or enter a new value to replace."
                : "Enter the client secret value from your app registration."
            }
          >
            <input
              type="password"
              value={clientSecret}
              onChange={(e) => setClientSecret(e.target.value)}
              placeholder={hasSecret ? "•••••••• (unchanged)" : "Enter secret value"}
              className={inputClass}
            />
          </Field>

          <Field
            label="Copilot SKU IDs"
            hint="Comma-separated. Defaults to the Microsoft 365 Copilot SKU."
          >
            <input
              value={skuIds}
              onChange={(e) => setSkuIds(e.target.value)}
              className={inputClass}
            />
          </Field>

          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Backfill days" hint="Lookback window on first run.">
              <input
                type="number"
                min={1}
                max={3650}
                value={backfillDays}
                onChange={(e) => setBackfillDays(Number(e.target.value))}
                className={inputClass}
              />
            </Field>
            <Field label="Schedule (cron)" hint="Optional. Worker default: 0 2 * * *">
              <input
                value={scheduleCron}
                onChange={(e) => setScheduleCron(e.target.value)}
                placeholder="0 2 * * *"
                className={inputClass}
              />
            </Field>
          </div>

          <Field
            label="Report access group ID"
            hint="Optional Entra security group whose members may view the report."
          >
            <input
              value={groupId}
              onChange={(e) => setGroupId(e.target.value)}
              className={inputClass}
            />
          </Field>

          <div className="flex flex-wrap gap-3 pt-2">
            <button
              type="submit"
              disabled={saving}
              className="btn-primary"
            >
              {saving ? "Saving…" : "Save settings"}
            </button>
            <button
              type="button"
              onClick={onTest}
              disabled={testing}
              className="btn-secondary"
            >
              {testing ? "Testing…" : "Test connection"}
            </button>
            <button
              type="button"
              onClick={onRunIngest}
              disabled={ingesting}
              className="rounded-lg border border-brand-300 bg-brand-50 px-4 py-2 text-sm font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60"
            >
              {ingesting ? "Starting…" : "Run ingest now"}
            </button>
          </div>
        </form>

        <div className="space-y-6">
          {test && (
            <div className="card p-6">
              <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
                Connection test
              </h3>
              <ul className="space-y-2 text-sm">
                <CheckRow ok={test.token_acquired} label="Token acquired" />
                <CheckRow ok={test.subscribed_skus} label="Read subscribed SKUs" />
                <CheckRow ok={test.directory_read} label="Directory read" />
              </ul>
              {test.copilot_licensed_users != null && (
                <div className="mt-3 text-sm text-slate-600">
                  Copilot-licensed users:{" "}
                  <span className="font-semibold">{test.copilot_licensed_users}</span>
                </div>
              )}
              {test.detail && (
                <div className="mt-3 rounded bg-slate-50 p-2 text-xs text-slate-500">
                  {test.detail}
                </div>
              )}
            </div>
          )}

          <div className="card p-6">
            <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">Data status</h3>
            <dl className="space-y-2 text-sm">
              <StatRow label="Configured" value={status?.configured ? "Yes" : "No"} />
              <StatRow label="Prompts" value={status?.prompts ?? 0} />
              <StatRow label="Conversations" value={status?.conversations ?? 0} />
              <StatRow label="Licensed users" value={status?.licensed_users ?? 0} />
              <StatRow label="Directory users" value={status?.entra_users ?? 0} />
            </dl>
            {status?.last_run && (
              <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
                Last run: <span className="font-medium">{status.last_run.job_name}</span>{" "}
                — {status.last_run.status}
              </div>
            )}
          </div>

          <div className="card p-6">
            <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
              Historical backfill
            </h3>
            <p className="mb-3 text-xs text-slate-400">
              Pull older history in resumable time windows. Safe to re-run.
            </p>
            <div className="flex items-end gap-3">
              <div className="flex-1">
                <label className="mb-1 block text-xs font-medium text-slate-600">
                  Lookback days
                </label>
                <input
                  type="number"
                  min={1}
                  max={3650}
                  value={backfillLookback}
                  onChange={(e) => setBackfillLookback(Number(e.target.value))}
                  className={inputClass}
                />
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={onRunBackfill}
                disabled={backfill?.status === "running"}
                className="rounded-lg border border-brand-300 bg-brand-50 px-3 py-1.5 text-sm font-semibold text-brand-700 hover:bg-brand-100 disabled:opacity-60 dark:border-brand-700 dark:bg-brand-700/20 dark:text-brand-500 dark:hover:bg-brand-700/30"
              >
                Run backfill
              </button>
              {backfill?.status === "running" && (
                <button
                  type="button"
                  onClick={onCancelBackfill}
                  className="btn-secondary px-3 py-1.5"
                >
                  Cancel
                </button>
              )}
            </div>
            {backfill && backfill.status !== "idle" && (
              <div className="mt-4 space-y-2 border-t border-slate-100 pt-3 text-xs text-slate-500">
                <div className="flex justify-between">
                  <span>Status</span>
                  <span className="font-semibold text-slate-700">{backfill.status}</span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-brand-500 transition-all"
                    style={{
                      width: `${
                        backfill.users_total
                          ? Math.round((backfill.users_done / backfill.users_total) * 100)
                          : 0
                      }%`,
                    }}
                  />
                </div>
                <div className="flex justify-between">
                  <span>
                    {backfill.users_done}/{backfill.users_total} users
                  </span>
                  <span>{backfill.prompts} prompts</span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

const inputClass = "input";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">{label}</label>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">{hint}</p>}
    </div>
  );
}

function CheckRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2">
      <span className={ok ? "text-green-600" : "text-slate-300"}>{ok ? "✓" : "○"}</span>
      <span className="text-slate-600">{label}</span>
    </li>
  );
}

function StatRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-semibold tabular-nums text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  );
}
