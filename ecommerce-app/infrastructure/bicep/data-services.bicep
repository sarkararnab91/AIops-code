// Data Services: Cosmos DB, Redis, Service Bus
// Cost-optimized for training environment

@description('Base name for all resources')
param baseName string = 'aiops'

@description('Location for all resources')
param location string = resourceGroup().location

@description('Environment tag')
param environment string = 'training'

// Common tags
var commonTags = {
  Project: 'aiops-training'
  Environment: environment
  AutoShutdown: 'true'
  CostCenter: 'aiops-lab'
  ManagedBy: 'bicep'
}

// Unique suffix for globally unique names
var uniqueSuffix = uniqueString(resourceGroup().id)

// ============================================================
// COSMOS DB - Serverless
// ============================================================
resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2023-11-15' = {
  name: '${baseName}-cosmos-${uniqueSuffix}'
  location: location
  tags: commonTags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false  // Cost savings
      }
    ]
    capabilities: [
      {
        name: 'EnableServerless'  // Pay-per-request model
      }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    enableFreeTier: true  // Use free tier if available
  }
}

// Cosmos DB Database
resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2023-11-15' = {
  parent: cosmosAccount
  name: 'ecommerce'
  properties: {
    resource: {
      id: 'ecommerce'
    }
  }
}

// Cosmos DB Containers
var containers = [
  { name: 'products', partitionKey: '/category' }
  { name: 'orders', partitionKey: '/userId' }
  { name: 'users', partitionKey: '/id' }
  { name: 'inventory', partitionKey: '/productId' }
  { name: 'carts', partitionKey: '/userId' }
]

resource cosmosContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2023-11-15' = [for container in containers: {
  parent: cosmosDatabase
  name: container.name
  properties: {
    resource: {
      id: container.name
      partitionKey: {
        paths: [container.partitionKey]
        kind: 'Hash'
      }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
      }
    }
  }
}]

// ============================================================
// REDIS CACHE - Basic C0
// ============================================================
resource redisCache 'Microsoft.Cache/redis@2023-08-01' = {
  name: '${baseName}-redis-${uniqueSuffix}'
  location: location
  tags: commonTags
  properties: {
    sku: {
      name: 'Basic'
      family: 'C'
      capacity: 0  // C0 = 250MB, ~$16/month
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'  // Evict least recently used
    }
  }
}

// ============================================================
// SERVICE BUS - Basic Tier
// ============================================================
resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: '${baseName}-servicebus-${uniqueSuffix}'
  location: location
  tags: commonTags
  sku: {
    name: 'Basic'  // Basic tier for training
    tier: 'Basic'
  }
  properties: {}
}

// Service Bus Queues
var queues = [
  'orders-queue'
  'payment-queue'
  'notification-queue'
  'inventory-queue'
]

resource serviceBusQueues 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = [for queue in queues: {
  parent: serviceBusNamespace
  name: queue
  properties: {
    lockDuration: 'PT1M'
    maxSizeInMegabytes: 1024
    requiresDuplicateDetection: false
    requiresSession: false
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 10
  }
}]

// ============================================================
// OUTPUTS
// ============================================================
output cosmosDbEndpoint string = cosmosAccount.properties.documentEndpoint
output cosmosDbName string = cosmosAccount.name
output redisHostName string = redisCache.properties.hostName
output redisPort int = redisCache.properties.sslPort
output serviceBusNamespace string = serviceBusNamespace.name
output serviceBusEndpoint string = serviceBusNamespace.properties.serviceBusEndpoint
