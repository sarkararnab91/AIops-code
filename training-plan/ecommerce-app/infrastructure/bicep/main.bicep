// Main Bicep Template - E-Commerce AIOps Training Infrastructure
// Deploys AKS, Cosmos DB, Redis, Service Bus, and Monitoring resources
// Optimized for cost with scale-to-zero and serverless options

targetScope = 'resourceGroup'

// ============================================================
// PARAMETERS
// ============================================================

@description('Location for all resources')
param location string = resourceGroup().location

@description('Environment name')
@allowed(['dev', 'training', 'prod'])
param environment string = 'training'

@description('Project name for resource naming')
param projectName string = 'aiops'

@description('Unique suffix for globally unique resource names')
param uniqueSuffix string = uniqueString(resourceGroup().id)

@description('AKS cluster admin username')
param aksAdminUsername string = 'azureuser'

@description('SSH public key for AKS nodes')
@secure()
param sshPublicKey string

@description('Azure AD tenant ID for AKS authentication')
param aadTenantId string = subscription().tenantId

// ============================================================
// VARIABLES
// ============================================================

var baseName = '${projectName}-${environment}'
var aksClusterName = '${baseName}-aks'
var cosmosAccountName = '${projectName}${uniqueSuffix}'
var redisCacheName = '${baseName}-redis'
var serviceBusName = '${projectName}${uniqueSuffix}sb'
var appInsightsName = '${baseName}-appinsights'
var logAnalyticsName = '${baseName}-logs'
var containerRegistryName = '${projectName}${uniqueSuffix}acr'

var commonTags = {
  Project: 'aiops-training'
  Environment: environment
  ManagedBy: 'bicep'
  CostCenter: 'training'
}

// ============================================================
// MODULES
// ============================================================

// Log Analytics Workspace (must be created first for monitoring)
module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'logAnalyticsDeployment'
  params: {
    name: logAnalyticsName
    location: location
    tags: commonTags
    retentionInDays: 30  // Minimum for cost savings
  }
}

// Application Insights
module appInsights 'modules/app-insights.bicep' = {
  name: 'appInsightsDeployment'
  params: {
    name: appInsightsName
    location: location
    tags: commonTags
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
  }
}

// Azure Container Registry
module containerRegistry 'modules/container-registry.bicep' = {
  name: 'containerRegistryDeployment'
  params: {
    name: containerRegistryName
    location: location
    tags: commonTags
    sku: 'Basic'  // Cost optimized for training
  }
}

// AKS Cluster with KEDA for scale-to-zero
module aks 'modules/aks.bicep' = {
  name: 'aksDeployment'
  params: {
    name: aksClusterName
    location: location
    tags: commonTags
    adminUsername: aksAdminUsername
    sshPublicKey: sshPublicKey
    aadTenantId: aadTenantId
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    containerRegistryId: containerRegistry.outputs.registryId
  }
}

// Cosmos DB (Serverless)
module cosmosDb 'modules/cosmos-db.bicep' = {
  name: 'cosmosDbDeployment'
  params: {
    accountName: cosmosAccountName
    location: location
    tags: commonTags
    enableServerless: true
  }
}

// Redis Cache
module redis 'modules/redis.bicep' = {
  name: 'redisDeployment'
  params: {
    name: redisCacheName
    location: location
    tags: commonTags
    skuName: 'Basic'
    skuFamily: 'C'
    skuCapacity: 0  // C0 - smallest/cheapest
  }
}

// Service Bus
module serviceBus 'modules/service-bus.bicep' = {
  name: 'serviceBusDeployment'
  params: {
    name: serviceBusName
    location: location
    tags: commonTags
    sku: 'Basic'  // Cost optimized
  }
}

// Alert Rules
module alerts 'modules/alerts.bicep' = {
  name: 'alertsDeployment'
  params: {
    appInsightsId: appInsights.outputs.appInsightsId
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    location: location
    tags: commonTags
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output aksClusterName string = aks.outputs.clusterName
output aksClusterFqdn string = aks.outputs.clusterFqdn
output cosmosDbEndpoint string = cosmosDb.outputs.endpoint
output redisHostName string = redis.outputs.hostName
output serviceBusNamespace string = serviceBus.outputs.namespaceName
output appInsightsConnectionString string = appInsights.outputs.connectionString
output appInsightsInstrumentationKey string = appInsights.outputs.instrumentationKey
output containerRegistryLoginServer string = containerRegistry.outputs.loginServer
output logAnalyticsWorkspaceId string = logAnalytics.outputs.workspaceId

// Cost estimation output
output estimatedMonthlyCost string = 'Estimated: $100-280/month with auto-shutdown. See README for cost breakdown.'
