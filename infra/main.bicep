// Every resource of the system in rg-<prefix>, applied by the deploy workflow on each push to main.
// Not here, because the pipeline's identity only has Contributor and so cannot grant roles: the identity
// itself, its federated credentials and every role assignment (README, "Azure initial setup").
// Also not here: the storage static website switch and the contained database users, which are data-plane settings.

@description('Azure name prefix: the IE username with dots replaced by hyphens.')
param prefix string = 'kpetrovski-ieu2024'

@description('Region of every resource; one of the five the Azure for Students subscription allows.')
param location string = resourceGroup().location

@description('Storage account serving the UI: the prefix without hyphens, followed by ui.')
param uiStorageName string = 'kpetrovskiieu2024ui'

@description('Image registry and namespace.')
param registry string = 'ghcr.io/kiril-p'

@description('Image tag both services run: the commit SHA being deployed.')
param imageTag string

@secure()
@description('Password of the SQL server admin login, used only for the initial setup of the database users.')
param sqlAdminPassword string

@secure()
@description('Connection string of the ideas database, with the ideas_app login: mssql://user:password@host:1433/db?encrypt=require')
param ideasDatabaseUrl string

@secure()
@description('Connection string of the review database, with the review_app login.')
param reviewDatabaseUrl string

@secure()
param organizerKey string

@secure()
param typesafeApiKey string

@secure()
param coachApiKey string

var webEndpoint = ui.properties.primaryEndpoints.web
var uiOrigin = take(webEndpoint, length(webEndpoint) - 1)

resource ui 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: uiStorageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: '${prefix}-sql'
  location: location
  properties: {
    administratorLogin: 'pkadmin'
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
    version: '12.0'
  }
}

// 0.0.0.0 to 0.0.0.0 is Azure's "allow Azure services": the Container Apps reach the server, the internet does not.
resource allowAzureServices 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  parent: sqlServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// The free offer fixes auto-pause at 60 minutes and the size at 32 GB, so neither is set here.
resource databases 'Microsoft.Sql/servers/databases@2023-08-01-preview' = [for service in ['ideas', 'review']: {
  parent: sqlServer
  name: '${prefix}-${service}-db'
  location: location
  sku: {
    name: 'GP_S_Gen5'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 1
  }
  properties: {
    minCapacity: json('0.5')
    requestedBackupStorageRedundancy: 'Local'
    useFreeLimit: true
    freeLimitExhaustionBehavior: 'AutoPause'
    zoneRedundant: false
  }
}]

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-env'
  location: location
  properties: {
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
    zoneRedundant: false
    peerAuthentication: { mtls: { enabled: false } }
    peerTrafficConfiguration: { encryption: { enabled: false } }
  }
}

resource review 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-review'
  location: location
  properties: {
    environmentId: containerEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      secrets: [
        { name: 'coach-api-key', value: coachApiKey }
        { name: 'database-url', value: reviewDatabaseUrl }
        { name: 'typesafe-api-key', value: typesafeApiKey }
      ]
    }
    template: {
      containers: [
        {
          name: '${prefix}-review'
          image: '${registry}/pitchgate-review:${imageTag}'
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'UI_ORIGIN', value: uiOrigin }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'TYPESAFE_API_KEY', secretRef: 'typesafe-api-key' }
            { name: 'COACH_API_KEY', secretRef: 'coach-api-key' }
          ]
        }
      ]
      // At most one replica, so startup migrations never run twice at once; zero when idle.
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          { name: 'http-scaler', http: { metadata: { concurrentRequests: '10' } } }
        ]
      }
    }
  }
}

resource ideas 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-ideas'
  location: location
  properties: {
    environmentId: containerEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      secrets: [
        { name: 'database-url', value: ideasDatabaseUrl }
        { name: 'organizer-key', value: organizerKey }
      ]
    }
    template: {
      containers: [
        {
          name: '${prefix}-ideas'
          image: '${registry}/pitchgate-ideas:${imageTag}'
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'UI_ORIGIN', value: uiOrigin }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'ORGANIZER_KEY', secretRef: 'organizer-key' }
            { name: 'REVIEW_URL', value: 'https://${review.properties.configuration.ingress.fqdn}' }
          ]
        }
      ]
      // At most one replica, so startup migrations never run twice at once; zero when idle.
      scale: {
        minReplicas: 0
        maxReplicas: 1
        rules: [
          { name: 'http-scaler', http: { metadata: { concurrentRequests: '10' } } }
        ]
      }
    }
  }
}

output uiOrigin string = uiOrigin
output ideasUrl string = 'https://${ideas.properties.configuration.ingress.fqdn}'
output reviewUrl string = 'https://${review.properties.configuration.ingress.fqdn}'
