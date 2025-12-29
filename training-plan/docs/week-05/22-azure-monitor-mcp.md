# Session 22: Azure Monitor Integration for MCP

## Learning Objectives
- Integrate real Azure Monitor with MCP
- Implement metric and log queries
- Build real-time health monitoring tools
- Handle authentication securely

## Duration: 1 hour

---

## 1. Azure Monitor MCP Tools

### Azure Monitor Tool Implementation

```python
# File: training-plan/mcp-server/src/aiops_mcp/tools/azure_monitor.py
"""
Azure Monitor integration for MCP server.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from azure.identity import DefaultAzureCredential, ClientSecretCredential
from azure.monitor.query import LogsQueryClient, MetricsQueryClient
from azure.monitor.query import LogsQueryStatus


@dataclass
class AzureMonitorConfig:
    """Configuration for Azure Monitor."""
    workspace_id: str
    subscription_id: str
    resource_group: str
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'AzureMonitorConfig':
        """Load configuration from environment variables."""
        return cls(
            workspace_id=os.getenv("AZURE_LOG_ANALYTICS_WORKSPACE_ID", ""),
            subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID", ""),
            resource_group=os.getenv("AZURE_RESOURCE_GROUP", ""),
            tenant_id=os.getenv("AZURE_TENANT_ID"),
            client_id=os.getenv("AZURE_CLIENT_ID"),
            client_secret=os.getenv("AZURE_CLIENT_SECRET"),
        )


class AzureMonitorClient:
    """
    Client for Azure Monitor queries.
    """
    
    def __init__(self, config: AzureMonitorConfig):
        self.config = config
        self.credential = self._get_credential()
        self.logs_client = LogsQueryClient(self.credential)
        self.metrics_client = MetricsQueryClient(self.credential)
    
    def _get_credential(self):
        """Get Azure credential."""
        if self.config.client_id and self.config.client_secret and self.config.tenant_id:
            return ClientSecretCredential(
                tenant_id=self.config.tenant_id,
                client_id=self.config.client_id,
                client_secret=self.config.client_secret
            )
        return DefaultAzureCredential()
    
    async def query_logs(
        self,
        query: str,
        timespan: str = "PT1H"
    ) -> Dict[str, Any]:
        """
        Execute a KQL query against Log Analytics.
        
        Args:
            query: KQL query string
            timespan: ISO 8601 duration (e.g., PT1H, P1D)
            
        Returns:
            Query results as dictionary
        """
        try:
            # Parse timespan
            duration = self._parse_timespan(timespan)
            
            response = self.logs_client.query_workspace(
                workspace_id=self.config.workspace_id,
                query=query,
                timespan=duration
            )
            
            if response.status == LogsQueryStatus.SUCCESS:
                results = []
                for table in response.tables:
                    columns = [col.name for col in table.columns]
                    for row in table.rows:
                        row_dict = {}
                        for i, value in enumerate(row):
                            # Handle datetime serialization
                            if isinstance(value, datetime):
                                row_dict[columns[i]] = value.isoformat()
                            else:
                                row_dict[columns[i]] = value
                        results.append(row_dict)
                
                return {
                    "status": "success",
                    "row_count": len(results),
                    "results": results[:100],  # Limit to 100 rows
                    "query": query,
                    "timespan": timespan
                }
            else:
                return {
                    "status": "partial",
                    "message": "Query returned partial results",
                    "results": []
                }
        
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "query": query
            }
    
    async def get_service_metrics(
        self,
        service_name: str,
        timespan: str = "PT1H"
    ) -> Dict[str, Any]:
        """
        Get metrics for a specific service.
        """
        # Build KQL query for service metrics
        query = f"""
        let service = "{service_name}";
        let timeRange = {timespan};
        
        // Request metrics
        AppRequests
        | where TimeGenerated > ago(timeRange)
        | where AppRoleName contains service or Name contains service
        | summarize 
            RequestCount = count(),
            AvgDuration = avg(DurationMs),
            P50Duration = percentile(DurationMs, 50),
            P95Duration = percentile(DurationMs, 95),
            P99Duration = percentile(DurationMs, 99),
            FailedCount = countif(Success == false)
            by bin(TimeGenerated, 5m)
        | order by TimeGenerated desc
        """
        
        return await self.query_logs(query, timespan)
    
    async def get_service_health(
        self,
        service_name: str,
        timespan: str = "PT1H"
    ) -> Dict[str, Any]:
        """
        Get comprehensive health status for a service.
        """
        duration = self._parse_timespan(timespan)
        
        # Get multiple metrics
        queries = {
            "requests": f"""
                AppRequests
                | where TimeGenerated > ago({timespan})
                | where AppRoleName contains "{service_name}"
                | summarize 
                    TotalRequests = count(),
                    FailedRequests = countif(Success == false),
                    AvgLatency = avg(DurationMs),
                    P99Latency = percentile(DurationMs, 99)
            """,
            "dependencies": f"""
                AppDependencies
                | where TimeGenerated > ago({timespan})
                | where AppRoleName contains "{service_name}"
                | summarize 
                    TotalCalls = count(),
                    FailedCalls = countif(Success == false),
                    AvgDuration = avg(DurationMs)
                    by DependencyType, Target
            """,
            "exceptions": f"""
                AppExceptions
                | where TimeGenerated > ago({timespan})
                | where AppRoleName contains "{service_name}"
                | summarize Count = count() by ExceptionType, ProblemId
                | top 5 by Count
            """
        }
        
        results = {}
        for name, query in queries.items():
            results[name] = await self.query_logs(query, timespan)
        
        # Calculate health score
        request_data = results.get("requests", {}).get("results", [{}])[0] if results.get("requests", {}).get("results") else {}
        
        total = request_data.get("TotalRequests", 0)
        failed = request_data.get("FailedRequests", 0)
        latency_p99 = request_data.get("P99Latency", 0)
        
        error_rate = failed / total if total > 0 else 0
        availability = 1 - error_rate
        
        # Health score (0-100)
        health_score = 100
        if error_rate > 0.01:
            health_score -= min(error_rate * 100, 30)
        if latency_p99 > 500:
            health_score -= min((latency_p99 - 500) / 50, 30)
        
        health_status = "healthy" if health_score >= 80 else "degraded" if health_score >= 50 else "unhealthy"
        
        return {
            "service": service_name,
            "status": health_status,
            "health_score": round(health_score, 2),
            "metrics": {
                "total_requests": total,
                "failed_requests": failed,
                "error_rate": round(error_rate, 4),
                "availability": round(availability, 4),
                "avg_latency_ms": round(request_data.get("AvgLatency", 0), 2),
                "p99_latency_ms": round(latency_p99, 2)
            },
            "dependencies": results.get("dependencies", {}).get("results", []),
            "top_exceptions": results.get("exceptions", {}).get("results", []),
            "timespan": timespan,
            "timestamp": datetime.now().isoformat()
        }
    
    async def detect_anomalies_kql(
        self,
        service_name: str,
        metric: str = "latency",
        timespan: str = "PT4H"
    ) -> Dict[str, Any]:
        """
        Detect anomalies using KQL's built-in functions.
        """
        if metric == "latency":
            query = f"""
                AppRequests
                | where TimeGenerated > ago({timespan})
                | where AppRoleName contains "{service_name}"
                | summarize AvgLatency = avg(DurationMs) by bin(TimeGenerated, 5m)
                | extend LatencyAnomaly = series_decompose_anomalies(pack_array(AvgLatency), 1.5)
                | mv-expand TimeGenerated, AvgLatency, LatencyAnomaly
                | where LatencyAnomaly != 0
                | project TimeGenerated, AvgLatency, AnomalyType = iff(LatencyAnomaly > 0, "spike", "dip")
            """
        elif metric == "errors":
            query = f"""
                AppRequests
                | where TimeGenerated > ago({timespan})
                | where AppRoleName contains "{service_name}"
                | summarize 
                    Requests = count(),
                    Errors = countif(Success == false)
                    by bin(TimeGenerated, 5m)
                | extend ErrorRate = Errors * 100.0 / Requests
                | extend ErrorAnomaly = series_decompose_anomalies(pack_array(ErrorRate), 2.0)
                | mv-expand TimeGenerated, ErrorRate, ErrorAnomaly
                | where ErrorAnomaly != 0
            """
        else:
            return {"error": f"Unknown metric: {metric}"}
        
        result = await self.query_logs(query, timespan)
        
        anomalies = result.get("results", [])
        
        return {
            "service": service_name,
            "metric": metric,
            "timespan": timespan,
            "anomalies_detected": len(anomalies) > 0,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:10],
            "analysis_time": datetime.now().isoformat()
        }
    
    async def get_traces(
        self,
        trace_id: Optional[str] = None,
        service_name: Optional[str] = None,
        timespan: str = "PT1H"
    ) -> Dict[str, Any]:
        """
        Get distributed traces.
        """
        filters = []
        if trace_id:
            filters.append(f'OperationId == "{trace_id}"')
        if service_name:
            filters.append(f'AppRoleName contains "{service_name}"')
        
        where_clause = " and ".join(filters) if filters else "true"
        
        query = f"""
            union AppRequests, AppDependencies
            | where TimeGenerated > ago({timespan})
            | where {where_clause}
            | project 
                TimeGenerated,
                OperationId,
                ParentId,
                Id,
                Name,
                AppRoleName,
                DurationMs,
                Success,
                Type = case(
                    itemType == "request", "request",
                    itemType == "dependency", "dependency",
                    "unknown"
                )
            | order by TimeGenerated asc
        """
        
        result = await self.query_logs(query, timespan)
        
        # Group by operation ID
        traces = {}
        for span in result.get("results", []):
            op_id = span.get("OperationId")
            if op_id not in traces:
                traces[op_id] = []
            traces[op_id].append(span)
        
        return {
            "trace_count": len(traces),
            "traces": dict(list(traces.items())[:10]),  # Limit to 10 traces
            "timespan": timespan
        }
    
    def _parse_timespan(self, timespan: str) -> timedelta:
        """Parse ISO 8601 duration to timedelta."""
        # Simple parser for common formats
        if timespan.startswith("PT"):
            timespan = timespan[2:]
            if timespan.endswith("H"):
                return timedelta(hours=int(timespan[:-1]))
            elif timespan.endswith("M"):
                return timedelta(minutes=int(timespan[:-1]))
            elif timespan.endswith("S"):
                return timedelta(seconds=int(timespan[:-1]))
        elif timespan.startswith("P"):
            timespan = timespan[1:]
            if timespan.endswith("D"):
                return timedelta(days=int(timespan[:-1]))
        
        return timedelta(hours=1)  # Default


# Singleton instance
_azure_client: Optional[AzureMonitorClient] = None


def get_azure_monitor_client() -> AzureMonitorClient:
    """Get or create Azure Monitor client."""
    global _azure_client
    
    if _azure_client is None:
        config = AzureMonitorConfig.from_env()
        _azure_client = AzureMonitorClient(config)
    
    return _azure_client
```

---

## 2. MCP Tool Handler Integration

### Updating the MCP Server

```python
# File: training-plan/mcp-server/src/aiops_mcp/tools/__init__.py
"""
MCP Tool implementations.
"""

from .azure_monitor import (
    AzureMonitorClient,
    AzureMonitorConfig,
    get_azure_monitor_client
)


async def query_azure_monitor(args: dict) -> dict:
    """Execute Azure Monitor query."""
    client = get_azure_monitor_client()
    
    query = args.get("query", "")
    timespan = args.get("timespan", "PT1H")
    
    return await client.query_logs(query, timespan)


async def get_service_health(args: dict) -> dict:
    """Get service health status."""
    client = get_azure_monitor_client()
    
    service_name = args.get("service_name", "")
    timespan = args.get("timespan", "PT1H")
    
    return await client.get_service_health(service_name, timespan)


async def detect_anomalies(args: dict) -> dict:
    """Detect anomalies in service metrics."""
    client = get_azure_monitor_client()
    
    service_name = args.get("service_name", "")
    metrics = args.get("metrics", ["latency"])
    timespan = args.get("timespan", "PT1H")
    
    results = {}
    for metric in metrics:
        results[metric] = await client.detect_anomalies_kql(
            service_name, metric, timespan
        )
    
    # Aggregate results
    all_anomalies = []
    for metric, result in results.items():
        if result.get("anomalies_detected"):
            all_anomalies.extend([
                {**a, "metric": metric}
                for a in result.get("anomalies", [])
            ])
    
    return {
        "service": service_name,
        "anomalies_detected": len(all_anomalies) > 0,
        "total_anomalies": len(all_anomalies),
        "anomalies": all_anomalies,
        "per_metric_results": results,
        "analysis_time": datetime.now().isoformat()
    }


async def get_traces(args: dict) -> dict:
    """Get distributed traces."""
    client = get_azure_monitor_client()
    
    return await client.get_traces(
        trace_id=args.get("trace_id"),
        service_name=args.get("service_name"),
        timespan=args.get("timespan", "PT1H")
    )
```

---

## 3. Key Takeaways

1. **Azure SDK**: Use official SDKs for reliable integration
2. **KQL Queries**: Powerful query language for logs and metrics
3. **Health Scoring**: Combine multiple metrics for overall health
4. **Anomaly Detection**: Use built-in KQL functions
5. **Error Handling**: Always handle API failures gracefully

## Next Session Preview
- Session 23: ServiceNow Simulation Integration
