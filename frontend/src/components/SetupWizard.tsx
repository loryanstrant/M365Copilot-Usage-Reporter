import { useState, type ReactNode } from "react";

// A ready-to-run script that creates the app registration, adds the two
// application permissions, grants admin consent, and prints the values to paste
// below. Permission GUIDs are resolved by name at runtime so nothing is
// hard-coded or can drift.
const SETUP_SCRIPT = `# Run in PowerShell 7 with the Microsoft Graph SDK.
# Requires a Global Administrator (or Privileged Role + Application admin).
Install-Module Microsoft.Graph -Scope CurrentUser -Force  # first time only
Connect-MgGraph -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All"

$graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"
$needed  = "AiEnterpriseInteraction.Read.All","Directory.Read.All"
$roles   = $graphSp.AppRoles | Where-Object { $needed -contains $_.Value }

$app = New-MgApplication -DisplayName "M365 Copilot Usage Reporter" -RequiredResourceAccess @{
  ResourceAppId  = "00000003-0000-0000-c000-000000000000"
  ResourceAccess = @($roles | ForEach-Object { @{ Id = $_.Id; Type = "Role" } })
}
$sp = New-MgServicePrincipal -AppId $app.AppId

# Grant admin consent for both application permissions
foreach ($r in $roles) {
  New-MgServicePrincipalAppRoleAssignment -ServicePrincipalId $sp.Id \`
    -PrincipalId $sp.Id -ResourceId $graphSp.Id -AppRoleId $r.Id | Out-Null
}

$secret = Add-MgApplicationPassword -ApplicationId $app.Id \`
  -PasswordCredential @{ DisplayName = "reporter"; EndDateTime = (Get-Date).AddYears(1) }

Write-Host "Tenant ID:     $((Get-MgContext).TenantId)"
Write-Host "Client ID:     $($app.AppId)"
Write-Host "Client secret: $($secret.SecretText)"`;

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

function Perm({ value }: { value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-3 py-2 dark:bg-slate-900">
      <code className="text-xs text-slate-700 dark:text-slate-200">{value}</code>
      <CopyButton text={value} />
    </div>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-600 text-xs font-bold text-white">
        {n}
      </div>
      <div className="min-w-0 flex-1 space-y-2">
        <h4 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h4>
        <div className="text-sm text-slate-600 dark:text-slate-300">{children}</div>
      </div>
    </div>
  );
}

/**
 * Guided first-run setup of the Entra app registration the reporter needs.
 * Shown until a connection is configured. Collapsible so it stays out of the
 * way once you know the drill.
 */
export default function SetupWizard({ defaultOpen = true }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const [showScript, setShowScript] = useState(false);

  return (
    <div className="card overflow-hidden border-brand-200 dark:border-brand-800/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 bg-brand-50 px-6 py-4 text-left dark:bg-brand-900/20"
      >
        <div>
          <h2 className="text-lg font-semibold text-brand-800 dark:text-brand-300">
            First-time setup: create your app registration
          </h2>
          <p className="mt-0.5 text-sm text-brand-700/80 dark:text-brand-400/80">
            The report reads Copilot usage from Microsoft Graph. Set up an Entra app
            registration once, then paste its details into the form below.
          </p>
        </div>
        <span className="shrink-0 text-brand-700 dark:text-brand-300">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="space-y-6 px-6 py-5">
          <Step n={1} title="Create the app registration">
            <p>
              Open{" "}
              <a
                href="https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/CreateApplicationBlade/quickStartType~/null/isMSAApp~/false"
                target="_blank"
                rel="noreferrer"
                className="font-medium text-brand-600 underline dark:text-brand-400"
              >
                Entra → App registrations → New registration
              </a>
              . Give it a name like <span className="font-medium">M365 Copilot Usage Reporter</span>,
              leave the defaults, and select <span className="font-medium">Register</span>.
            </p>
          </Step>

          <Step n={2} title="Add application permissions">
            <p className="mb-2">
              Under <span className="font-medium">API permissions → Add a permission → Microsoft
              Graph → Application permissions</span>, add these two, then choose{" "}
              <span className="font-medium">Grant admin consent</span>:
            </p>
            <div className="space-y-2">
              <Perm value="AiEnterpriseInteraction.Read.All" />
              <Perm value="Directory.Read.All" />
            </div>
          </Step>

          <Step n={3} title="Create a client secret">
            <p>
              Under <span className="font-medium">Certificates &amp; secrets → New client
              secret</span>, create one and copy its <span className="font-medium">Value</span>{" "}
              immediately (it's shown only once).
            </p>
          </Step>

          <Step n={4} title="Copy the IDs and paste below">
            <p>
              From the app's <span className="font-medium">Overview</span> page, copy the{" "}
              <span className="font-medium">Directory (tenant) ID</span> and{" "}
              <span className="font-medium">Application (client) ID</span>. Paste those plus the
              secret into the form below, then <span className="font-medium">Save</span> and{" "}
              <span className="font-medium">Test connection</span>.
            </p>
          </Step>

          <div className="rounded-lg border border-slate-200 dark:border-slate-700">
            <button
              type="button"
              onClick={() => setShowScript((v) => !v)}
              className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-slate-700 dark:text-slate-200"
            >
              <span>Prefer to script it? Run this instead of steps 1–3</span>
              <span className="text-slate-400">{showScript ? "▲" : "▼"}</span>
            </button>
            {showScript && (
              <div className="border-t border-slate-200 px-4 py-3 dark:border-slate-700">
                <div className="mb-2 flex justify-end">
                  <CopyButton text={SETUP_SCRIPT} label="Copy script" />
                </div>
                <pre className="max-h-72 overflow-auto rounded-md bg-slate-900 p-3 text-xs leading-relaxed text-slate-100">
                  <code>{SETUP_SCRIPT}</code>
                </pre>
                <p className="mt-2 text-xs text-slate-400">
                  Resolves permission IDs by name, creates the app, grants consent, and prints the
                  Tenant ID, Client ID, and secret to paste below.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
