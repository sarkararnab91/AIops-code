# Session 9: Alerting & Dashboards

##  Session Details
- **Duration**: 1 hour
- **Week**: 2, Day 4 
- **Prerequisites**: Sessions 1-8 completed
- **Deliverable**: Azure alerts and workbooks configured

---

##  Learning Objectives

By the end of this session, you will:
1. Configure metric-based alerts
2. Create log-based (KQL) alerts
3. Set up action groups for notifications
4. Build Azure Workbooks for dashboards

---

##  Concepts

### Alert Types

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AZURE MONITOR ALERTS                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   METRIC ALERTS              LOG ALERTS               SMART DETECTION       │
│   ┌──────────────┐          ┌──────────────┐         ┌──────────────┐      │
│   │ • CPU > 80%  │          │ • Error rate │         │ • Anomaly    │      │
│   │ • Memory %   │          │   > threshold│         │   detection  │      │
│   │ • Response   │          │ • Exception  │         │ • Failure    │      │
│   │   time       │          │   patterns   │         │   analytics  │      │
│   │ • Queue depth│          │ • Custom KQL │         │ • Dependency │      │
│   └──────────────┘          └──────────────┘         │   issues     │      │
│                                                      └──────────────┘      │
│   Evaluation: 1-5 min       Evaluation: 5-15 min     Automatic, ML-based   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Alert Severity Levels

| Severity | Name | Use Case |
|----------|------|----------|
| 0 | Critical | Complete outage, data loss |
| 1 | Error | Service degradation, high error rate |
| 2 | Warning | Performance issues, approaching limits |
| 3 | Informational | Notable events, non-urgent |
| 4 | Verbose | Debugging, detailed tracking |

---

##  Hands-On Exercise

### Step 1: Create Alert Rules with Bicep

Create `ecommerce-app/infrastructure/bicep/alerts.bicep`:

```bicep
// Azure Monitor Alert Rules
// Configure alerts for e-commerce services

@description('Application Insights resource ID')
param appInsightsId string

@description('Log Analytics workspace ID')
param logAnalyticsWorkspaceId string

@description('Action group resource ID')
param actionGroupId string

@description('Environment tag')
param environment string = 'training'

// Common tags
var commonTags = {
  Project: 'aiops-training'
  Environment: environment
  ManagedBy: 'bicep'
}

// ============================================================
// ACTION GROUP
// ============================================================
resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
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
    // Add webhook for integration with ticketing systems
    webhookReceivers: [
      {
        name: 'ServiceNow Webhook'
        serviceUri: 'https://your-servicenow-instance/webhook'
        useCommonAlertSchema: true
      }
    ]
  }
}

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
        actionGroupId: actionGroup.id
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
        actionGroupId: actionGroup.id
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
        actionGroupId: actionGroup.id
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
      actionGroups: [actionGroup.id]
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
      actionGroups: [actionGroup.id]
    }
  }
}

// Alert: Service Unavailable
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
      actionGroups: [actionGroup.id]
    }
  }
}

// Alert: Order Processing Failures
resource orderFailuresAlert 'Microsoft.Insights/scheduledQueryRules@2022-06-15' = {
  name: 'order-processing-failures'
  location: resourceGroup().location
  tags: commonTags
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

// Outputs
output actionGroupId string = actionGroup.id
```

### Step 2: Deploy Alerts

```bash
# Deploy alerts
az deployment group create \
  --resource-group aiops-training-rg \
  --template-file ecommerce-app/infrastructure/bicep/alerts.bicep \
  --parameters \
    appInsightsId="/subscriptions/XXX/resourceGroups/aiops-training-rg/providers/microsoft.insights/components/aiops-appinsights" \
    logAnalyticsWorkspaceId="/subscriptions/XXX/resourceGroups/aiops-training-rg/providers/Microsoft.OperationalInsights/workspaces/aiops-aks-logs"
```

### Step 3: Create Azure Workbook

Create `ecommerce-app/monitoring/workbooks/service-health-workbook.json`:

```json
{
  "version": "Notebook/1.0",
  "items": [
    {
      "type": 1,
      "content": {
        "json": "# 🛒 E-Commerce Service Health Dashboard\n\nReal-time monitoring of all microservices in the Perfume & Dessert e-commerce platform."
      },
      "name": "header"
    },
    {
      "type": 9,
      "content": {
        "version": "KqlParameterItem/1.0",
        "parameters": [
          {
            "name": "TimeRange",
            "type": 4,
            "isRequired": true,
            "value": {
              "durationMs": 3600000
            },
            "typeSettings": {
              "selectableValues": [
                { "durationMs": 300000, "displayName": "Last 5 minutes" },
                { "durationMs": 900000, "displayName": "Last 15 minutes" },
                { "durationMs": 1800000, "displayName": "Last 30 minutes" },
                { "durationMs": 3600000, "displayName": "Last 1 hour" },
                { "durationMs": 14400000, "displayName": "Last 4 hours" },
                { "durationMs": 86400000, "displayName": "Last 24 hours" }
              ]
            }
          }
        ]
      },
      "name": "parameters"
    },
    {
      "type": 3,
      "content": {
        "version": "KqlItem/1.0",
        "query": "requests\n| where timestamp > ago(1h)\n| summarize Requests = count(), Failures = countif(success == false)\n| extend SuccessRate = round(100.0 * (Requests - Failures) / Requests, 1)",
        "size": 4,
        "title": "Overall Health",
        "queryType": 0,
        "visualization": "tiles",
        "tileSettings": {
          "showBorder": false,
          "titleContent": {
            "columnMatch": "Requests"
          }
        }
      },
      "name": "overall-health"
    },
    {
      "type": 3,
      "content": {
        "version": "KqlItem/1.0",
        "query": "requests\n| where timestamp > {TimeRange:query}\n| summarize \n    Requests = count(),\n    Failures = countif(success == false),\n    AvgLatency = round(avg(duration), 0),\n    P95Latency = round(percentile(duration, 95), 0)\n    by Service = cloud_RoleName\n| extend FailureRate = round(100.0 * Failures / Requests, 2)\n| order by Requests desc",
        "size": 0,
        "title": "Service Performance",
        "queryType": 0,
        "visualization": "table",
        "gridSettings": {
          "formatters": [
            {
              "columnMatch": "FailureRate",
              "formatter": 8,
              "formatOptions": {
                "palette": "redGreen"
              }
            },
            {
              "columnMatch": "AvgLatency",
              "formatter": 8,
              "formatOptions": {
                "palette": "blue"
              }
            }
          ]
        }
      },
      "name": "service-performance"
    },
    {
      "type": 3,
      "content": {
        "version": "KqlItem/1.0",
        "query": "requests\n| where timestamp > {TimeRange:query}\n| summarize Count = count() by bin(timestamp, 5m), cloud_RoleName\n| render timechart",
        "size": 0,
        "title": "Request Volume by Service",
        "queryType": 0,
        "visualization": "timechart"
      },
      "name": "request-volume"
    },
    {
      "type": 3,
      "content": {
        "version": "KqlItem/1.0",
        "query": "requests\n| where timestamp > {TimeRange:query}\n| summarize ErrorRate = 100.0 * countif(success == false) / count() by bin(timestamp, 5m)\n| render timechart",
        "size": 0,
        "title": "Error Rate Trend",
        "queryType": 0,
        "visualization": "timechart"
      },
      "name": "error-rate-trend"
    },
    {
      "type": 3,
      "content": {
        "version": "KqlItem/1.0",
        "query": "dependencies\n| where timestamp > {TimeRange:query}\n| summarize \n    Calls = count(),\n    Failures = countif(success == false),\n    AvgDuration = round(avg(duration), 0)\n    by type, target\n| extend FailureRate = round(100.0 * Failures / Calls, 2)\n| order by Calls desc",
        "size": 0,
        "title": "Dependency Health",
        "queryType": 0,
        "visualization": "table"
      },
      "name": "dependency-health"
    },
    {
      "type": 3,
      "content": {
        "version": "KqlItem/1.0",
        "query": "exceptions\n| where timestamp > {TimeRange:query}\n| summarize Count = count() by type\n| order by Count desc\n| take 10",
        "size": 0,
        "title": "Top Exceptions",
        "queryType": 0,
        "visualization": "piechart"
      },
      "name": "top-exceptions"
    }
  ]
}
```

### Step 4: Deploy Workbook via Azure CLI

```bash
# Create workbook
az monitor workbook create \
  --resource-group aiops-training-rg \
  --name "E-Commerce Service Health" \
  --display-name "E-Commerce Service Health" \
  --serialized-data @ecommerce-app/monitoring/workbooks/service-health-workbook.json \
  --category workbook
```

---

##  Verification Checklist

Before moving to the next session, ensure you have:

- [ ] Action group created with email receiver
- [ ] 3+ metric alerts configured
- [ ] 4+ log-based (KQL) alerts configured
- [ ] Workbook deployed with 6+ tiles
- [ ] Test alert firing (lower threshold temporarily)

---

## 📖 Key Takeaways

1. **Metric alerts** are faster (1-5 min) but less flexible
2. **Log alerts** support complex KQL queries but slower (5-15 min)
3. **Action groups** centralize notification configuration
4. **Workbooks** provide interactive dashboards with parameters

---

## 🔜 Next Session Preview

**Session 10: Distributed Tracing**
- End-to-end request correlation
- Trace analysis and debugging
- Performance bottleneck identification

---

## 📚 Additional Resources

- [Azure Monitor Alerts](https://docs.microsoft.com/en-us/azure/azure-monitor/alerts/alerts-overview)
- [Azure Workbooks](https://docs.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-overview)
- [Action Groups](https://docs.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups)
