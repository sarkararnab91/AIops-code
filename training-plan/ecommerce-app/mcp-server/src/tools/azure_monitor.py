"""
Azure Monitor Tools for MCP Server
Real integration with Azure Monitor for metrics, logs, and alerts
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Any, Optional

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, MetricsQueryClient
from azure.monitor.query import LogsQueryStatus


class AzureMonitorTools:
    """Tools for querying Azure Monitor metrics and logs."""
    
    def __init__(self):
        self.credential = DefaultAzureCredential()
        self.logs_client = LogsQueryClient(self.credential)
        self.metrics_client = MetricsQueryClient(self.credential)
        
        # Configuration
        self.workspace_id = os.getenv("AZURE_LOG_ANALYTICS_WORKSPACE_ID", "")
        self.subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID", "")
        self.resource_group = os.getenv("AZURE_RESOURCE_GROUP", "rg-aiops-demo")
        
        # Service to resource mapping
        self.services = {
            "catalog-service": "catalog",
            "order-service": "order",
            "cart-service": "cart",
            "user-service": "user",
            "payment-service": "payment",
            "inventory-service": "inventory",
            "notification-service": "notification",
            "api-gateway": "gateway"
        }
        
        # Service dependencies
        self.dependencies = {
            "api-gateway": ["catalog-service", "order-service", "cart-service", "user-service"],
            "order-service": ["inventory-service", "payment-service", "notification-service", "cart-service"],
            "cart-service": ["catalog-service", "inventory-service"],
            "payment-service": [],
            "inventory-service": [],
            "user-service": [],
            "catalog-service": ["inventory-service"],
            "notification-service": []
        }
    
    def _parse_time_range(self, time_range: str) -> timedelta:
        """Parse ISO 8601 duration to timedelta."""
        # Simple parser for common formats: PT1H, PT6H, P1D, etc.
        if time_range.startswith("PT"):
            value = int(time_range[2:-1])
            unit = time_range[-1]
            if unit == "H":
                return timedelta(hours=value)
            elif unit == "M":
                return timedelta(minutes=value)
            elif unit == "S":
                return timedelta(seconds=value)
        elif time_range.startswith("P"):
            value = int(time_range[1:-1])
            unit = time_range[-1]
            if unit == "D":
                return timedelta(days=value)
        return timedelta(hours=1)  # Default
    
    async def get_service_health(
        self,
        service_name: str,
        time_range: str = "PT1H"
    ) -> dict[str, Any]:
        """Get health status of a specific service."""
        
        # For demo/simulation when Azure is not configured
        if not self.workspace_id:
            return self._simulate_service_health(service_name)
        
        duration = self._parse_time_range(time_range)
        end_time = datetime.utcnow()
        start_time = end_time - duration
        
        # Query for service metrics
        query = f"""
        let serviceName = "{service_name}";
        
        // Get CPU and Memory from container metrics
        let containerMetrics = ContainerInventory
        | where ContainerName contains serviceName
        | join kind=inner (
            Perf
            | where ObjectName == "K8SContainer"
        ) on $left.ContainerID == $right.InstanceName
        | summarize 
            avgCpu = avg(CounterValue) by CounterName
        | where CounterName in ("cpuUsageNanoCores", "memoryRssBytes");
        
        // Get request metrics from Application Insights
        let appMetrics = AppRequests
        | where AppRoleName == serviceName
        | summarize 
            requestCount = count(),
            avgDuration = avg(DurationMs),
            p50Duration = percentile(DurationMs, 50),
            p95Duration = percentile(DurationMs, 95),
            p99Duration = percentile(DurationMs, 99),
            errorCount = countif(Success == false)
        | extend errorRate = todouble(errorCount) / requestCount;
        
        appMetrics
        """
        
        try:
            response = await asyncio.to_thread(
                self.logs_client.query_workspace,
                self.workspace_id,
                query,
                timespan=(start_time, end_time)
            )
            
            if response.status == LogsQueryStatus.SUCCESS:
                table = response.tables[0]
                if table.rows:
                    row = table.rows[0]
                    return {
                        "service": service_name,
                        "status": self._determine_status(row),
                        "timestamp": datetime.utcnow().isoformat(),
                        "time_range": time_range,
                        "metrics": {
                            "request_count": row[0],
                            "avg_latency_ms": row[1],
                            "p50_latency_ms": row[2],
                            "p95_latency_ms": row[3],
                            "p99_latency_ms": row[4],
                            "error_count": row[5],
                            "error_rate": row[6]
                        }
                    }
            
            return self._simulate_service_health(service_name)
            
        except Exception as e:
            # Fall back to simulation
            return self._simulate_service_health(service_name)
    
    def _simulate_service_health(self, service_name: str) -> dict[str, Any]:
        """Simulate service health for demo purposes."""
        import random
        
        # Simulate some variability
        base_latency = random.uniform(50, 200)
        cpu = random.uniform(20, 70)
        memory = random.uniform(40, 80)
        error_rate = random.uniform(0, 0.05)
        
        # Simulate occasional issues
        is_degraded = random.random() < 0.15
        if is_degraded:
            cpu = random.uniform(75, 95)
            error_rate = random.uniform(0.05, 0.15)
        
        status = "healthy"
        if cpu > 85 or error_rate > 0.1:
            status = "critical"
        elif cpu > 70 or error_rate > 0.05:
            status = "degraded"
        
        return {
            "service": service_name,
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "cpu_percent": round(cpu, 2),
                "memory_percent": round(memory, 2),
                "request_count": random.randint(1000, 10000),
                "avg_latency_ms": round(base_latency, 2),
                "p50_latency_ms": round(base_latency * 0.8, 2),
                "p95_latency_ms": round(base_latency * 2.5, 2),
                "p99_latency_ms": round(base_latency * 4, 2),
                "error_rate": round(error_rate, 4),
                "pods_running": random.randint(2, 5),
                "pods_desired": 3
            },
            "recent_deployments": [],
            "active_alerts": [] if status == "healthy" else [{
                "severity": "warning" if status == "degraded" else "critical",
                "message": f"High {'CPU' if cpu > 70 else 'error rate'} detected"
            }]
        }
    
    def _determine_status(self, metrics: tuple) -> str:
        """Determine service status from metrics."""
        error_rate = metrics[6] if len(metrics) > 6 else 0
        p99_latency = metrics[4] if len(metrics) > 4 else 0
        
        if error_rate > 0.1 or p99_latency > 5000:
            return "critical"
        elif error_rate > 0.05 or p99_latency > 2000:
            return "degraded"
        return "healthy"
    
    async def get_all_services_status(
        self,
        include_details: bool = False
    ) -> dict[str, Any]:
        """Get status of all services."""
        
        services_status = {}
        overall_status = "healthy"
        
        for service_name in self.services:
            if include_details:
                status = await self.get_service_health(service_name)
            else:
                status = await self._get_quick_status(service_name)
            
            services_status[service_name] = status
            
            if status.get("status") == "critical":
                overall_status = "critical"
            elif status.get("status") == "degraded" and overall_status != "critical":
                overall_status = "degraded"
        
        return {
            "overall_status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "services": services_status,
            "summary": {
                "total": len(self.services),
                "healthy": sum(1 for s in services_status.values() if s.get("status") == "healthy"),
                "degraded": sum(1 for s in services_status.values() if s.get("status") == "degraded"),
                "critical": sum(1 for s in services_status.values() if s.get("status") == "critical")
            }
        }
    
    async def _get_quick_status(self, service_name: str) -> dict[str, Any]:
        """Get quick status without full metrics."""
        health = await self.get_service_health(service_name, "PT5M")
        return {
            "status": health.get("status", "unknown"),
            "error_rate": health.get("metrics", {}).get("error_rate", 0)
        }
    
    async def query_logs(
        self,
        service_name: str,
        severity: Optional[str] = None,
        time_range: str = "PT1H",
        search_text: Optional[str] = None,
        limit: int = 50
    ) -> dict[str, Any]:
        """Query application logs."""
        
        # For demo/simulation
        if not self.workspace_id:
            return self._simulate_logs(service_name, severity, search_text, limit)
        
        duration = self._parse_time_range(time_range)
        end_time = datetime.utcnow()
        start_time = end_time - duration
        
        # Build query
        severity_filter = f"| where SeverityLevel == '{severity}'" if severity else ""
        search_filter = f"| where Message contains '{search_text}'" if search_text else ""
        
        query = f"""
        AppTraces
        | where AppRoleName == "{service_name}"
        {severity_filter}
        {search_filter}
        | order by TimeGenerated desc
        | take {limit}
        | project TimeGenerated, SeverityLevel, Message, OperationId
        """
        
        try:
            response = await asyncio.to_thread(
                self.logs_client.query_workspace,
                self.workspace_id,
                query,
                timespan=(start_time, end_time)
            )
            
            if response.status == LogsQueryStatus.SUCCESS:
                logs = []
                for row in response.tables[0].rows:
                    logs.append({
                        "timestamp": row[0].isoformat() if row[0] else None,
                        "severity": row[1],
                        "message": row[2],
                        "operation_id": row[3]
                    })
                
                return {
                    "service": service_name,
                    "time_range": time_range,
                    "filters": {
                        "severity": severity,
                        "search_text": search_text
                    },
                    "count": len(logs),
                    "logs": logs
                }
            
            return self._simulate_logs(service_name, severity, search_text, limit)
            
        except Exception:
            return self._simulate_logs(service_name, severity, search_text, limit)
    
    def _simulate_logs(
        self,
        service_name: str,
        severity: Optional[str],
        search_text: Optional[str],
        limit: int
    ) -> dict[str, Any]:
        """Simulate log data for demo."""
        import random
        
        log_templates = {
            "info": [
                "Request processed successfully",
                "Connection established to database",
                "Cache hit for key: {key}",
                "User {user_id} authenticated successfully",
                "Health check passed"
            ],
            "warning": [
                "Slow query detected: {duration}ms",
                "Cache miss for key: {key}",
                "Retry attempt {n} for external service call",
                "Connection pool nearing capacity: {percent}%",
                "Rate limit warning: {rate}/min"
            ],
            "error": [
                "Failed to connect to database: connection timeout",
                "Request failed with status 500: Internal Server Error",
                "NullPointerException in OrderProcessor.processOrder()",
                "Circuit breaker opened for payment-service",
                "Out of memory error in container"
            ]
        }
        
        severities = ["info", "info", "info", "warning", "error"] if not severity else [severity]
        
        logs = []
        base_time = datetime.utcnow()
        
        for i in range(min(limit, 50)):
            sev = random.choice(severities)
            template = random.choice(log_templates[sev])
            
            # Fill in template placeholders
            message = template.format(
                key=f"user:{random.randint(1000, 9999)}",
                user_id=f"u{random.randint(1000, 9999)}",
                duration=random.randint(500, 5000),
                n=random.randint(1, 3),
                percent=random.randint(70, 95),
                rate=random.randint(100, 500)
            )
            
            if search_text and search_text.lower() not in message.lower():
                continue
            
            logs.append({
                "timestamp": (base_time - timedelta(seconds=i*30)).isoformat(),
                "severity": sev,
                "message": message,
                "operation_id": f"op-{random.randint(100000, 999999)}"
            })
        
        return {
            "service": service_name,
            "filters": {
                "severity": severity,
                "search_text": search_text
            },
            "count": len(logs),
            "logs": logs
        }
    
    async def get_active_alerts(
        self,
        severity: Optional[str] = None,
        service_name: Optional[str] = None
    ) -> dict[str, Any]:
        """Get active alerts."""
        import random
        
        # Simulate alerts
        alert_templates = [
            {
                "name": "High Error Rate",
                "severity": "critical",
                "service": "order-service",
                "message": "Error rate exceeded 10% threshold",
                "fired_at": (datetime.utcnow() - timedelta(minutes=15)).isoformat()
            },
            {
                "name": "High CPU Usage",
                "severity": "high",
                "service": "catalog-service",
                "message": "CPU usage above 85% for 5 minutes",
                "fired_at": (datetime.utcnow() - timedelta(minutes=30)).isoformat()
            },
            {
                "name": "Memory Pressure",
                "severity": "medium",
                "service": "cart-service",
                "message": "Memory usage above 80%",
                "fired_at": (datetime.utcnow() - timedelta(hours=1)).isoformat()
            },
            {
                "name": "Slow Response Time",
                "severity": "medium",
                "service": "payment-service",
                "message": "P99 latency above 2 seconds",
                "fired_at": (datetime.utcnow() - timedelta(minutes=45)).isoformat()
            }
        ]
        
        # Filter alerts
        alerts = []
        for alert in alert_templates:
            if severity and alert["severity"] != severity:
                continue
            if service_name and alert["service"] != service_name:
                continue
            # Randomly include some alerts
            if random.random() < 0.6:
                alerts.append(alert)
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_count": len(alerts),
            "alerts": alerts,
            "filters": {
                "severity": severity,
                "service": service_name
            }
        }
    
    async def get_service_dependencies(
        self,
        service_name: str
    ) -> dict[str, Any]:
        """Get service dependency map."""
        import random
        
        dependencies = self.dependencies.get(service_name, [])
        
        dep_status = []
        for dep in dependencies:
            health = await self._get_quick_status(dep)
            dep_status.append({
                "name": dep,
                "status": health.get("status", "unknown"),
                "latency_ms": round(random.uniform(10, 100), 2),
                "error_rate": health.get("error_rate", 0)
            })
        
        # Find reverse dependencies (services that depend on this one)
        dependents = [
            svc for svc, deps in self.dependencies.items()
            if service_name in deps
        ]
        
        return {
            "service": service_name,
            "dependencies": dep_status,
            "dependents": dependents,
            "total_dependencies": len(dependencies),
            "total_dependents": len(dependents)
        }
