/** Shared first-run setup content — imported by both SetupWizard (Settings) and
 *  SetupGuidePage (/help) so the two can never drift apart. */

export const APP_DISPLAY_NAME = "M365 Copilot Usage Reporter";

/** Microsoft Graph application permissions this solution needs. */
export const REQUIRED_PERMISSIONS = [
  {
    value: "AiEnterpriseInteraction.Read.All",
    why: "Reads Copilot enterprise interaction history — the usage signal itself.",
  },
  {
    value: "Directory.Read.All",
    why: "Resolves users, departments and licences so usage can be grouped and filtered.",
  },
];

/** A ready-to-run script that creates the app registration, adds the application
 *  permissions, grants admin consent, and prints the values to paste into the
 *  wizard. Permission GUIDs are resolved by name at runtime so nothing is
 *  hard-coded or can drift. */
export const SETUP_SCRIPT = `# Run in PowerShell 7 with the Microsoft Graph SDK.
# Requires a Global Administrator (or Privileged Role + Application admin).
Install-Module Microsoft.Graph -Scope CurrentUser -Force  # first time only
Connect-MgGraph -Scopes "Application.ReadWrite.All","AppRoleAssignment.ReadWrite.All"

$graphSp = Get-MgServicePrincipal -Filter "appId eq '00000003-0000-0000-c000-000000000000'"
$needed  = "AiEnterpriseInteraction.Read.All","Directory.Read.All"
$roles   = $graphSp.AppRoles | Where-Object { $needed -contains $_.Value }

$app = New-MgApplication -DisplayName "${APP_DISPLAY_NAME}" -RequiredResourceAccess @{
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
