# Session 8: Log Analytics & KQL Mastery

## 📋 Session Details
- **Duration**: 1 hour
- **Week**: 2, Day 3 (Wednesday)
- **Prerequisites**: Sessions 1-7 completed
- **Deliverable**: KQL query library and saved queries

---

## 🎯 Learning Objectives

By the end of this session, you will:
1. Master KQL (Kusto Query Language) fundamentals
2. Write complex queries for troubleshooting
3. Create and save reusable queries
4. Build custom dashboards

---

## 📚 KQL Fundamentals

### Query Structure

```kql
TableName                    // 1. Start with a table
| where Condition            // 2. Filter rows
| extend NewColumn = Expr    // 3. Add calculated columns
| summarize Aggregation      // 4. Group and aggregate
| project Column1, Column2   // 5. Select columns
| order by Column desc       // 6. Sort results
| take N                     // 7. Limit rows
```

### Common Tables

| Table | Description |
|-------|-------------|
| `requests` | HTTP requests to your app |
| `dependencies` | Calls to external services |
| `exceptions` | Unhandled exceptions |
| `traces` | Log messages |
| `customEvents` | Custom telemetry events |
| `customMetrics` | Custom metrics |
| `performanceCounters` | System metrics |
| `availabilityResults` | Availability test results |

---

## 🛠️ Hands-On Exercise

### Step 1: Basic Queries

```kql
// Query 1: Recent requests
requests
| where timestamp > ago(1h)
| project timestamp, name, duration, success, resultCode
| order by timestamp desc
| take 100

// Query 2: Filter by service
requests
| where timestamp > ago(1h)
| where cloud_RoleName == "catalog-service"
| summarize count() by resultCode

// Query 3: Search in logs
traces
| where timestamp > ago(1h)
| where message contains "error" or severityLevel >= 3
| project timestamp, message, severityLevel
| order by timestamp desc

// Query 4: Time-based filtering
requests
| where timestamp between (datetime(2025-01-01) .. datetime(2025-01-02))
| summarize count() by bin(timestamp, 1h)
| render timechart
```

### Step 2: Aggregation Queries

```kql
// Query 5: Percentile analysis
requests
| where timestamp > ago(1h)
| summarize 
    Count = count(),
    Avg = avg(duration),
    P50 = percentile(duration, 50),
    P90 = percentile(duration, 90),
    P95 = percentile(duration, 95),
    P99 = percentile(duration, 99),
    Max = max(duration)
| project-reorder Count, Avg, P50, P90, P95, P99, Max

// Query 6: Group by multiple dimensions
requests
| where timestamp > ago(1h)
| summarize 
    Count = count(),
    AvgDuration = avg(duration),
    FailureRate = 100.0 * countif(success == false) / count()
by cloud_RoleName, name
| order by FailureRate desc

// Query 7: Time bucketing
requests
| where timestamp > ago(24h)
| summarize 
    RequestCount = count(),
    ErrorCount = countif(success == false)
by bin(timestamp, 1h)
| extend ErrorRate = 100.0 * ErrorCount / RequestCount
| project timestamp, RequestCount, ErrorRate
| render timechart

// Query 8: Running totals
requests
| where timestamp > ago(24h)
| summarize Count = count() by bin(timestamp, 1h)
| order by timestamp asc
| extend RunningTotal = row_cumsum(Count)
```

### Step 3: Join and Correlation Queries

```kql
// Query 9: Correlate requests with dependencies
let operation = "YOUR_OPERATION_ID";
requests
| where operation_Id == operation
| project 
    Type = "Request",
    timestamp,
    name,
    duration,
    success
| union (
    dependencies
    | where operation_Id == operation
    | project 
        Type = "Dependency",
        timestamp,
        name,
        duration,
        success
)
| order by timestamp asc

// Query 10: Join requests with exceptions
requests
| where timestamp > ago(1h)
| where success == false
| join kind=leftouter (
    exceptions
    | where timestamp > ago(1h)
    | project operation_Id, ExceptionType = type, ExceptionMessage = outerMessage
) on operation_Id
| project timestamp, name, resultCode, ExceptionType, ExceptionMessage

// Query 11: End-to-end transaction analysis
let trace_id = "YOUR_TRACE_ID";
union 
    (requests | where operation_Id == trace_id),
    (dependencies | where operation_Id == trace_id),
    (traces | where operation_Id == trace_id),
    (exceptions | where operation_Id == trace_id)
| project 
    timestamp,
    itemType,
    name = coalesce(name, message),
    duration,
    success
| order by timestamp asc
```

### Step 4: Performance Analysis Queries

```kql
// Query 12: Slow dependency detection
dependencies
| where timestamp > ago(1h)
| where duration > 1000  // > 1 second
| summarize 
    SlowCalls = count(),
    AvgDuration = avg(duration),
    MaxDuration = max(duration)
by type, target, name
| order by SlowCalls desc

// Query 13: Error pattern analysis
exceptions
| where timestamp > ago(24h)
| summarize Count = count() by type, bin(timestamp, 1h)
| render timechart

// Query 14: Service latency comparison
requests
| where timestamp > ago(1h)
| summarize 
    P50 = percentile(duration, 50),
    P95 = percentile(duration, 95)
by cloud_RoleName
| render barchart

// Query 15: Anomaly detection (static threshold)
requests
| where timestamp > ago(1h)
| summarize AvgDuration = avg(duration) by bin(timestamp, 5m), name
| where AvgDuration > 500  // Threshold: 500ms
| project timestamp, name, AvgDuration
```

### Step 5: Custom Metrics Queries

```kql
// Query 16: Business metrics from custom events
customEvents
| where timestamp > ago(24h)
| where name == "order_created"
| extend 
    orderId = tostring(customDimensions["order_id"]),
    total = todouble(customDimensions["total"]),
    items = toint(customDimensions["item_count"])
| summarize 
    OrderCount = count(),
    TotalRevenue = sum(total),
    AvgOrderValue = avg(total),
    AvgItems = avg(items)
by bin(timestamp, 1h)

// Query 17: Product search analytics
customEvents
| where timestamp > ago(24h)
| where name == "product_searched"
| extend 
    query = tostring(customDimensions["query"]),
    results = toint(customDimensions["results_count"])
| summarize 
    SearchCount = count(),
    AvgResults = avg(results),
    ZeroResults = countif(results == 0)
by query
| order by SearchCount desc
| take 20

// Query 18: Conversion funnel
let productViews = customEvents
| where name == "products_viewed"
| summarize ProductViews = count();
let cartAdds = customEvents
| where name == "cart_item_added"
| summarize CartAdds = count();
let orders = customEvents
| where name == "order_created"
| summarize Orders = count();
productViews
| extend CartAdds = toscalar(cartAdds)
| extend Orders = toscalar(orders)
| project 
    Stage = "Product Views", Count = ProductViews
| union (
    cartAdds | extend Stage = "Cart Adds" | project Stage, Count = CartAdds
)
| union (
    orders | extend Stage = "Orders" | project Stage, Count = Orders
)
```

### Step 6: Create Saved Queries

In Azure Portal → Log Analytics → Queries:

```kql
// Save as: "Service Health Overview"
// Category: Performance
let timeRange = ago(1h);
requests
| where timestamp > timeRange
| summarize 
    Requests = count(),
    Failures = countif(success == false),
    AvgLatency = avg(duration),
    P95Latency = percentile(duration, 95)
by cloud_RoleName
| extend FailureRate = round(100.0 * Failures / Requests, 2)
| project 
    Service = cloud_RoleName,
    Requests,
    Failures,
    FailureRate,
    AvgLatency = round(AvgLatency, 0),
    P95Latency = round(P95Latency, 0)
| order by Requests desc

// Save as: "Dependency Health"
// Category: Dependencies
dependencies
| where timestamp > ago(1h)
| summarize 
    Calls = count(),
    Failures = countif(success == false),
    AvgDuration = avg(duration)
by type, target
| extend FailureRate = round(100.0 * Failures / Calls, 2)
| order by Calls desc

// Save as: "Recent Errors"
// Category: Errors
exceptions
| where timestamp > ago(1h)
| project 
    timestamp,
    Service = cloud_RoleName,
    Type = type,
    Message = outerMessage,
    OperationId = operation_Id
| order by timestamp desc
| take 50

// Save as: "Slow Requests (> 1s)"
// Category: Performance
requests
| where timestamp > ago(1h)
| where duration > 1000
| project 
    timestamp,
    Service = cloud_RoleName,
    Endpoint = name,
    Duration = round(duration, 0),
    Success = success,
    OperationId = operation_Id
| order by Duration desc
| take 100
```

### Step 7: Create Query Functions

```kql
// Create reusable function for service stats
.create-or-alter function ServiceStats(serviceName:string, lookback:timespan) {
    requests
    | where timestamp > ago(lookback)
    | where cloud_RoleName == serviceName
    | summarize 
        Requests = count(),
        AvgDuration = avg(duration),
        P95Duration = percentile(duration, 95),
        FailureRate = 100.0 * countif(success == false) / count()
}

// Usage:
ServiceStats("catalog-service", 1h)

// Create function for error trend
.create-or-alter function ErrorTrend(lookback:timespan, interval:timespan) {
    exceptions
    | where timestamp > ago(lookback)
    | summarize Count = count() by Type = type, bin(timestamp, interval)
    | order by timestamp asc
}

// Usage:
ErrorTrend(24h, 1h)
| render timechart
```

---

## 📊 Building a Dashboard

### Dashboard Tiles Query Examples

```kql
// Tile 1: Total Requests (Single Value)
requests
| where timestamp > ago(1h)
| count

// Tile 2: Error Rate (Single Value)
requests
| where timestamp > ago(1h)
| summarize ErrorRate = round(100.0 * countif(success == false) / count(), 2)

// Tile 3: Request Trend (Time Chart)
requests
| where timestamp > ago(24h)
| summarize Count = count() by bin(timestamp, 1h)
| render timechart

// Tile 4: Top Endpoints (Bar Chart)
requests
| where timestamp > ago(1h)
| summarize Count = count() by name
| top 10 by Count
| render barchart

// Tile 5: Service Distribution (Pie Chart)
requests
| where timestamp > ago(1h)
| summarize Count = count() by cloud_RoleName
| render piechart

// Tile 6: Latency Heatmap (Scatter Chart)
requests
| where timestamp > ago(1h)
| project timestamp, duration, name
| render scatterchart
```

---

## 🧪 Verification Checklist

Before moving to the next session, ensure you have:

- [ ] Written and tested 15+ KQL queries
- [ ] Saved reusable queries in Log Analytics
- [ ] Created a dashboard with 6+ tiles
- [ ] Understand join, summarize, and extend operators
- [ ] Can trace requests end-to-end with operation_Id

---

## 📖 Key Takeaways

1. **KQL is powerful** for log analysis and troubleshooting
2. **Percentiles** (P50, P95, P99) are better than averages for latency
3. **Saved queries** enable team knowledge sharing
4. **Dashboards** provide real-time visibility into system health

---

## 🔜 Next Session Preview

**Session 9: Alerting & Dashboards**
- Configure metric and log alerts
- Create Azure Workbooks
- Set up action groups for notifications

---

## 📚 Additional Resources

- [KQL Quick Reference](https://docs.microsoft.com/en-us/azure/data-explorer/kql-quick-reference)
- [Log Analytics Tutorial](https://docs.microsoft.com/en-us/azure/azure-monitor/logs/log-analytics-tutorial)
- [Azure Workbooks](https://docs.microsoft.com/en-us/azure/azure-monitor/visualize/workbooks-overview)
