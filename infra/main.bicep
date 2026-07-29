// Subscription-scoped entrypoint: creates the resource group and deploys all
// resources into it. Driven by `azd up`.
targetScope = 'subscription'
@minLength(1)
@maxLength(64)
@description('Name of the azd environment; used to derive resource names.')
param environmentName string

@minLength(1)
@description('Primary location for all resources.')
param location string

@secure()
@description('Administrator password for the PostgreSQL flexible server.')
param postgresAdminPassword string

@secure()
@description('Fernet key (urlsafe base64, 32 bytes) for encrypting the Graph secret.')
param fernetKey string

@secure()
@description('Secret key used to sign JWT session tokens.')
param secretKey string

@description('First-run admin username for the report.')
param adminUsername string = 'admin'

@secure()
@description('First-run admin password for the report.')
param adminPassword string

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    resourceToken: resourceToken
    tags: tags
    postgresAdminPassword: postgresAdminPassword
    fernetKey: fernetKey
    secretKey: secretKey
    adminUsername: adminUsername
    adminPassword: adminPassword
  }
}

output AZURE_LOCATION string = location
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryLoginServer
output SERVICE_API_URI string = resources.outputs.apiUri
