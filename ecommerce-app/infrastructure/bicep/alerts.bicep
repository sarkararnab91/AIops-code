// Azure Monitor Alert Rules
// Configure alerts for e-commerce services

@description('Application Insights resource ID')
param appInsightsId string

@description('Log Analytics workspace ID')
param logAnalyticsWorkspaceId string

@description('Action group resource ID')
param actionGroupId string = ''

@description('Environment tag')
param environment string = 'training'

// Common tags
var commonTags = {
  Project: 'aiops-training'
  Environment: environment
  ManagedBy: 'bicep'
}

// ============================================================
// ACTION GROUP (Only create if ID not provided)
// ============================================================
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (empty(actionGroupId)) {
  name: 'aiops-training-alerts'
  location: 'Global'
  tags: commonTags
  properties: {
    groupShortName: 'AIOps'
    enabled: true
    emailReceivers: [
      {
        name: 'Training Team Email'
        emailAddress: 'training-alerts@example.com'
        useCommonAlertSchema: true
      }
    ]
  }
}

var finalActionGroupId = empty(actionGroupId) ? actionGroup.id : actionGroupId

// ============================================================
// METRIC ALERTS
// ============================================================

// Alert: High Error Rate
resource highErrorRateAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'high-error-rate'
  location: 'Global'
  tags: commonTags
  properties: {
    description: 'Alert when error rate exceeds 5%'
    severity: 1
    enabled: true
    scopes: [appInsightsId]
    evaluationFrequency: 'PT5M'  // Every 5 minutes
    windowSize: 'PT15M'          // 15 minute window
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'FailedRequests'
          metricName: 'requests/failed'
          metricNamespace: 'microsoft.insights/components'
          operator: 'GreaterThan'
          threshold: 5
          timeAggregation: 'Count'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: finalActionGroupId
      }
    ]
  }
}

// Alert: High Response Time
resource highLatencyAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'high-response-time'
  location: 'Global'
  tags: commonTags
  properties: {
    description: 'Alert when P95 response time exceeds 2 seconds'
    severity: 2
    enabled: true
    scopes: [appInsightsId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'ServerResponseTime'
          metricName: 'requests/duration'
          metricNamespace: 'microsoft.insights/components'
          operator: 'GreaterThan'
          threshold: 2000  // 2000ms = 2 seconds
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: finalActionGroupId
      }
    ]
  }
}

// Alert: Dependency Failures
resource dependencyFailureAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'dependency-failures'
  location: 'Global'
  tags: commonTags
  properties: {
    description: 'Alert when dependency call failures exceed threshold'
    severity: 1
    enabled: true
    scopes: [appInsightsId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'DependencyFailures'
          metricName: 'dependencies/failed'
          metricNamespace: 'microsoft.insights/components'
          operator: 'GreaterThan'
          threshold: 10
          timeAggregation: 'Count'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: finalActionGroupId
      }
    ]
  }
}

// ============================================================
// LOG-BASED (KQL) ALERTS
// ============================================================

// Alert: Exception Spike
resource exceptionSpikeAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'exception-spike'
  location: resourceGroup().location
  tags: commonTags
  properties: {
    displayName: 'Exception Spike Detected'
    description: 'Alert when exception count spikes above normal'
    severity: 1
    enabled: true
    evaluationFrequency: 'PT5M'
    scopes: [logAnalyticsWorkspaceId]
    windowSize: 'PT15M'
    criteria: {
      allOf: [
        {
          query: '''
            exceptions
            | where timestamp > ago(15m)
            | summarize ExceptionCount = count() by bin(timestamp, 5m)
            | where ExceptionCount > 50
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [finalActionGroupId]
    }
  }
}

// Alert: Slow Database Queries
resource slowDbQueriesAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'slow-database-queries'
  location: resourceGroup().location
  tags: commonTags
  properties: {
    displayName: 'Slow Database Queries'
    description: 'Alert when Cosmos DB queries exceed 5 seconds'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT5M'
    scopes: [logAnalyticsWorkspaceId]
    windowSize: 'PT15M'
    criteria: {
      allOf: [
        {
          query: '''
            dependencies
            | where timestamp > ago(15m)
            | where type == "Azure DocumentDB"
            | where duration > 5000
            | summarize SlowQueries = count()
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 5
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [finalActionGroupId]
    }
  }
}

// Alert: Service Unavailable(503)
resource serviceUnavailableAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'service-unavailable'
  location: resourceGroup().location
  tags: commonTags
  properties: {
    displayName: 'Service Unavailable'
    description: 'Alert when a service returns 503 errors'
    severity: 0  // Critical
    enabled: true
    evaluationFrequency: 'PT1M'  // Check every minute
    scopes: [logAnalyticsWorkspaceId]
    windowSize: 'PT5M'
    criteria: {
      allOf: [
        {
          query: '''
            requests
            | where timestamp > ago(5m)
            | where resultCode == "503"
            | summarize Count = count() by cloud_RoleName
            | where Count > 3
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [finalActionGroupId]
    }
  }
}
