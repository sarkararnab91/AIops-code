// Service Bus Module - Async Messaging for Microservices
// Cost optimized with Basic SKU

@description('Service Bus namespace name')
param name string

@description('Location for Service Bus')
param location string

@description('Resource tags')
param tags object

@description('SKU tier')
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

// ============================================================
// SERVICE BUS NAMESPACE
// ============================================================

resource serviceBusNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    // Disable local auth in production, but enable for training
    disableLocalAuth: false
    
    // Minimum TLS version
    minimumTlsVersion: '1.2'
    
    // Public network access (enable for training simplicity)
    publicNetworkAccess: 'Enabled'
  }
}

// ============================================================
// QUEUES
// ============================================================

// Order processing queue
resource orderQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'orders'
  properties: {
    lockDuration: 'PT1M'  // 1 minute lock
    maxSizeInMegabytes: 1024
    requiresDuplicateDetection: false
    requiresSession: false
    defaultMessageTimeToLive: 'P1D'  // 1 day TTL
    deadLetteringOnMessageExpiration: true
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    maxDeliveryCount: 5
    enablePartitioning: false  // Disable for Basic SKU
  }
}

// Payment processing queue
resource paymentQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'payments'
  properties: {
    lockDuration: 'PT1M'
    maxSizeInMegabytes: 1024
    requiresDuplicateDetection: false
    requiresSession: false
    defaultMessageTimeToLive: 'P1D'
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 5
    enablePartitioning: false
  }
}

// Notification queue
resource notificationQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'notifications'
  properties: {
    lockDuration: 'PT30S'  // 30 seconds lock
    maxSizeInMegabytes: 1024
    requiresDuplicateDetection: false
    requiresSession: false
    defaultMessageTimeToLive: 'P1D'
    deadLetteringOnMessageExpiration: true
    maxDeliveryCount: 3  // Fewer retries for notifications
    enablePartitioning: false
  }
}

// Inventory update queue
resource inventoryQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'inventory-updates'
  properties: {
    lockDuration: 'PT1M'
    maxSizeInMegabytes: 1024
    requiresDuplicateDetection: true
    requiresSession: false
    defaultMessageTimeToLive: 'P1D'
    deadLetteringOnMessageExpiration: true
    duplicateDetectionHistoryTimeWindow: 'PT10M'
    maxDeliveryCount: 5
    enablePartitioning: false
  }
}

// Dead letter queue monitoring (for failed messages)
resource deadLetterMonitorQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: serviceBusNamespace
  name: 'dead-letter-monitor'
  properties: {
    lockDuration: 'PT5M'  // Longer lock for manual processing
    maxSizeInMegabytes: 1024
    requiresDuplicateDetection: false
    requiresSession: false
    defaultMessageTimeToLive: 'P7D'  // 7 days for investigation
    deadLetteringOnMessageExpiration: false
    maxDeliveryCount: 1
    enablePartitioning: false
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output namespaceId string = serviceBusNamespace.id
output namespaceName string = serviceBusNamespace.name
output namespaceEndpoint string = serviceBusNamespace.properties.serviceBusEndpoint

// Queue names
output orderQueueName string = orderQueue.name
output paymentQueueName string = paymentQueue.name
output notificationQueueName string = notificationQueue.name
output inventoryQueueName string = inventoryQueue.name

// Connection string (for development only - use managed identity in production)
#disable-next-line outputs-should-not-contain-secrets
output primaryConnectionString string = listKeys('${serviceBusNamespace.id}/AuthorizationRules/RootManageSharedAccessKey', serviceBusNamespace.apiVersion).primaryConnectionString
