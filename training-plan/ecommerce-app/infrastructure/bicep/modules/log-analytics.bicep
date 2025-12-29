// Log Analytics Module - Central logging for AKS and Application Insights
// Configured with minimal retention for cost savings

@description('Log Analytics workspace name')
param name string

@description('Location for Log Analytics')
param location string

@description('Resource tags')
param tags object

@description('Data retention in days (minimum 30)')
@minValue(30)
@maxValue(730)
param retentionInDays int = 30

// ============================================================
// LOG ANALYTICS WORKSPACE
// ============================================================

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'  // Pay-as-you-go pricing
    }
    retentionInDays: retentionInDays
    
    // Features
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    
    // Workspace capping for cost control (optional)
    workspaceCapping: {
      dailyQuotaGb: 1  // 1 GB daily cap for training
    }
    
    // Public network access
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ============================================================
// SAVED QUERIES
// ============================================================

resource serviceHealthQuery 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: logAnalyticsWorkspace
  name: 'ServiceHealthOverview'
  properties: {
    category: 'Performance'
    displayName: 'Service Health Overview'
    query: '''
      requests
      | where timestamp > ago(1h)
      | summarize 
          Requests = count(),
          Failures = countif(success == false),
          AvgLatency = round(avg(duration), 0),
          P95Latency = round(percentile(duration, 95), 0)
      by cloud_RoleName
      | extend FailureRate = round(100.0 * Failures / Requests, 2)
      | order by Requests desc
    '''
    version: 2
  }
}

resource slowRequestsQuery 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: logAnalyticsWorkspace
  name: 'SlowRequests'
  properties: {
    category: 'Performance'
    displayName: 'Slow Requests (> 1 second)'
    query: '''
      requests
      | where timestamp > ago(1h)
      | where duration > 1000
      | project 
          timestamp,
          Service = cloud_RoleName,
          Endpoint = name,
          Duration = round(duration, 0),
          Success = success,
          operation_Id
      | order by Duration desc
      | take 100
    '''
    version: 2
  }
}

resource errorAnalysisQuery 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: logAnalyticsWorkspace
  name: 'ErrorAnalysis'
  properties: {
    category: 'Errors'
    displayName: 'Error Analysis by Service'
    query: '''
      exceptions
      | where timestamp > ago(24h)
      | summarize 
          Count = count(),
          LastSeen = max(timestamp)
      by cloud_RoleName, type, outerMessage
      | order by Count desc
      | take 50
    '''
    version: 2
  }
}

resource dependencyHealthQuery 'Microsoft.OperationalInsights/workspaces/savedSearches@2020-08-01' = {
  parent: logAnalyticsWorkspace
  name: 'DependencyHealth'
  properties: {
    category: 'Dependencies'
    displayName: 'Dependency Health'
    query: '''
      dependencies
      | where timestamp > ago(1h)
      | summarize 
          Calls = count(),
          Failures = countif(success == false),
          AvgDuration = round(avg(duration), 0)
      by type, target
      | extend FailureRate = round(100.0 * Failures / Calls, 2)
      | order by Calls desc
    '''
    version: 2
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output workspaceId string = logAnalyticsWorkspace.id
output workspaceName string = logAnalyticsWorkspace.name
output customerId string = logAnalyticsWorkspace.properties.customerId

// Primary key for agents (use managed identity in production)
#disable-next-line outputs-should-not-contain-secrets
output primarySharedKey string = logAnalyticsWorkspace.listKeys().primarySharedKey
