import { useState } from "react";
import { APP_DISPLAY_NAME, REQUIRED_PERMISSIONS, SETUP_SCRIPT } from "../lib/setup";

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          /* clipboard blocked — user can select manually */
        }
      }}
      className="shrink-0 rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
    >
      {copied ? "Copied ✓" : label}
    </button>
  );
}

export default function SetupGuidePage() {
  return (
    <div className="max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold">Setup guide</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Everything needed to connect this report to your tenant, and what to check when
          something looks wrong.
        </p>
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Before you start
        </h3>
        <ul className="list-inside list-disc space-y-1.5 text-sm text-slate-600 dark:text-slate-300">
          <li>
            A <span className="font-medium">Global Administrator</span> (or Privileged Role
            Administrator plus Application Administrator) to create the app registration and
            grant admin consent.
          </li>
          <li>Microsoft 365 Copilot licences assigned in the tenant.</li>
          <li>PowerShell 7 with the Microsoft Graph SDK, if you want to script it.</li>
        </ul>
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Required Graph permissions
        </h3>
        <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
          These are <span className="font-medium">application</span> permissions, not
          delegated. Both need admin consent before the first run will return data.
        </p>
        <div className="space-y-3">
          {REQUIRED_PERMISSIONS.map((p) => (
            <div
              key={p.value}
              className="rounded-md bg-slate-50 px-3 py-2.5 dark:bg-slate-900"
            >
              <div className="flex items-center justify-between gap-2">
                <code className="text-xs font-semibold text-slate-700 dark:text-slate-200">
                  {p.value}
                </code>
                <CopyButton text={p.value} />
              </div>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{p.why}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Create the app registration manually
        </h3>
        <ol className="list-inside list-decimal space-y-2 text-sm text-slate-600 dark:text-slate-300">
          <li>
            Open{" "}
            <a
              href="https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade/quickStartType~/null/isMSAApp~/false"
              target="_blank"
              rel="noreferrer"
              className="font-medium text-brand-600 underline dark:text-brand-500"
            >
              Entra → App registrations → New registration
            </a>
            , name it <span className="font-medium">{APP_DISPLAY_NAME}</span>, keep the
            defaults and select <span className="font-medium">Register</span>.
          </li>
          <li>
            Under <span className="font-medium">API permissions</span>, add both Graph
            application permissions above, then choose{" "}
            <span className="font-medium">Grant admin consent</span>.
          </li>
          <li>
            Under <span className="font-medium">Certificates &amp; secrets</span>, create a
            client secret and copy its <span className="font-medium">Value</span> straight
            away — it is shown only once.
          </li>
          <li>
            From <span className="font-medium">Overview</span>, copy the{" "}
            <span className="font-medium">Directory (tenant) ID</span> and{" "}
            <span className="font-medium">Application (client) ID</span>.
          </li>
          <li>
            Paste all three into <span className="font-medium">Settings</span>, then{" "}
            <span className="font-medium">Save</span> and{" "}
            <span className="font-medium">Test connection</span>.
          </li>
        </ol>
      </div>

      <div className="card p-6">
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">
            Or script it
          </h3>
          <CopyButton text={SETUP_SCRIPT} label="Copy script" />
        </div>
        <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">
          This does the whole registration in one pass — resolves the permission IDs by
          name, creates the app, grants consent, and prints the three values you need.
        </p>
        <pre className="max-h-96 overflow-auto rounded-md bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
          <code>{SETUP_SCRIPT}</code>
        </pre>
      </div>

      <div className="card p-6">
        <h3 className="mb-3 text-sm font-semibold text-slate-700 dark:text-slate-200">
          Troubleshooting
        </h3>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="font-medium text-slate-800 dark:text-slate-100">
              Test connection succeeds but no data appears
            </dt>
            <dd className="text-slate-600 dark:text-slate-300">
              Graph only returns interaction history for licensed users who have actually
              used Copilot. Run again after a day of activity, or load demo data from
              Settings to check the dashboards render.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-800 dark:text-slate-100">
              403 or &quot;Insufficient privileges&quot;
            </dt>
            <dd className="text-slate-600 dark:text-slate-300">
              Admin consent was not granted, or it was granted for delegated rather than
              application permissions. Re-check the API permissions blade — both entries
              should show a green tick under Status.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-800 dark:text-slate-100">
              Authentication fails after a while
            </dt>
            <dd className="text-slate-600 dark:text-slate-300">
              Client secrets expire. Create a new one and update it in Settings.
            </dd>
          </div>
          <div>
            <dt className="font-medium text-slate-800 dark:text-slate-100">
              Where do I see what happened on the last run?
            </dt>
            <dd className="text-slate-600 dark:text-slate-300">
              Settings shows run history with status and any error detail, and the About
              page shows data freshness.
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
