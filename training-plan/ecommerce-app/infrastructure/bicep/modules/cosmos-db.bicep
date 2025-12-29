// Cosmos DB Module - Serverless NoSQL Database
// Cost optimized with serverless capacity mode

@description('Cosmos DB account name')
param accountName string

@description('Location for Cosmos DB')
param location string

@description('Resource tags')
param tags object

@description('Enable serverless mode for cost optimization')
param enableServerless bool = true

// ============================================================
// COSMOS DB ACCOUNT
// ============================================================

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-02-15-preview' = {
  name: accountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    
    // Serverless for cost optimization (pay per request)
    capabilities: enableServerless ? [
      {
        name: 'EnableServerless'
      }
    ] : []
    
    // Consistency level
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'  // Good balance of consistency and performance
    }
    
    // Single region for training (cost saving)
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false  // Disable for cost savings
      }
    ]
    
    // Backup policy - periodic for serverless
    backupPolicy: {
      type: 'Periodic'
      periodicModeProperties: {
        backupIntervalInMinutes: 1440  // Daily backup
        backupRetentionIntervalInHours: 168  // 7 days retention
        backupStorageRedundancy: 'Local'  // LRS for cost savings
      }
    }
    
    // Disable public network access for security (optional)
    publicNetworkAccess: 'Enabled'  // Enable for training simplicity
    
    // Free tier (if available in subscription)
    enableFreeTier: false  // Set to true if free tier is available
  }
}

// ============================================================
// DATABASE
// ============================================================

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-02-15-preview' = {
  parent: cosmosAccount
  name: 'ecommerce'
  properties: {
    resource: {
      id: 'ecommerce'
    }
  }
}

// ============================================================
// CONTAINERS
// ============================================================

// Products container
resource productsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: database
  name: 'products'
  properties: {
    resource: {
      id: 'products'
      partitionKey: {
        paths: ['/category']
        kind: 'Hash'
      }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/"_etag"/?'
          }
        ]
      }
    }
  }
}

// Orders container
resource ordersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: database
  name: 'orders'
  properties: {
    resource: {
      id: 'orders'
      partitionKey: {
        paths: ['/userId']
        kind: 'Hash'
      }
      indexingPolicy: {
        automatic: true
        indexingMode: 'consistent'
      }
      // TTL for order history (optional)
      defaultTtl: -1  // -1 means no default TTL
    }
  }
}

// Users container
resource usersContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: database
  name: 'users'
  properties: {
    resource: {
      id: 'users'
      partitionKey: {
        paths: ['/id']
        kind: 'Hash'
      }
      uniqueKeyPolicy: {
        uniqueKeys: [
          {
            paths: ['/email']
          }
        ]
      }
    }
  }
}

// Inventory container
resource inventoryContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: database
  name: 'inventory'
  properties: {
    resource: {
      id: 'inventory'
      partitionKey: {
        paths: ['/productId']
        kind: 'Hash'
      }
    }
  }
}

// Carts container (with TTL for abandoned carts)
resource cartsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: database
  name: 'carts'
  properties: {
    resource: {
      id: 'carts'
      partitionKey: {
        paths: ['/userId']
        kind: 'Hash'
      }
      defaultTtl: 604800  // 7 days TTL for abandoned carts
    }
  }
}

// Payments container
resource paymentsContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-02-15-preview' = {
  parent: database
  name: 'payments'
  properties: {
    resource: {
      id: 'payments'
      partitionKey: {
        paths: ['/orderId']
        kind: 'Hash'
      }
    }
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output accountId string = cosmosAccount.id
output accountName string = cosmosAccount.name
output endpoint string = cosmosAccount.properties.documentEndpoint
output databaseName string = database.name

// Output connection string (for development only - use managed identity in production)
#disable-next-line outputs-should-not-contain-secrets
output primaryConnectionString string = cosmosAccount.listConnectionStrings().connectionStrings[0].connectionString
