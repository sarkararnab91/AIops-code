# Session 3: Data Services Setup (Cosmos DB, Redis, Service Bus)

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 1, Day 3 (Wednesday)
- **Prerequisites**: Sessions 1-2 completed, AKS cluster running
- **Deliverable**: Cosmos DB, Redis Cache, and Service Bus deployed

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Deploy Cosmos DB with serverless configuration
2. Set up Azure Redis Cache (Basic tier)
3. Configure Azure Service Bus for async messaging
4. Understand the role of each service in our e-commerce app

---

## 📚 Concepts

### Data Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        E-COMMERCE DATA LAYER                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         COSMOS DB (Serverless)                        │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐  │   │
│  │  │  products   │  │   orders    │  │    users    │  │  inventory │  │   │
│  │  │ (catalog)   │  │  (orders)   │  │   (users)   │  │ (inventory)│  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └────────────┘  │   │
│  │  • NoSQL document store           • Auto-scale on demand            │   │
│  │  • Low latency reads              • Pay-per-request (serverless)    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         REDIS CACHE (Basic C0)                       │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │   Session   │  │    Cart     │  │   Product   │                  │   │
│  │  │    Store    │  │    Cache    │  │    Cache    │                  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │   │
│  │  • In-memory caching              • Sub-millisecond latency         │   │
│  │  • 250MB cache size               • $16/month fixed cost            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         SERVICE BUS (Basic)                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │   Orders    │  │   Payment   │  │Notifications│                  │   │
│  │  │    Queue    │  │    Queue    │  │    Topic    │                  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │   │
│  │  • Async message processing       • Reliable delivery               │   │
│  │  • Decoupled services             • Dead letter queues              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why These Services?

| Service | Purpose | Cost Optimization |
|---------|---------|-------------------|
| **Cosmos DB** | Primary document database | Serverless = pay only for requests |
| **Redis Cache** | Session & data caching | Basic C0 = $16/month fixed |
| **Service Bus** | Async messaging between services | Basic tier = ~$0.05/million ops |

---

## 🛠️ Hands-On Exercise

### Step 1: Create Combined Bicep Template for Data Services

Create `ecommerce-app/infrastructure/bicep/data-services.bicep`:

```bicep
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
```

### Step 2: Deploy Data Services

```bash
# Set variables
RESOURCE_GROUP="aiops-training-rg"

# Deploy data services
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file ecommerce-app/infrastructure/bicep/data-services.bicep \
  --parameters \
    baseName="aiops" \
    environment="training"

# This takes about 10-15 minutes (Redis is the slowest)
```

### Step 3: Retrieve Connection Information

```bash
# Get Cosmos DB connection info
COSMOS_NAME=$(az cosmosdb list -g $RESOURCE_GROUP --query "[0].name" -o tsv)
COSMOS_ENDPOINT=$(az cosmosdb show -n $COSMOS_NAME -g $RESOURCE_GROUP --query "documentEndpoint" -o tsv)
COSMOS_KEY=$(az cosmosdb keys list -n $COSMOS_NAME -g $RESOURCE_GROUP --query "primaryMasterKey" -o tsv)

echo "Cosmos DB Endpoint: $COSMOS_ENDPOINT"

# Get Redis connection info
REDIS_NAME=$(az redis list -g $RESOURCE_GROUP --query "[0].name" -o tsv)
REDIS_HOST=$(az redis show -n $REDIS_NAME -g $RESOURCE_GROUP --query "hostName" -o tsv)
REDIS_KEY=$(az redis list-keys -n $REDIS_NAME -g $RESOURCE_GROUP --query "primaryKey" -o tsv)

echo "Redis Host: $REDIS_HOST"

# Get Service Bus connection string
SB_NAME=$(az servicebus namespace list -g $RESOURCE_GROUP --query "[0].name" -o tsv)
SB_CONNECTION=$(az servicebus namespace authorization-rule keys list \
  -g $RESOURCE_GROUP \
  --namespace-name $SB_NAME \
  --name RootManageSharedAccessKey \
  --query "primaryConnectionString" -o tsv)

echo "Service Bus: $SB_NAME"
```

### Step 4: Test Cosmos DB Connection

Create a test script `scripts/test_cosmos.py`:

```python
#!/usr/bin/env python3
"""Test Cosmos DB connection and basic operations."""

import os
from azure.cosmos import CosmosClient, PartitionKey
from dotenv import load_dotenv

load_dotenv()

def test_cosmos_connection():
    """Test basic Cosmos DB operations."""
    
    # Get connection info from environment or Azure CLI
    endpoint = os.getenv("COSMOS_DB_ENDPOINT")
    key = os.getenv("COSMOS_DB_KEY")
    
    if not endpoint or not key:
        print("❌ Missing COSMOS_DB_ENDPOINT or COSMOS_DB_KEY")
        print("   Set these in your .env file or export them")
        return False
    
    try:
        # Connect to Cosmos DB
        client = CosmosClient(endpoint, key)
        print(f"✅ Connected to Cosmos DB: {endpoint}")
        
        # List databases
        databases = list(client.list_databases())
        print(f"✅ Found {len(databases)} database(s)")
        
        # Check ecommerce database
        database = client.get_database_client("ecommerce")
        containers = list(database.list_containers())
        print(f"✅ Database 'ecommerce' has {len(containers)} container(s):")
        for container in containers:
            print(f"   - {container['id']}")
        
        # Test write to products container
        products = database.get_container_client("products")
        test_product = {
            "id": "test-product-001",
            "name": "Test Perfume",
            "category": "perfumes",
            "price": 49.99,
            "description": "A test product for connectivity verification"
        }
        
        products.upsert_item(test_product)
        print("✅ Successfully wrote test product to 'products' container")
        
        # Read it back
        read_product = products.read_item(item="test-product-001", partition_key="perfumes")
        print(f"✅ Successfully read back: {read_product['name']}")
        
        # Clean up test data
        products.delete_item(item="test-product-001", partition_key="perfumes")
        print("✅ Cleaned up test data")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_cosmos_connection()
    exit(0 if success else 1)
```

### Step 5: Test Redis Connection

Create `scripts/test_redis.py`:

```python
#!/usr/bin/env python3
"""Test Redis connection and basic operations."""

import os
import redis
from dotenv import load_dotenv

load_dotenv()

def test_redis_connection():
    """Test basic Redis operations."""
    
    host = os.getenv("REDIS_HOST")
    password = os.getenv("REDIS_PASSWORD")
    port = int(os.getenv("REDIS_PORT", 6380))
    
    if not host or not password:
        print("❌ Missing REDIS_HOST or REDIS_PASSWORD")
        print("   Set these in your .env file or export them")
        return False
    
    try:
        # Connect to Redis (Azure Redis requires SSL)
        client = redis.Redis(
            host=host,
            port=port,
            password=password,
            ssl=True,
            ssl_cert_reqs=None
        )
        
        # Test connection
        pong = client.ping()
        print(f"✅ Connected to Redis: {host}")
        print(f"✅ PING response: {pong}")
        
        # Test write
        client.set("test:key", "Hello from AIOps Training!")
        print("✅ Successfully wrote test key")
        
        # Test read
        value = client.get("test:key")
        print(f"✅ Read value: {value.decode()}")
        
        # Test delete
        client.delete("test:key")
        print("✅ Cleaned up test key")
        
        # Get info
        info = client.info("memory")
        print(f"✅ Redis memory used: {info['used_memory_human']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_redis_connection()
    exit(0 if success else 1)
```

### Step 6: Test Service Bus Connection

Create `scripts/test_servicebus.py`:

```python
#!/usr/bin/env python3
"""Test Service Bus connection and basic operations."""

import os
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from dotenv import load_dotenv

load_dotenv()

def test_servicebus_connection():
    """Test basic Service Bus operations."""
    
    connection_string = os.getenv("SERVICE_BUS_CONNECTION_STRING")
    
    if not connection_string:
        print("❌ Missing SERVICE_BUS_CONNECTION_STRING")
        print("   Set this in your .env file or export it")
        return False
    
    try:
        # Connect to Service Bus
        client = ServiceBusClient.from_connection_string(connection_string)
        print("✅ Connected to Service Bus")
        
        # Test sending to orders-queue
        with client.get_queue_sender("orders-queue") as sender:
            message = ServiceBusMessage(
                body="Test order message",
                application_properties={"test": True}
            )
            sender.send_messages(message)
            print("✅ Sent test message to 'orders-queue'")
        
        # Test receiving from orders-queue
        with client.get_queue_receiver("orders-queue", max_wait_time=5) as receiver:
            messages = receiver.receive_messages(max_message_count=1)
            for msg in messages:
                print(f"✅ Received message: {str(msg)}")
                receiver.complete_message(msg)
                print("✅ Completed (acknowledged) message")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_servicebus_connection()
    exit(0 if success else 1)
```

---

## 🧪 Verification Checklist

Before moving to the next session, ensure you have:

- [ ] Cosmos DB deployed with serverless configuration
- [ ] Database `ecommerce` created with 5 containers
- [ ] Redis Cache (Basic C0) deployed and accessible
- [ ] Service Bus namespace with 4 queues created
- [ ] Connection strings retrieved and saved to `.env` file
- [ ] Test scripts run successfully

---

## 💡 Cost Summary

| Service | Configuration | Est. Monthly Cost |
|---------|---------------|-------------------|
| Cosmos DB | Serverless + Free tier | $0-10 (usage based) |
| Redis Cache | Basic C0 | $16 |
| Service Bus | Basic tier | $10 |
| **Total** | | **~$26-36/month** |

---

## 📖 Key Takeaways

1. **Cosmos DB serverless** charges per request - perfect for variable workloads
2. **Redis Basic C0** is the most cost-effective cache for training
3. **Service Bus** enables reliable async communication between services
4. **Partition keys** in Cosmos DB are critical for performance

---

## 🔜 Next Session Preview

**Session 4: Microservices Part 1**
- Build Catalog Service with Cosmos DB integration
- Build Inventory Service for stock management
- Build User Service for authentication

---

## 📚 Additional Resources

- [Cosmos DB Serverless](https://docs.microsoft.com/en-us/azure/cosmos-db/serverless)
- [Azure Redis Cache](https://docs.microsoft.com/en-us/azure/azure-cache-for-redis/)
- [Azure Service Bus](https://docs.microsoft.com/en-us/azure/service-bus-messaging/)
- [Choosing partition keys](https://docs.microsoft.com/en-us/azure/cosmos-db/partitioning-overview)
