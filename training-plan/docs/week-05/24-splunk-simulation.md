# Session 24: Splunk Simulation for MCP

## Learning Objectives
- Build Splunk log simulation
- Implement SPL-like query parsing
- Generate realistic log data
- Enable log pattern analysis

## Duration: 1 hour

---

## 1. Splunk Simulator

### Splunk Simulation Implementation

```python
# File: training-plan/mcp-server/src/aiops_mcp/tools/splunk.py
"""
Splunk simulation for MCP server.
Simulates log search and analysis capabilities.
"""

import random
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class LogEvent:
    """A single log event."""
    timestamp: datetime
    source: str
    sourcetype: str
    host: str
    index: str
    raw: str
    fields: Dict[str, Any] = field(default_factory=dict)


class LogGenerator:
    """
    Generates realistic log data for simulation.
    """
    
    LOG_TEMPLATES = {
        "access": [
            '{ip} - - [{timestamp}] "{method} {path} HTTP/1.1" {status} {bytes} "{referrer}" "{user_agent}"',
            '{ip} - {user} [{timestamp}] "{method} {path} HTTP/1.1" {status} {bytes}',
        ],
        "application": [
            "[{timestamp}] [{level}] [{service}] [{trace_id}] {message}",
            "{timestamp} {level} {service} - {message}",
        ],
        "error": [
            "[{timestamp}] [ERROR] [{service}] Exception in {method}: {error_type} - {error_message}",
            "{timestamp} ERROR {service} {trace_id} - {error_type}: {error_message}",
        ],
        "metrics": [
            "{timestamp} metric={metric_name} value={value} host={host} service={service}",
        ]
    }
    
    ERROR_TYPES = [
        ("ConnectionTimeoutException", "Connection timed out after 30000ms"),
        ("DatabaseException", "Too many connections"),
        ("NullPointerException", "Null reference in processOrder"),
        ("AuthenticationException", "Invalid token"),
        ("ValidationException", "Invalid request payload"),
        ("ServiceUnavailableException", "Downstream service unavailable"),
    ]
    
    PATHS = [
        "/api/products", "/api/products/{id}",
        "/api/orders", "/api/orders/{id}",
        "/api/cart", "/api/cart/items",
        "/api/users", "/api/users/{id}",
        "/api/payments", "/api/inventory",
        "/health", "/metrics", "/ready"
    ]
    
    SERVICES = [
        "catalog-service", "order-service", "cart-service",
        "payment-service", "user-service", "notification-service",
        "inventory-service", "api-gateway"
    ]
    
    def generate_logs(
        self,
        count: int = 1000,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        services: Optional[List[str]] = None,
        error_rate: float = 0.05
    ) -> List[LogEvent]:
        """Generate sample log events."""
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=1)
        if end_time is None:
            end_time = datetime.now()
        
        services = services or self.SERVICES
        time_range = (end_time - start_time).total_seconds()
        
        logs = []
        for _ in range(count):
            # Random timestamp within range
            offset = random.random() * time_range
            timestamp = start_time + timedelta(seconds=offset)
            
            # Decide log type
            is_error = random.random() < error_rate
            
            if is_error:
                log = self._generate_error_log(timestamp, services)
            else:
                log_type = random.choice(["access", "application", "metrics"])
                if log_type == "access":
                    log = self._generate_access_log(timestamp, services)
                elif log_type == "application":
                    log = self._generate_app_log(timestamp, services)
                else:
                    log = self._generate_metric_log(timestamp, services)
            
            logs.append(log)
        
        # Sort by timestamp
        logs.sort(key=lambda x: x.timestamp)
        return logs
    
    def _generate_access_log(
        self,
        timestamp: datetime,
        services: List[str]
    ) -> LogEvent:
        """Generate access log."""
        service = random.choice(services)
        status = random.choices(
            [200, 201, 400, 401, 404, 500, 503],
            weights=[70, 10, 5, 3, 5, 4, 3]
        )[0]
        
        template = random.choice(self.LOG_TEMPLATES["access"])
        raw = template.format(
            ip=f"10.0.{random.randint(0,255)}.{random.randint(1,254)}",
            timestamp=timestamp.strftime("%d/%b/%Y:%H:%M:%S +0000"),
            method=random.choice(["GET", "POST", "PUT", "DELETE"]),
            path=random.choice(self.PATHS).replace("{id}", str(random.randint(1000, 9999))),
            status=status,
            bytes=random.randint(100, 50000),
            referrer="-",
            user_agent="Mozilla/5.0",
            user="-"
        )
        
        return LogEvent(
            timestamp=timestamp,
            source=f"/var/log/{service}/access.log",
            sourcetype="access_combined",
            host=f"{service}-{random.randint(1, 5)}",
            index="main",
            raw=raw,
            fields={
                "service": service,
                "status": status,
                "log_type": "access"
            }
        )
    
    def _generate_app_log(
        self,
        timestamp: datetime,
        services: List[str]
    ) -> LogEvent:
        """Generate application log."""
        service = random.choice(services)
        level = random.choices(
            ["INFO", "DEBUG", "WARN"],
            weights=[70, 20, 10]
        )[0]
        
        messages = [
            "Request processed successfully",
            "Cache hit for key session_123",
            "Database query completed in 45ms",
            "User authentication successful",
            "Order created with ID ORD-12345",
            "Sending notification to user@example.com",
            "Health check passed",
            "Connection pool stats: active=5, idle=15"
        ]
        
        template = random.choice(self.LOG_TEMPLATES["application"])
        raw = template.format(
            timestamp=timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            level=level,
            service=service,
            trace_id=f"{random.randint(100000, 999999):06x}",
            message=random.choice(messages)
        )
        
        return LogEvent(
            timestamp=timestamp,
            source=f"/var/log/{service}/application.log",
            sourcetype="application",
            host=f"{service}-{random.randint(1, 5)}",
            index="main",
            raw=raw,
            fields={
                "service": service,
                "level": level,
                "log_type": "application"
            }
        )
    
    def _generate_error_log(
        self,
        timestamp: datetime,
        services: List[str]
    ) -> LogEvent:
        """Generate error log."""
        service = random.choice(services)
        error_type, error_message = random.choice(self.ERROR_TYPES)
        
        template = random.choice(self.LOG_TEMPLATES["error"])
        raw = template.format(
            timestamp=timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            service=service,
            trace_id=f"{random.randint(100000, 999999):06x}",
            method="processRequest",
            error_type=error_type,
            error_message=error_message
        )
        
        return LogEvent(
            timestamp=timestamp,
            source=f"/var/log/{service}/error.log",
            sourcetype="application",
            host=f"{service}-{random.randint(1, 5)}",
            index="main",
            raw=raw,
            fields={
                "service": service,
                "level": "ERROR",
                "error_type": error_type,
                "log_type": "error"
            }
        )
    
    def _generate_metric_log(
        self,
        timestamp: datetime,
        services: List[str]
    ) -> LogEvent:
        """Generate metric log."""
        service = random.choice(services)
        metrics = [
            ("cpu_percent", random.uniform(10, 90)),
            ("memory_mb", random.uniform(256, 2048)),
            ("request_latency_ms", random.uniform(5, 500)),
            ("active_connections", random.randint(10, 200))
        ]
        metric_name, value = random.choice(metrics)
        
        template = self.LOG_TEMPLATES["metrics"][0]
        raw = template.format(
            timestamp=timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            metric_name=metric_name,
            value=f"{value:.2f}",
            host=f"{service}-{random.randint(1, 5)}",
            service=service
        )
        
        return LogEvent(
            timestamp=timestamp,
            source="metrics",
            sourcetype="metrics",
            host=f"{service}-{random.randint(1, 5)}",
            index="metrics",
            raw=raw,
            fields={
                "service": service,
                "metric_name": metric_name,
                "value": value,
                "log_type": "metrics"
            }
        )


class SplunkSimulator:
    """
    Simulates Splunk search capabilities.
    """
    
    def __init__(self):
        self.log_generator = LogGenerator()
        self.logs: List[LogEvent] = []
        self._generate_initial_logs()
    
    def _generate_initial_logs(self):
        """Generate initial log dataset."""
        # Generate logs for the last 24 hours
        self.logs = self.log_generator.generate_logs(
            count=5000,
            start_time=datetime.now() - timedelta(hours=24),
            end_time=datetime.now(),
            error_rate=0.05
        )
    
    def _parse_time_modifier(self, time_str: str) -> datetime:
        """Parse Splunk time modifiers like -1h, -24h, now."""
        if time_str == "now":
            return datetime.now()
        
        match = re.match(r'-(\d+)(m|h|d)', time_str)
        if match:
            value = int(match.group(1))
            unit = match.group(2)
            
            if unit == 'm':
                return datetime.now() - timedelta(minutes=value)
            elif unit == 'h':
                return datetime.now() - timedelta(hours=value)
            elif unit == 'd':
                return datetime.now() - timedelta(days=value)
        
        return datetime.now() - timedelta(hours=1)
    
    def _parse_search_query(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """Parse SPL-like search query."""
        parts = query.split('|')
        search_terms = parts[0].strip()
        
        filters = {}
        
        # Extract field=value pairs
        field_pattern = r'(\w+)=(["\']?)([^"\'\s]+)\2'
        for match in re.finditer(field_pattern, search_terms):
            field, _, value = match.groups()
            filters[field] = value
        
        # Extract bare search terms
        bare_terms = re.sub(field_pattern, '', search_terms).strip()
        if bare_terms:
            filters['_raw'] = bare_terms
        
        return query, filters
    
    async def search(
        self,
        query: str,
        earliest: str = "-1h",
        latest: str = "now",
        limit: int = 100
    ) -> Dict[str, Any]:
        """Execute a search query."""
        start_time = self._parse_time_modifier(earliest)
        end_time = self._parse_time_modifier(latest)
        
        _, filters = self._parse_search_query(query)
        
        # Filter logs
        results = []
        for log in self.logs:
            # Time filter
            if not (start_time <= log.timestamp <= end_time):
                continue
            
            # Field filters
            match = True
            for field, value in filters.items():
                if field == '_raw':
                    if value.lower() not in log.raw.lower():
                        match = False
                        break
                elif field == 'service':
                    if value.lower() not in log.fields.get('service', '').lower():
                        match = False
                        break
                elif field == 'level':
                    if value.upper() != log.fields.get('level', '').upper():
                        match = False
                        break
                elif field == 'sourcetype':
                    if value != log.sourcetype:
                        match = False
                        break
            
            if match:
                results.append({
                    "_time": log.timestamp.isoformat(),
                    "_raw": log.raw,
                    "source": log.source,
                    "sourcetype": log.sourcetype,
                    "host": log.host,
                    "index": log.index,
                    **log.fields
                })
        
        # Sort by time descending
        results.sort(key=lambda x: x["_time"], reverse=True)
        
        return {
            "status": "success",
            "query": query,
            "earliest": earliest,
            "latest": latest,
            "result_count": len(results[:limit]),
            "total_count": len(results),
            "results": results[:limit]
        }
    
    async def stats(
        self,
        query: str,
        earliest: str = "-1h",
        latest: str = "now",
        by_field: str = "service",
        stat_func: str = "count"
    ) -> Dict[str, Any]:
        """Execute a stats query."""
        search_result = await self.search(query, earliest, latest, limit=10000)
        results = search_result.get("results", [])
        
        # Group by field
        groups = defaultdict(list)
        for result in results:
            key = result.get(by_field, "unknown")
            groups[key].append(result)
        
        # Calculate stats
        stats_results = []
        for key, group_results in groups.items():
            stat_value = len(group_results)  # count by default
            stats_results.append({
                by_field: key,
                stat_func: stat_value
            })
        
        # Sort by count descending
        stats_results.sort(key=lambda x: x[stat_func], reverse=True)
        
        return {
            "status": "success",
            "query": query,
            "results": stats_results
        }
    
    async def timechart(
        self,
        query: str,
        earliest: str = "-1h",
        latest: str = "now",
        span: str = "5m"
    ) -> Dict[str, Any]:
        """Execute a timechart query."""
        search_result = await self.search(query, earliest, latest, limit=10000)
        results = search_result.get("results", [])
        
        # Parse span
        span_minutes = 5
        span_match = re.match(r'(\d+)(m|h)', span)
        if span_match:
            value = int(span_match.group(1))
            unit = span_match.group(2)
            span_minutes = value if unit == 'm' else value * 60
        
        # Group by time bucket
        buckets = defaultdict(int)
        for result in results:
            timestamp = datetime.fromisoformat(result["_time"])
            bucket = timestamp.replace(
                minute=(timestamp.minute // span_minutes) * span_minutes,
                second=0,
                microsecond=0
            )
            buckets[bucket.isoformat()] += 1
        
        # Sort by time
        timechart_results = [
            {"_time": k, "count": v}
            for k, v in sorted(buckets.items())
        ]
        
        return {
            "status": "success",
            "query": query,
            "span": span,
            "results": timechart_results
        }


# Singleton instance
_splunk_sim: Optional[SplunkSimulator] = None


def get_splunk_simulator() -> SplunkSimulator:
    """Get or create Splunk simulator."""
    global _splunk_sim
    
    if _splunk_sim is None:
        _splunk_sim = SplunkSimulator()
    
    return _splunk_sim
```

---

## 2. Key Takeaways

1. **Realistic Logs**: Generate logs that match real patterns
2. **SPL Parsing**: Simple SPL-like query support
3. **Time Filters**: Support relative time queries
4. **Stats & Timechart**: Enable aggregation queries
5. **Error Injection**: Configurable error rates

## Next Session Preview
- Session 25: Building RAG for Historical Tickets
