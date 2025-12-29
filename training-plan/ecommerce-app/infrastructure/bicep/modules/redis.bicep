// Redis Cache Module - Session and Cart Caching
// Cost optimized with Basic SKU

@description('Redis cache name')
param name string

@description('Location for Redis')
param location string

@description('Resource tags')
param tags object

@description('SKU name')
@allowed(['Basic', 'Standard', 'Premium'])
param skuName string = 'Basic'

@description('SKU family')
@allowed(['C', 'P'])
param skuFamily string = 'C'

@description('SKU capacity (0-6 for C family, 1-5 for P family)')
@minValue(0)
@maxValue(6)
param skuCapacity int = 0

// ============================================================
// REDIS CACHE
// ============================================================

resource redisCache 'Microsoft.Cache/redis@2023-08-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: skuName
      family: skuFamily
      capacity: skuCapacity
    }
    
    enableNonSslPort: false  // Disable non-SSL for security
    
    minimumTlsVersion: '1.2'
    
    // Redis configuration
    redisConfiguration: {
      'maxmemory-policy': 'volatile-lru'  // Evict keys with TTL when memory is full
      'maxfragmentationmemory-reserved': '50'
      'maxmemory-reserved': '50'
    }
    
    // Public network access (enable for training simplicity)
    publicNetworkAccess: 'Enabled'
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output cacheId string = redisCache.id
output hostName string = redisCache.properties.hostName
output port int = redisCache.properties.port
output sslPort int = redisCache.properties.sslPort

// Output primary key (for development only - use managed identity in production)
#disable-next-line outputs-should-not-contain-secrets
output primaryKey string = redisCache.listKeys().primaryKey

// Connection string format
output connectionString string = '${redisCache.properties.hostName}:${redisCache.properties.sslPort},password=${redisCache.listKeys().primaryKey},ssl=True,abortConnect=False'
