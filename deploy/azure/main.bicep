// Maria One — Azure Container Apps + managed Postgres/Redis + Key Vault.
// Minimal, security-baseline-aligned skeleton (see ../../SECURITY.md and README.md).
// Deploy: az deployment group create -g maria-one --template-file main.bicep -p imageTag=<tag>

@description('Location for all resources')
param location string = resourceGroup().location

@description('Container image tag (git short sha)')
param imageTag string

@description('ACR login server, e.g. mariaoneacr.azurecr.io')
param acrServer string

@description('Postgres admin password (pass via Key Vault reference, not plaintext)')
@secure()
param pgAdminPassword string

var prefix = 'maria-one'

// ---- Key Vault (secrets; app reads via managed identity) ----
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${prefix}-kv'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    publicNetworkAccess: 'Disabled'
  }
}

// ---- PostgreSQL Flexible Server (system of record) ----
resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview' = {
  name: '${prefix}-pg'
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    version: '16'
    administratorLogin: 'maria'
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 30, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    network: { publicNetworkAccess: 'Disabled' } // private endpoint wired separately
  }
}

// ---- Azure Cache for Redis (queues, locks, idempotency) ----
resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: '${prefix}-redis'
  location: location
  properties: {
    sku: { name: 'Basic', family: 'C', capacity: 0 }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
  }
}

// ---- Container Apps environment ----
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${prefix}-env'
  location: location
  properties: {}
}

// ---- API container app (external ingress) ----
resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-api'
  location: location
  identity: { type: 'SystemAssigned' } // used to read Key Vault
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8000, transport: 'auto', allowInsecure: false }
      // secrets are Key Vault references in practice; placeholder names shown
      secrets: [
        { name: 'api-token', keyVaultUrl: '${kv.properties.vaultUri}secrets/API-TOKEN', identity: 'system' }
      ]
      registries: [ { server: acrServer, identity: 'system' } ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${acrServer}/maria-one-api:${imageTag}'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'ENV', value: 'prod' }
            { name: 'API_TOKEN', secretRef: 'api-token' }
          ]
          probes: [
            { type: 'Liveness',  httpGet: { path: '/healthz', port: 8000 } }
            { type: 'Readiness', httpGet: { path: '/readyz',  port: 8000 } }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 10
        rules: [ { name: 'http', http: { metadata: { concurrentRequests: '50' } } } ]
      }
    }
  }
}

// ---- Worker container app (internal; scales on queue depth) ----
resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-worker'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [ { server: acrServer, identity: 'system' } ]
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: '${acrServer}/maria-one-api:${imageTag}'
          command: [ 'python', '-m', 'app.workers' ]
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
        }
      ]
      // Scale on Redis outbox/queue depth (KEDA). Idle to zero when drained.
      scale: { minReplicas: 0, maxReplicas: 5 }
    }
  }
}

output apiFqdn string = api.properties.configuration.ingress.fqdn
