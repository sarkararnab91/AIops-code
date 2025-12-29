"""
RAG Knowledge Base for MCP Server
Semantic search over historical incidents using ChromaDB and Azure OpenAI
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Any, Optional

import chromadb
from chromadb.config import Settings


class RAGKnowledgeBase:
    """RAG-based knowledge base for incident resolution."""
    
    def __init__(self, persist_dir: str = "./data/chromadb"):
        # Initialize ChromaDB
        self.client = chromadb.Client(Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory=persist_dir,
            anonymized_telemetry=False
        ))
        
        # Create collections
        self.incidents_collection = self.client.get_or_create_collection(
            name="incidents",
            metadata={"description": "Historical incidents with resolutions"}
        )
        
        self.runbooks_collection = self.client.get_or_create_collection(
            name="runbooks",
            metadata={"description": "Operational runbooks"}
        )
        
        # Seed with data if empty
        if self.incidents_collection.count() == 0:
            self._seed_incidents()
        
        if self.runbooks_collection.count() == 0:
            self._seed_runbooks()
    
    def _generate_id(self, text: str) -> str:
        """Generate deterministic ID from text."""
        return hashlib.md5(text.encode()).hexdigest()[:12]
    
    def _seed_incidents(self):
        """Seed with historical incident data."""
        
        incidents = [
            {
                "id": "INC0001001",
                "service": "order-service",
                "title": "High latency in order processing during peak hours",
                "symptoms": ["High response times", "Timeout errors", "Queue buildup"],
                "root_cause": "Database connection pool exhaustion under high load",
                "resolution": "1. Increased connection pool from 10 to 25\n2. Added connection timeout of 5s\n3. Implemented connection health checks\n4. Added metrics for pool utilization",
                "prevention": "Monitor connection pool metrics, set up alerts at 80% utilization",
                "category": "performance",
                "priority": "P2",
                "mttr_hours": 2.5
            },
            {
                "id": "INC0001002",
                "service": "payment-service",
                "title": "Payment processing failures due to external provider timeout",
                "symptoms": ["Payment failures", "5xx errors", "Customer complaints"],
                "root_cause": "External payment gateway experiencing latency spikes",
                "resolution": "1. Implemented circuit breaker pattern\n2. Added retry with exponential backoff\n3. Created fallback to secondary provider\n4. Added detailed timeout logging",
                "prevention": "Regular health checks on payment providers, maintain backup provider",
                "category": "availability",
                "priority": "P1",
                "mttr_hours": 1.5
            },
            {
                "id": "INC0001003",
                "service": "catalog-service",
                "title": "Memory leak causing pod restarts",
                "symptoms": ["OOMKilled pods", "Increasing memory usage", "Slow responses"],
                "root_cause": "Unbounded cache growth in product search feature",
                "resolution": "1. Implemented LRU cache with 10000 item limit\n2. Added cache TTL of 1 hour\n3. Increased memory limit to 1Gi\n4. Added memory usage metrics",
                "prevention": "Regular load testing, memory profiling in pre-prod",
                "category": "performance",
                "priority": "P2",
                "mttr_hours": 4.0
            },
            {
                "id": "INC0001004",
                "service": "cart-service",
                "title": "Cart data loss after Redis restart",
                "symptoms": ["Empty carts", "Customer complaints", "Session errors"],
                "root_cause": "Redis persistence not configured, data lost on restart",
                "resolution": "1. Enabled Redis AOF persistence\n2. Configured backup to Azure Blob\n3. Implemented cart recovery from order history\n4. Added session persistence fallback",
                "prevention": "Always configure persistence for stateful services",
                "category": "data-loss",
                "priority": "P1",
                "mttr_hours": 3.0
            },
            {
                "id": "INC0001005",
                "service": "user-service",
                "title": "Authentication failures spike during deployment",
                "symptoms": ["Login failures", "401 errors", "Session invalidation"],
                "root_cause": "Rolling deployment invalidated JWT signing keys",
                "resolution": "1. Implemented key rotation with overlap\n2. Changed to blue-green deployment\n3. Added session migration logic\n4. Improved deployment health checks",
                "prevention": "Test deployments with active sessions, use immutable configs",
                "category": "deployment",
                "priority": "P1",
                "mttr_hours": 1.0
            },
            {
                "id": "INC0001006",
                "service": "inventory-service",
                "title": "Inventory sync failures with warehouse system",
                "symptoms": ["Stale inventory", "Overselling", "Sync errors in logs"],
                "root_cause": "SSL certificate expired on external warehouse API",
                "resolution": "1. Renewed SSL certificate\n2. Set up certificate expiry monitoring\n3. Added fallback to cached inventory\n4. Implemented graceful degradation",
                "prevention": "Monitor certificate expiry, automate renewal",
                "category": "integration",
                "priority": "P2",
                "mttr_hours": 2.0
            },
            {
                "id": "INC0001007",
                "service": "api-gateway",
                "title": "Gateway timeout under sustained load",
                "symptoms": ["504 errors", "Request timeouts", "Dropped connections"],
                "root_cause": "Insufficient replicas and no auto-scaling configured",
                "resolution": "1. Configured HPA with CPU/memory targets\n2. Set minimum 3 replicas\n3. Added request rate limiting\n4. Implemented request queuing",
                "prevention": "Load test regularly, configure auto-scaling from start",
                "category": "capacity",
                "priority": "P2",
                "mttr_hours": 1.5
            },
            {
                "id": "INC0001008",
                "service": "notification-service",
                "title": "Email notifications delayed by hours",
                "symptoms": ["Delayed emails", "Queue growth", "Slow processing"],
                "root_cause": "Single-threaded message consumer overwhelmed",
                "resolution": "1. Increased concurrent handlers from 1 to 5\n2. Partitioned queue by priority\n3. Added dead letter queue\n4. Implemented batch processing",
                "prevention": "Design for expected throughput, monitor queue depth",
                "category": "performance",
                "priority": "P3",
                "mttr_hours": 2.0
            },
            {
                "id": "INC0001009",
                "service": "order-service",
                "title": "Order duplication during high traffic",
                "symptoms": ["Duplicate orders", "Double charges", "Customer complaints"],
                "root_cause": "Missing idempotency check on order creation endpoint",
                "resolution": "1. Added idempotency key header support\n2. Implemented request deduplication\n3. Added database unique constraint\n4. Created order reconciliation job",
                "prevention": "Design APIs with idempotency from start",
                "category": "data-integrity",
                "priority": "P1",
                "mttr_hours": 4.0
            },
            {
                "id": "INC0001010",
                "service": "catalog-service",
                "title": "Search returning stale results after product update",
                "symptoms": ["Outdated search results", "Missing new products", "Cache inconsistency"],
                "root_cause": "Search index not invalidated on product updates",
                "resolution": "1. Implemented event-driven index updates\n2. Added cache invalidation on writes\n3. Reduced cache TTL to 5 minutes\n4. Added manual cache clear endpoint",
                "prevention": "Design cache invalidation strategy with data model",
                "category": "data-consistency",
                "priority": "P3",
                "mttr_hours": 3.0
            }
        ]
        
        documents = []
        metadatas = []
        ids = []
        
        for inc in incidents:
            # Create searchable document
            doc = f"""
            Service: {inc['service']}
            Title: {inc['title']}
            Symptoms: {', '.join(inc['symptoms'])}
            Root Cause: {inc['root_cause']}
            Resolution: {inc['resolution']}
            Prevention: {inc['prevention']}
            Category: {inc['category']}
            """
            
            documents.append(doc)
            metadatas.append({
                "incident_id": inc["id"],
                "service": inc["service"],
                "category": inc["category"],
                "priority": inc["priority"],
                "mttr_hours": inc["mttr_hours"],
                "title": inc["title"],
                "resolution": inc["resolution"],
                "root_cause": inc["root_cause"]
            })
            ids.append(inc["id"])
        
        self.incidents_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
    
    def _seed_runbooks(self):
        """Seed with operational runbooks."""
        
        runbooks = [
            {
                "id": "RB001",
                "issue_type": "high_cpu",
                "title": "High CPU Usage Troubleshooting",
                "steps": [
                    "1. Check current CPU usage: kubectl top pods -n <namespace>",
                    "2. Identify high-CPU containers: kubectl top pods --containers",
                    "3. Check for recent deployments: kubectl rollout history",
                    "4. Profile application if needed: attach profiler or enable CPU profiling",
                    "5. Check for infinite loops or busy waits in logs",
                    "6. Scale horizontally if legitimate load: kubectl scale deployment",
                    "7. If bug identified, prepare hotfix and deploy"
                ],
                "automation": {
                    "scale_threshold": 85,
                    "scale_action": "kubectl scale deployment <name> --replicas=+2"
                }
            },
            {
                "id": "RB002",
                "issue_type": "memory_leak",
                "title": "Memory Leak Investigation",
                "steps": [
                    "1. Check memory trends: kubectl top pods --watch",
                    "2. Capture heap dump: kubectl exec <pod> -- jmap -dump:format=b,file=/tmp/heap.hprof",
                    "3. Analyze with memory profiler",
                    "4. Check for common patterns: unbounded caches, connection leaks",
                    "5. Review recent code changes for memory issues",
                    "6. Temporary mitigation: restart pods on schedule",
                    "7. Long-term fix: patch and deploy corrected code"
                ],
                "automation": {
                    "restart_threshold": 90,
                    "restart_action": "kubectl rollout restart deployment <name>"
                }
            },
            {
                "id": "RB003",
                "issue_type": "connection_timeout",
                "title": "Database Connection Timeout",
                "steps": [
                    "1. Check database health: az cosmosdb show --query provisioningState",
                    "2. Verify network connectivity: kubectl exec <pod> -- nc -zv <db-host> 443",
                    "3. Check connection pool metrics: connection_pool_size, active_connections",
                    "4. Review connection pool configuration",
                    "5. Check for connection leaks in application",
                    "6. Increase pool size if needed",
                    "7. Add connection health checks and timeouts"
                ],
                "automation": {
                    "pool_increase_action": "Update config map and restart pods"
                }
            },
            {
                "id": "RB004",
                "issue_type": "pod_crash_loop",
                "title": "Pod CrashLoopBackOff Resolution",
                "steps": [
                    "1. Check pod status: kubectl describe pod <name>",
                    "2. Check previous container logs: kubectl logs <pod> --previous",
                    "3. Check resource limits: kubectl get pod <name> -o yaml | grep -A5 resources",
                    "4. Verify environment variables and config maps",
                    "5. Check liveness/readiness probe configuration",
                    "6. If OOMKilled: increase memory limits",
                    "7. If application error: fix and redeploy",
                    "8. If config error: update ConfigMap/Secret"
                ],
                "automation": {
                    "diagnostic_commands": [
                        "kubectl describe pod",
                        "kubectl logs --previous",
                        "kubectl get events --sort-by=.lastTimestamp"
                    ]
                }
            },
            {
                "id": "RB005",
                "issue_type": "high_latency",
                "title": "High Latency Investigation",
                "steps": [
                    "1. Check service metrics: response time percentiles",
                    "2. Review distributed traces for slow requests",
                    "3. Check downstream dependencies health",
                    "4. Verify database query performance",
                    "5. Check for lock contention or blocking operations",
                    "6. Review recent deployments",
                    "7. Check network latency between services",
                    "8. Enable detailed tracing if needed"
                ],
                "automation": {
                    "scale_check": "Check if load warrants scaling"
                }
            },
            {
                "id": "RB006",
                "issue_type": "certificate_expiry",
                "title": "SSL/TLS Certificate Expiry",
                "steps": [
                    "1. Check certificate expiry: openssl s_client -connect host:443 | openssl x509 -noout -dates",
                    "2. Identify certificate source (cert-manager, manual, etc.)",
                    "3. Renew certificate through appropriate channel",
                    "4. Update Kubernetes secret if manual",
                    "5. Restart affected pods to pick up new cert",
                    "6. Verify connectivity with new certificate",
                    "7. Set up certificate expiry monitoring"
                ],
                "automation": {
                    "renewal_action": "kubectl cert-manager renew <certificate-name>"
                }
            }
        ]
        
        documents = []
        metadatas = []
        ids = []
        
        for rb in runbooks:
            doc = f"""
            Issue Type: {rb['issue_type']}
            Title: {rb['title']}
            Steps: {chr(10).join(rb['steps'])}
            """
            
            documents.append(doc)
            metadatas.append({
                "runbook_id": rb["id"],
                "issue_type": rb["issue_type"],
                "title": rb["title"],
                "steps": json.dumps(rb["steps"]),
                "automation": json.dumps(rb.get("automation", {}))
            })
            ids.append(rb["id"])
        
        self.runbooks_collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
    
    async def search_similar_incidents(
        self,
        description: str,
        service_name: Optional[str] = None,
        top_k: int = 5
    ) -> dict[str, Any]:
        """Search for similar past incidents."""
        
        # Build query
        query = description
        if service_name:
            query = f"Service: {service_name}. {description}"
        
        # Search
        results = self.incidents_collection.query(
            query_texts=[query],
            n_results=top_k,
            where={"service": service_name} if service_name else None
        )
        
        incidents = []
        if results and results["metadatas"]:
            for i, metadata in enumerate(results["metadatas"][0]):
                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 / (1 + distance)  # Convert distance to similarity
                
                incidents.append({
                    "id": metadata.get("incident_id"),
                    "service": metadata.get("service"),
                    "title": metadata.get("title"),
                    "root_cause": metadata.get("root_cause"),
                    "resolution": metadata.get("resolution"),
                    "category": metadata.get("category"),
                    "priority": metadata.get("priority"),
                    "similarity": round(similarity, 3),
                    "mttr_hours": metadata.get("mttr_hours")
                })
        
        return {
            "query": description,
            "service_filter": service_name,
            "incident_count": len(incidents),
            "incidents": incidents
        }
    
    async def get_resolution_suggestions(
        self,
        incident_description: str,
        service_name: Optional[str] = None,
        error_messages: list[str] = None
    ) -> dict[str, Any]:
        """Get resolution suggestions based on similar incidents."""
        
        # Combine description with error messages
        full_description = incident_description
        if error_messages:
            full_description += " Errors: " + " ".join(error_messages)
        
        # Find similar incidents
        similar = await self.search_similar_incidents(
            description=full_description,
            service_name=service_name,
            top_k=3
        )
        
        suggestions = []
        for incident in similar.get("incidents", []):
            if incident["similarity"] > 0.3:  # Only suggest if reasonably similar
                suggestions.append({
                    "based_on": incident["id"],
                    "similarity": incident["similarity"],
                    "suggested_resolution": incident["resolution"],
                    "root_cause_hint": incident["root_cause"],
                    "expected_mttr_hours": incident["mttr_hours"]
                })
        
        # Also check runbooks
        runbook = await self.get_runbook(
            issue_type=self._classify_issue(full_description),
            service_name=service_name
        )
        
        return {
            "incident_description": incident_description,
            "suggestions": suggestions,
            "runbook": runbook.get("runbook"),
            "confidence": suggestions[0]["similarity"] if suggestions else 0
        }
    
    def _classify_issue(self, description: str) -> str:
        """Simple classification of issue type from description."""
        description = description.lower()
        
        if "cpu" in description or "processor" in description:
            return "high_cpu"
        elif "memory" in description or "oom" in description or "leak" in description:
            return "memory_leak"
        elif "timeout" in description or "connection" in description:
            return "connection_timeout"
        elif "crash" in description or "restart" in description:
            return "pod_crash_loop"
        elif "slow" in description or "latency" in description:
            return "high_latency"
        elif "certificate" in description or "ssl" in description or "tls" in description:
            return "certificate_expiry"
        else:
            return "unknown"
    
    async def get_runbook(
        self,
        issue_type: str,
        service_name: Optional[str] = None
    ) -> dict[str, Any]:
        """Get runbook for a specific issue type."""
        
        # Search runbooks
        results = self.runbooks_collection.query(
            query_texts=[f"Issue type: {issue_type}"],
            n_results=1,
            where={"issue_type": issue_type}
        )
        
        if results and results["metadatas"] and results["metadatas"][0]:
            metadata = results["metadatas"][0][0]
            
            return {
                "issue_type": issue_type,
                "runbook": {
                    "id": metadata.get("runbook_id"),
                    "title": metadata.get("title"),
                    "steps": json.loads(metadata.get("steps", "[]")),
                    "automation": json.loads(metadata.get("automation", "{}"))
                }
            }
        
        return {
            "issue_type": issue_type,
            "runbook": None,
            "message": f"No runbook found for issue type: {issue_type}"
        }
    
    async def add_incident(
        self,
        incident_id: str,
        service: str,
        title: str,
        symptoms: list[str],
        root_cause: str,
        resolution: str,
        category: str,
        priority: str,
        mttr_hours: float
    ) -> dict[str, Any]:
        """Add a new incident to the knowledge base."""
        
        doc = f"""
        Service: {service}
        Title: {title}
        Symptoms: {', '.join(symptoms)}
        Root Cause: {root_cause}
        Resolution: {resolution}
        Category: {category}
        """
        
        self.incidents_collection.add(
            documents=[doc],
            metadatas=[{
                "incident_id": incident_id,
                "service": service,
                "category": category,
                "priority": priority,
                "mttr_hours": mttr_hours,
                "title": title,
                "resolution": resolution,
                "root_cause": root_cause
            }],
            ids=[incident_id]
        )
        
        return {
            "status": "success",
            "message": f"Incident {incident_id} added to knowledge base"
        }
