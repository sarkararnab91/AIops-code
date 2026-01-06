// Alerts Module - Azure Monitor alerts for proactive monitoring
// Includes metric and log-based alerts

@description('Application Insights resource ID')
param appInsightsId string

@description('Log Analytics workspace ID')
param logAnalyticsWorkspaceId string

@description('Location for alert resources')
param location string

@description('Resource tags')
param tags object

@description('Email addresses for alert notifications')
param alertEmailAddresses array = ['training-alerts@example.com']

// ============================================================
// ACTION GROUP
// ============================================================

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'aiops-training-alerts'
  location: 'Global'
  tags: tags
  properties: {
    groupShortName: 'AIOps'
    enabled: true
    emailReceivers: [for (email, i) in alertEmailAddresses: {
      name: 'EmailReceiver${i}'
      emailAddress: email
      useCommonAlertSchema: true
    }]
  }
}

// ============================================================
// METRIC ALERTS
// ============================================================

// High Error Rate Alert
resource highErrorRateAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'high-error-rate'
  location: 'Global'
  tags: tags
  properties: {
    description: 'Alert when failed request count exceeds threshold'
    severity: 1
    enabled: true
    scopes: [appInsightsId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'FailedRequests'
          metricName: 'requests/failed'
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
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// High Response Time Alert
resource highLatencyAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'high-response-time'
  location: 'Global'
  tags: tags
  properties: {
    description: 'Alert when average response time exceeds 2 seconds'
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
          threshold: 2000
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// Dependency Failures Alert
resource dependencyFailureAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'dependency-failures'
  location: 'Global'
  tags: tags
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
          threshold: 5
          timeAggregation: 'Count'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

// ============================================================
// LOG-BASED (KQL) ALERTS
// ============================================================

// Exception Spike Alert
resource exceptionSpikeAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'exception-spike'
  location: location
  tags: tags
  properties: {
    displayName: 'Exception Spike Detected'
    description: 'Alert when exception count spikes above normal levels'
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
            | summarize ExceptionCount = count()
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 50
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// Service Unavailable (503) Alert
resource serviceUnavailableAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'service-unavailable'
  location: location
  tags: tags
  properties: {
    displayName: 'Service Unavailable (503 Errors)'
    description: 'Alert when services return 503 errors'
    severity: 0
    enabled: true
    evaluationFrequency: 'PT1M'
    scopes: [logAnalyticsWorkspaceId]
    windowSize: 'PT5M'
    criteria: {
      allOf: [
        {
          query: '''
            requests
            | where timestamp > ago(5m)
            | where resultCode == "503"
            | summarize Count = count()
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 3
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// Slow Database Queries Alert
resource slowDbQueriesAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'slow-database-queries'
  location: location
  tags: tags
  properties: {
    displayName: 'Slow Database Queries'
    description: 'Alert when database queries exceed 5 seconds'
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
      actionGroups: [actionGroup.id]
    }
  }
}

// Order Processing Failures Alert
resource orderFailuresAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'order-processing-failures'
  location: location
  tags: tags
  properties: {
    displayName: 'Order Processing Failures'
    description: 'Alert on order creation or payment failures'
    severity: 1
    enabled: true
    evaluationFrequency: 'PT5M'
    scopes: [logAnalyticsWorkspaceId]
    windowSize: 'PT15M'
    criteria: {
      allOf: [
        {
          query: '''
            requests
            | where timestamp > ago(15m)
            | where name has "orders" or name has "payments"
            | where success == false
            | summarize FailedOrders = count()
          '''
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 3
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output actionGroupId string = actionGroup.id
output actionGroupName string = actionGroup.name
