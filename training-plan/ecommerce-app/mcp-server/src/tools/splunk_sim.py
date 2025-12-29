"""
Splunk Log Simulator for MCP Server
Simulates Splunk-like log querying and analysis
"""

import random
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from collections import Counter


class SplunkSimulator:
    """Simulates Splunk log search and analysis."""
    
    def __init__(self):
        self.services = [
            "catalog-service", "order-service", "cart-service",
            "user-service", "payment-service", "inventory-service",
            "notification-service", "api-gateway"
        ]
        
        # Log templates by severity
        self.log_templates = {
            "info": [
                "Request completed successfully | method={method} path={path} status=200 duration={duration}ms",
                "Database query executed | query_time={query_time}ms rows={rows}",
                "Cache hit | key={cache_key} ttl={ttl}s",
                "Health check passed | component={component} status=healthy",
                "Connection established | host={host} port={port}",
                "Background job completed | job={job_name} duration={duration}ms",
                "User action logged | user_id={user_id} action={action}",
                "Configuration loaded | version={version} env={env}"
            ],
            "warning": [
                "Slow query detected | query_time={query_time}ms threshold=500ms query={query}",
                "Cache miss | key={cache_key} attempting database lookup",
                "Retry attempt | attempt={attempt} max_attempts=3 service={downstream}",
                "Connection pool nearing capacity | active={active} max={max} utilization={util}%",
                "Rate limit warning | rate={rate}/min limit={limit}/min client={client}",
                "High memory usage | current={memory}MB threshold={threshold}MB",
                "Request timeout approaching | elapsed={elapsed}ms timeout={timeout}ms",
                "Deprecated API used | endpoint={path} deprecation_date={date}"
            ],
            "error": [
                "Request failed | method={method} path={path} status={status} error={error}",
                "Database connection failed | host={host} error=connection_refused",
                "External service unavailable | service={downstream} status={status}",
                "Authentication failed | user_id={user_id} reason={reason}",
                "Transaction rollback | transaction_id={tx_id} reason={reason}",
                "Circuit breaker opened | service={downstream} failure_count={count}",
                "Out of memory error | allocated={allocated}MB limit={limit}MB",
                "Unhandled exception | exception={exception} stack_trace={trace}"
            ]
        }
        
        # Error patterns for analysis
        self.error_patterns = {
            "connection_timeout": {
                "pattern": r"connection.*timeout|timeout.*connection",
                "description": "Database or service connection timeouts",
                "remediation": "Check network connectivity, increase timeout values, verify target service health"
            },
            "out_of_memory": {
                "pattern": r"out\s*of\s*memory|oom|memory.*exceeded",
                "description": "Memory exhaustion errors",
                "remediation": "Increase memory limits, check for memory leaks, optimize memory usage"
            },
            "authentication_failure": {
                "pattern": r"auth.*fail|unauthorized|401|invalid.*token",
                "description": "Authentication and authorization failures",
                "remediation": "Check credentials, verify token validity, review auth configuration"
            },
            "database_error": {
                "pattern": r"database.*error|sql.*exception|query.*failed",
                "description": "Database query or connection errors",
                "remediation": "Check database health, review query performance, verify connection pool"
            },
            "circuit_breaker": {
                "pattern": r"circuit.*breaker|circuit.*open",
                "description": "Circuit breaker activated for downstream service",
                "remediation": "Check downstream service health, review failure thresholds"
            },
            "rate_limit": {
                "pattern": r"rate.*limit|throttl|429|too.*many.*requests",
                "description": "Rate limiting triggered",
                "remediation": "Review rate limit configuration, implement request queuing"
            }
        }
    
    def _generate_logs(
        self,
        service_name: str,
        count: int,
        severity_dist: dict = None
    ) -> list[dict]:
        """Generate simulated log entries."""
        
        if severity_dist is None:
            severity_dist = {"info": 0.7, "warning": 0.2, "error": 0.1}
        
        logs = []
        base_time = datetime.utcnow()
        
        for i in range(count):
            # Select severity based on distribution
            r = random.random()
            if r < severity_dist.get("info", 0.7):
                severity = "info"
            elif r < severity_dist.get("info", 0.7) + severity_dist.get("warning", 0.2):
                severity = "warning"
            else:
                severity = "error"
            
            template = random.choice(self.log_templates[severity])
            
            # Fill in template variables
            message = template.format(
                method=random.choice(["GET", "POST", "PUT", "DELETE"]),
                path=random.choice(["/api/products", "/api/orders", "/api/cart", "/api/users"]),
                duration=random.randint(10, 500),
                query_time=random.randint(5, 2000),
                rows=random.randint(1, 100),
                cache_key=f"cache:{random.randint(1000, 9999)}",
                ttl=random.randint(60, 3600),
                component=random.choice(["db", "cache", "api", "queue"]),
                host=f"host-{random.randint(1, 5)}.internal",
                port=random.choice([443, 5432, 6379, 9092]),
                job_name=random.choice(["cleanup", "sync", "report", "backup"]),
                user_id=f"u{random.randint(10000, 99999)}",
                action=random.choice(["login", "purchase", "view", "update"]),
                version=f"v{random.randint(1, 3)}.{random.randint(0, 9)}.{random.randint(0, 20)}",
                env=random.choice(["dev", "staging", "prod"]),
                query=random.choice(["SELECT *", "INSERT INTO", "UPDATE", "DELETE FROM"]),
                attempt=random.randint(1, 3),
                downstream=random.choice(["payment-api", "inventory-api", "notification-api"]),
                active=random.randint(5, 20),
                max=25,
                util=random.randint(60, 95),
                rate=random.randint(100, 500),
                limit=500,
                client=f"client-{random.randint(1, 10)}",
                memory=random.randint(400, 900),
                threshold=512,
                elapsed=random.randint(2000, 4500),
                timeout=5000,
                date="2025-01-01",
                status=random.choice([500, 502, 503, 504]),
                error=random.choice(["internal_error", "timeout", "connection_refused"]),
                reason=random.choice(["invalid_token", "expired", "rate_limited"]),
                tx_id=f"tx-{random.randint(100000, 999999)}",
                count=random.randint(5, 20),
                allocated=random.randint(900, 1200),
                exception=random.choice(["NullPointerException", "IOException", "TimeoutException"]),
                trace="..."
            )
            
            logs.append({
                "timestamp": (base_time - timedelta(seconds=i*30)).isoformat(),
                "service": service_name,
                "severity": severity,
                "message": message,
                "trace_id": f"trace-{random.randint(100000, 999999)}",
                "span_id": f"span-{random.randint(1000, 9999)}"
            })
        
        return logs
    
    async def analyze_error_patterns(
        self,
        service_name: str,
        time_range: str = "PT1H",
        top_n: int = 10
    ) -> dict[str, Any]:
        """Analyze error patterns in logs."""
        
        # Generate logs with higher error rate for interesting results
        logs = self._generate_logs(
            service_name,
            count=200,
            severity_dist={"info": 0.5, "warning": 0.25, "error": 0.25}
        )
        
        error_logs = [log for log in logs if log["severity"] == "error"]
        
        # Analyze patterns
        pattern_counts = Counter()
        matched_patterns = {}
        
        for log in error_logs:
            for pattern_name, pattern_info in self.error_patterns.items():
                if re.search(pattern_info["pattern"], log["message"], re.IGNORECASE):
                    pattern_counts[pattern_name] += 1
                    if pattern_name not in matched_patterns:
                        matched_patterns[pattern_name] = {
                            "pattern": pattern_name,
                            "description": pattern_info["description"],
                            "remediation": pattern_info["remediation"],
                            "count": 0,
                            "sample_messages": []
                        }
                    matched_patterns[pattern_name]["count"] += 1
                    if len(matched_patterns[pattern_name]["sample_messages"]) < 3:
                        matched_patterns[pattern_name]["sample_messages"].append(log["message"][:200])
        
        # Sort by count
        sorted_patterns = sorted(
            matched_patterns.values(),
            key=lambda x: x["count"],
            reverse=True
        )[:top_n]
        
        return {
            "service": service_name,
            "time_range": time_range,
            "total_logs_analyzed": len(logs),
            "total_errors": len(error_logs),
            "error_rate": round(len(error_logs) / len(logs), 3),
            "patterns": sorted_patterns,
            "top_pattern": sorted_patterns[0] if sorted_patterns else None
        }
    
    async def get_log_timeline(
        self,
        service_name: str,
        time_range: str = "PT1H",
        interval: str = "5m"
    ) -> dict[str, Any]:
        """Get log timeline aggregated by interval."""
        
        # Parse interval
        interval_minutes = 5
        if interval.endswith("m"):
            interval_minutes = int(interval[:-1])
        elif interval.endswith("h"):
            interval_minutes = int(interval[:-1]) * 60
        
        # Parse time range to get bucket count
        hours = 1
        if time_range.startswith("PT"):
            if time_range.endswith("H"):
                hours = int(time_range[2:-1])
            elif time_range.endswith("M"):
                hours = int(time_range[2:-1]) / 60
        elif time_range.startswith("P") and time_range.endswith("D"):
            hours = int(time_range[1:-1]) * 24
        
        num_buckets = int((hours * 60) / interval_minutes)
        
        # Generate timeline data
        base_time = datetime.utcnow()
        timeline = []
        
        for i in range(num_buckets):
            bucket_time = base_time - timedelta(minutes=i * interval_minutes)
            
            # Generate varying counts
            base_count = random.randint(50, 200)
            error_base = random.randint(1, 10)
            
            # Occasionally spike
            if random.random() < 0.1:
                base_count = random.randint(300, 500)
                error_base = random.randint(20, 50)
            
            timeline.append({
                "timestamp": bucket_time.isoformat(),
                "total_count": base_count,
                "info_count": int(base_count * 0.7),
                "warning_count": int(base_count * 0.2),
                "error_count": error_base,
                "avg_response_time_ms": random.randint(50, 300)
            })
        
        # Reverse to chronological order
        timeline.reverse()
        
        return {
            "service": service_name,
            "time_range": time_range,
            "interval": interval,
            "bucket_count": len(timeline),
            "timeline": timeline,
            "summary": {
                "total_logs": sum(b["total_count"] for b in timeline),
                "total_errors": sum(b["error_count"] for b in timeline),
                "peak_minute": max(timeline, key=lambda x: x["total_count"])["timestamp"],
                "highest_error_rate": max(
                    b["error_count"] / b["total_count"] if b["total_count"] > 0 else 0
                    for b in timeline
                )
            }
        }
    
    async def search_logs(
        self,
        query: str,
        service_name: Optional[str] = None,
        time_range: str = "PT1H",
        limit: int = 100
    ) -> dict[str, Any]:
        """Search logs using SPL-like query syntax."""
        
        # Parse simple SPL-like query
        filters = self._parse_query(query)
        
        # Generate logs
        if service_name:
            logs = self._generate_logs(service_name, count=500)
        else:
            logs = []
            for svc in self.services:
                logs.extend(self._generate_logs(svc, count=100))
        
        # Apply filters
        filtered_logs = []
        for log in logs:
            if service_name and log["service"] != service_name:
                continue
            
            if filters.get("severity") and log["severity"] != filters["severity"]:
                continue
            
            if filters.get("search_text"):
                if filters["search_text"].lower() not in log["message"].lower():
                    continue
            
            filtered_logs.append(log)
            
            if len(filtered_logs) >= limit:
                break
        
        return {
            "query": query,
            "service_filter": service_name,
            "time_range": time_range,
            "result_count": len(filtered_logs),
            "logs": filtered_logs[:limit],
            "parsed_filters": filters
        }
    
    def _parse_query(self, query: str) -> dict[str, Any]:
        """Parse simple SPL-like query."""
        
        filters = {}
        
        # Parse severity filter
        severity_match = re.search(r'severity\s*=\s*(\w+)', query, re.IGNORECASE)
        if severity_match:
            filters["severity"] = severity_match.group(1).lower()
        
        # Parse search text
        search_match = re.search(r'search\s+"([^"]+)"', query, re.IGNORECASE)
        if search_match:
            filters["search_text"] = search_match.group(1)
        
        # Parse service filter
        service_match = re.search(r'service\s*=\s*(\S+)', query, re.IGNORECASE)
        if service_match:
            filters["service"] = service_match.group(1)
        
        return filters
    
    async def get_error_statistics(
        self,
        service_name: str,
        time_range: str = "PT1H"
    ) -> dict[str, Any]:
        """Get error statistics for a service."""
        
        logs = self._generate_logs(
            service_name,
            count=500,
            severity_dist={"info": 0.7, "warning": 0.2, "error": 0.1}
        )
        
        total = len(logs)
        by_severity = Counter(log["severity"] for log in logs)
        
        error_logs = [log for log in logs if log["severity"] == "error"]
        
        # Extract error types
        error_types = Counter()
        for log in error_logs:
            # Simple error type extraction
            if "timeout" in log["message"].lower():
                error_types["timeout"] += 1
            elif "connection" in log["message"].lower():
                error_types["connection"] += 1
            elif "auth" in log["message"].lower():
                error_types["authentication"] += 1
            elif "memory" in log["message"].lower():
                error_types["memory"] += 1
            else:
                error_types["other"] += 1
        
        return {
            "service": service_name,
            "time_range": time_range,
            "total_logs": total,
            "by_severity": dict(by_severity),
            "error_rate": round(by_severity["error"] / total, 4),
            "error_types": dict(error_types),
            "most_common_error": error_types.most_common(1)[0] if error_types else None
        }
