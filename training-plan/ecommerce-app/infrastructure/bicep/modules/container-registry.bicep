// Container Registry Module - Docker image storage
// Basic SKU for cost optimization

@description('Container Registry name')
param name string

@description('Location for Container Registry')
param location string

@description('Resource tags')
param tags object

@description('SKU for Container Registry')
@allowed(['Basic', 'Standard', 'Premium'])
param sku string = 'Basic'

// ============================================================
// CONTAINER REGISTRY
// ============================================================

resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: true  // Enable for training simplicity
    
    // Public network access
    publicNetworkAccess: 'Enabled'
    
    // Network rule bypass
    networkRuleBypassOptions: 'AzureServices'
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output registryId string = containerRegistry.id
output registryName string = containerRegistry.name
output loginServer string = containerRegistry.properties.loginServer

// Admin credentials (for development only - use managed identity in production)
#disable-next-line outputs-should-not-contain-secrets
output adminUsername string = containerRegistry.listCredentials().username
#disable-next-line outputs-should-not-contain-secrets
output adminPassword string = containerRegistry.listCredentials().passwords[0].value
