// All resources for the M365 Copilot Usage Reporter, deployed into one RG:
// Log Analytics, Container Registry, managed identity, Container Apps
// Environment, a PostgreSQL flexible server, and the api + worker container apps.
@description('Location for all resources.')
param location string

@minLength(3)
@description('Stable token used to name resources uniquely.')
param resourceToken string

@description('Tags applied to every resource (must include azd-env-name).')
param tags object

@secure()
param postgresAdminPassword string
@secure()
param fernetKey string
@secure()
param secretKey string
param adminUsername string
@secure()
param adminPassword string

@description('Enable Entra ID single sign-on (Container Apps Easy Auth). When false, only the admin password is used.')
param enableEntraAuth bool = false
@description('Application (client) ID of the app registration used for Entra sign-in. Only used when enableEntraAuth is true.')
param entraClientId string = ''
@secure()
@description('Client secret for the Entra sign-in app registration. Only used when enableEntraAuth is true.')
param entraClientSecret string = ''
@description('Directory (tenant) ID that issues sign-in tokens. Defaults to the deployment tenant.')
param entraTenantId string = tenant().tenantId

@allowed([ '17', '16', '15', '14' ])
@description('PostgreSQL major version. If a region reports the allowed set as empty ([]), it does not offer this version/SKU — choose a supported region or a different SKU.')
param postgresVersion string = '16'
@description('PostgreSQL Flexible Server compute size. Default is the cheapest burstable size; switch to e.g. Standard_D2ds_v5 (GeneralPurpose) if a region lacks Burstable.')
param postgresSkuName string = 'Standard_B1ms'
@allowed([ 'Burstable', 'GeneralPurpose', 'MemoryOptimized' ])
@description('Compute tier matching postgresSkuName.')
param postgresSkuTier string = 'Burstable'

// Workload prefix so every resource is instantly identifiable in the portal
// (e.g. "copilot-psql-xxxx" instead of a bare "psql-xxxx"). Change this one
// value to rebrand every resource name.
var workload = 'copilot'
var abbrs = {
  registry: 'acr'
  identity: 'id'
  logs: 'log'
  env: 'cae'
  postgres: 'psql'
}
var pgAdminLogin = 'copilotadmin'
var pgDatabaseName = 'copilot'

// --- Observability ------------------------------------------------------
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${workload}-${abbrs.logs}-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// --- Identity + registry ------------------------------------------------
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${workload}-${abbrs.identity}-${resourceToken}'
  location: location
  tags: tags
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  // ACR names are alphanumeric only (no hyphens) and globally unique.
  name: '${workload}${abbrs.registry}${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
  }
}

// AcrPull for the managed identity so container apps can pull images.
var acrPullRoleId = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '7f951dda-4ed3-4680-a7ca-43fe172d538d'
)
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// --- Database -----------------------------------------------------------
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: '${workload}-${abbrs.postgres}-${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: postgresSkuName
    tier: postgresSkuTier
  }
  properties: {
    version: postgresVersion
    administratorLogin: pgAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }

  resource database 'databases@2024-08-01' = {
    name: pgDatabaseName
  }

  // Allow access from Azure services (Container Apps).
  resource allowAzure 'firewallRules@2024-08-01' = {
    name: 'AllowAllAzureServices'
    properties: {
      startIpAddress: '0.0.0.0'
      endIpAddress: '0.0.0.0'
    }
  }
}

var databaseUrl = 'postgresql+psycopg://${pgAdminLogin}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${pgDatabaseName}?sslmode=require'

// --- Container Apps environment ----------------------------------------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${workload}-${abbrs.env}-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var sharedSecrets = [
  { name: 'database-url', value: databaseUrl }
  { name: 'fernet-key', value: fernetKey }
  { name: 'secret-key', value: secretKey }
  { name: 'admin-password', value: adminPassword }
]

var sharedEnv = [
  { name: 'DATABASE_URL', secretRef: 'database-url' }
  { name: 'FERNET_KEY', secretRef: 'fernet-key' }
  { name: 'SECRET_KEY', secretRef: 'secret-key' }
  { name: 'ADMIN_USERNAME', value: adminUsername }
  { name: 'ADMIN_PASSWORD', secretRef: 'admin-password' }
  { name: 'APP_ENV', value: 'production' }
]

// When Entra SSO is on, the api app also holds the AAD client secret that Easy
// Auth references by name (aad-client-secret).
var apiSecrets = enableEntraAuth
  ? concat(sharedSecrets, [{ name: 'aad-client-secret', value: entraClientSecret }])
  : sharedSecrets

// --- API (web) container app -------------------------------------------
resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${workload}-api-${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': 'api' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        { server: registry.properties.loginServer, identity: identity.id }
      ]
      secrets: apiSecrets
    }
    template: {
      containers: [
        {
          name: 'api'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(sharedEnv, [
            { name: 'RUN_MIGRATIONS_ON_STARTUP', value: 'true' }
          ])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
  dependsOn: [acrPull]
}

// --- Entra SSO (Easy Auth) on the api app, when enabled ----------------
// AllowAnonymous so it only adds identity when present and never blocks the
// built-in password gate. The app exchanges the injected identity for its own
// JWT at POST /auth/entra.
resource apiAuth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (enableEntraAuth) {
  parent: api
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: { unauthenticatedClientAction: 'AllowAnonymous' }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          openIdIssuer: 'https://login.microsoftonline.com/${entraTenantId}/v2.0'
          clientId: entraClientId
          clientSecretSettingName: 'aad-client-secret'
        }
        validation: {
          allowedAudiences: [
            entraClientId
            'api://${entraClientId}'
          ]
        }
      }
    }
    login: {
      tokenStore: { enabled: true }
    }
  }
}

// --- Worker container app (no ingress) ---------------------------------
resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${workload}-worker-${resourceToken}'
  location: location
  tags: union(tags, { 'azd-service-name': 'worker' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        { server: registry.properties.loginServer, identity: identity.id }
      ]
      secrets: sharedSecrets
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: concat(sharedEnv, [
            { name: 'RUN_MIGRATIONS_ON_STARTUP', value: 'false' }
          ])
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [acrPull]
}

output registryLoginServer string = registry.properties.loginServer
output apiUri string = 'https://${api.properties.configuration.ingress.fqdn}'
