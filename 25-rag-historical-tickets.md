# Session 25: Building RAG for Historical Tickets

## Learning Objectives
- Implement RAG (Retrieval-Augmented Generation) system
- Use ChromaDB for vector storage
- Build semantic search for incidents
- Integrate with MCP server

## Duration: 1 hour

---

## 1. RAG System Architecture

### Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Query Input    │────▶│  Embedding      │────▶│   ChromaDB      │
│  (Current Issue)│     │  (Azure OpenAI) │     │  (Vector Store) │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                          │
                        ┌─────────────────┐               │
                        │  Similar        │◀──────────────┘
                        │  Incidents      │
                        └────────┬────────┘
                                 │
                        ┌────────▼────────┐
                        │  Context +      │
                        │  Resolution     │
                        └─────────────────┘
```

---

## 2. RAG Implementation

### RAG System for Incident Resolution

```python
# File: training-plan/mcp-server/src/aiops_mcp/tools/rag.py
"""
RAG system for historical incident resolution.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

try:
    from openai import AzureOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


@dataclass
class IncidentDocument:
    """A document representing a historical incident."""
    incident_id: str
    title: str
    description: str
    symptoms: str
    root_cause: str
    resolution: str
    affected_service: str
    severity: str
    resolution_time_hours: float
    tags: List[str] = field(default_factory=list)
    
    def to_text(self) -> str:
        """Convert to searchable text."""
        return f"""
Incident: {self.title}
Description: {self.description}
Symptoms: {self.symptoms}
Root Cause: {self.root_cause}
Resolution: {self.resolution}
Affected Service: {self.affected_service}
Severity: {self.severity}
Tags: {', '.join(self.tags)}
        """.strip()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "symptoms": self.symptoms,
            "root_cause": self.root_cause,
            "resolution": self.resolution,
            "affected_service": self.affected_service,
            "severity": self.severity,
            "resolution_time_hours": self.resolution_time_hours,
            "tags": self.tags
        }


class IncidentKnowledgeBase:
    """
    Knowledge base of historical incidents using RAG.
    """
    
    # Sample historical incidents for training
    SAMPLE_INCIDENTS = [
        IncidentDocument(
            incident_id="INC-2024-001",
            title="Database Connection Pool Exhausted",
            description="Order service unable to connect to database during peak traffic",
            symptoms="Connection timeout errors, 503 errors, high latency",
            root_cause="Max connections set too low (20) for peak traffic",
            resolution="1. Increased max_pool_size from 20 to 100\n2. Implemented connection pooling with HikariCP\n3. Added connection timeout monitoring",
            affected_service="order-service",
            severity="critical",
            resolution_time_hours=2.5,
            tags=["database", "connection-pool", "performance", "timeout"]
        ),
        IncidentDocument(
            incident_id="INC-2024-002",
            title="Memory Leak in Catalog Service",
            description="Catalog service memory usage growing continuously until OOM",
            symptoms="Increasing memory usage, eventual pod restarts, slow responses",
            root_cause="Image caching not clearing expired entries",
            resolution="1. Fixed cache eviction policy\n2. Implemented max cache size limit\n3. Added memory usage alerts at 80%",
            affected_service="catalog-service",
            severity="high",
            resolution_time_hours=4.0,
            tags=["memory-leak", "caching", "oom", "performance"]
        ),
        IncidentDocument(
            incident_id="INC-2024-003",
            title="Redis Connection Failures",
            description="Intermittent failures connecting to Redis cluster",
            symptoms="Cache misses, increased database load, timeout errors",
            root_cause="Network MTU mismatch between pods and Redis nodes",
            resolution="1. Network team fixed MTU settings\n2. Increased connection timeout to 5s\n3. Implemented circuit breaker pattern",
            affected_service="cart-service",
            severity="high",
            resolution_time_hours=3.0,
            tags=["redis", "network", "timeout", "cache"]
        ),
        IncidentDocument(
            incident_id="INC-2024-004",
            title="Payment Gateway Timeout",
            description="Payment processing timing out during checkout",
            symptoms="Payment failures, abandoned carts, customer complaints",
            root_cause="Third-party payment gateway had latency issues",
            resolution="1. Implemented retry with exponential backoff\n2. Added fallback payment processor\n3. Increased timeout to 30s\n4. Added payment gateway health check",
            affected_service="payment-service",
            severity="critical",
            resolution_time_hours=1.5,
            tags=["payment", "timeout", "third-party", "gateway"]
        ),
        IncidentDocument(
            incident_id="INC-2024-005",
            title="Kafka Consumer Lag",
            description="Notification service falling behind on message processing",
            symptoms="Delayed notifications, growing message backlog",
            root_cause="Single consumer unable to keep up with message volume",
            resolution="1. Scaled to 5 consumer instances\n2. Implemented batch processing (100 messages per batch)\n3. Added consumer lag monitoring and alerts",
            affected_service="notification-service",
            severity="medium",
            resolution_time_hours=2.0,
            tags=["kafka", "consumer-lag", "scaling", "messaging"]
        ),
        IncidentDocument(
            incident_id="INC-2024-006",
            title="SSL Certificate Expiry",
            description="API endpoints returning SSL errors",
            symptoms="SSL handshake failures, 502 errors from ingress",
            root_cause="TLS certificate expired, auto-renewal failed",
            resolution="1. Manually renewed certificate\n2. Fixed cert-manager configuration\n3. Added certificate expiry monitoring (30 days warning)",
            affected_service="api-gateway",
            severity="critical",
            resolution_time_hours=0.5,
            tags=["ssl", "certificate", "ingress", "tls"]
        ),
        IncidentDocument(
            incident_id="INC-2024-007",
            title="Slow Database Queries",
            description="Order queries taking >10 seconds during peak hours",
            symptoms="High latency, database CPU at 100%, timeout errors",
            root_cause="Missing index on order_date column for date range queries",
            resolution="1. Added composite index (customer_id, order_date)\n2. Implemented query caching\n3. Added slow query logging",
            affected_service="order-service",
            severity="high",
            resolution_time_hours=3.0,
            tags=["database", "slow-query", "index", "performance"]
        ),
        IncidentDocument(
            incident_id="INC-2024-008",
            title="Kubernetes Pod Evictions",
            description="Pods being evicted due to resource pressure",
            symptoms="Random pod restarts, service interruptions",
            root_cause="Node memory pressure from logging sidecar memory leak",
            resolution="1. Fixed logging sidecar memory limit\n2. Implemented pod disruption budgets\n3. Added node pressure monitoring",
            affected_service="all-services",
            severity="high",
            resolution_time_hours=4.0,
            tags=["kubernetes", "pod-eviction", "memory", "node-pressure"]
        ),
        IncidentDocument(
            incident_id="INC-2024-009",
            title="API Rate Limiting Triggering Incorrectly",
            description="Legitimate requests being rate limited",
            symptoms="429 errors for normal traffic, customer complaints",
            root_cause="Rate limit bucket sharing across all customers",
            resolution="1. Implemented per-customer rate limiting\n2. Increased global limit 10x\n3. Added rate limit headers to responses",
            affected_service="api-gateway",
            severity="medium",
            resolution_time_hours=2.0,
            tags=["rate-limiting", "api", "configuration"]
        ),
        IncidentDocument(
            incident_id="INC-2024-010",
            title="Inventory Sync Failure",
            description="Inventory counts not updating after orders",
            symptoms="Overselling, incorrect stock levels, order failures",
            root_cause="Dead letter queue not being processed",
            resolution="1. Deployed DLQ processor\n2. Replayed failed messages\n3. Added DLQ depth monitoring and alerts",
            affected_service="inventory-service",
            severity="critical",
            resolution_time_hours=2.5,
            tags=["inventory", "messaging", "dlq", "sync"]
        )
    ]
    
    def __init__(
        self,
        persist_directory: str = "/data/chromadb",
        collection_name: str = "incidents"
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self.embedding_fn = None
        
        self._initialize()
    
    def _initialize(self):
        """Initialize ChromaDB and embeddings."""
        if not CHROMADB_AVAILABLE:
            print("ChromaDB not available. Using simple search.")
            return
        
        # Create persist directory
        Path(self.persist_directory).mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB
        self.client = chromadb.PersistentClient(path=self.persist_directory)
        
        # Set up embedding function
        if OPENAI_AVAILABLE and os.getenv("AZURE_OPENAI_ENDPOINT"):
            # Use Azure OpenAI embeddings
            self.embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_type="azure",
                model_name="text-embedding-ada-002"
            )
        else:
            # Use default embeddings
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_fn,
            metadata={"description": "Historical incident resolutions"}
        )
        
        # Load sample incidents if collection is empty
        if self.collection.count() == 0:
            self._load_sample_incidents()
    
    def _load_sample_incidents(self):
        """Load sample incidents into the knowledge base."""
        documents = []
        metadatas = []
        ids = []
        
        for incident in self.SAMPLE_INCIDENTS:
            documents.append(incident.to_text())
            metadatas.append({
                "incident_id": incident.incident_id,
                "title": incident.title,
                "affected_service": incident.affected_service,
                "severity": incident.severity,
                "resolution_time_hours": incident.resolution_time_hours,
                "tags": ",".join(incident.tags)
            })
            ids.append(incident.incident_id)
        
        if self.collection:
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
    
    async def search_similar(
        self,
        query: str,
        limit: int = 5,
        filter_service: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for similar incidents."""
        if not CHROMADB_AVAILABLE or not self.collection:
            # Fallback to simple keyword search
            return self._simple_search(query, limit, filter_service)
        
        # Build where filter
        where = None
        if filter_service:
            where = {"affected_service": filter_service}
        
        results = self.collection.query(
            query_texts=[query],
            n_results=limit,
            where=where
        )
        
        # Format results
        similar_incidents = []
        if results and results['ids'] and results['ids'][0]:
            for i, incident_id in enumerate(results['ids'][0]):
                # Get full incident details
                incident = self._get_incident_by_id(incident_id)
                if incident:
                    similar_incidents.append({
                        **incident.to_dict(),
                        "similarity_score": 1 - (results['distances'][0][i] if results['distances'] else 0)
                    })
        
        return {
            "status": "success",
            "query": query,
            "results": similar_incidents,
            "count": len(similar_incidents)
        }
    
    async def add_incident(
        self,
        incident: IncidentDocument
    ) -> Dict[str, Any]:
        """Add a new incident to the knowledge base."""
        if not CHROMADB_AVAILABLE or not self.collection:
            return {"status": "error", "message": "ChromaDB not available"}
        
        self.collection.add(
            documents=[incident.to_text()],
            metadatas=[{
                "incident_id": incident.incident_id,
                "title": incident.title,
                "affected_service": incident.affected_service,
                "severity": incident.severity,
                "resolution_time_hours": incident.resolution_time_hours,
                "tags": ",".join(incident.tags)
            }],
            ids=[incident.incident_id]
        )
        
        return {
            "status": "success",
            "message": f"Incident {incident.incident_id} added to knowledge base"
        }
    
    async def get_runbook(
        self,
        issue_type: str
    ) -> Dict[str, Any]:
        """Get runbook for a specific issue type."""
        runbooks = {
            "high_latency": {
                "title": "High Latency Troubleshooting Runbook",
                "description": "Steps to diagnose and resolve high latency issues",
                "steps": [
                    {
                        "step": 1,
                        "action": "Check current resource utilization",
                        "command": "kubectl top pods -n ecommerce",
                        "expected": "Identify pods with high CPU/memory"
                    },
                    {
                        "step": 2,
                        "action": "Check database connection pool",
                        "query": "SELECT count(*) FROM pg_stat_activity",
                        "expected": "Connections should be below max_connections"
                    },
                    {
                        "step": 3,
                        "action": "Review slow query logs",
                        "command": "SELECT * FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10",
                        "expected": "Identify queries taking >100ms"
                    },
                    {
                        "step": 4,
                        "action": "Check for recent deployments",
                        "command": "kubectl rollout history deployment -n ecommerce",
                        "expected": "Identify recent changes that may correlate"
                    },
                    {
                        "step": 5,
                        "action": "Scale if resource constrained",
                        "command": "kubectl scale deployment <name> --replicas=<n> -n ecommerce",
                        "expected": "Latency should decrease after scaling"
                    }
                ],
                "escalation": "If issue persists after 30 minutes, escalate to Platform Team"
            },
            "database_connection": {
                "title": "Database Connection Issues Runbook",
                "steps": [
                    {
                        "step": 1,
                        "action": "Verify database is reachable",
                        "command": "nc -zv <db-host> 5432"
                    },
                    {
                        "step": 2,
                        "action": "Check connection pool status",
                        "query": "SELECT * FROM pg_stat_activity WHERE state = 'active'"
                    },
                    {
                        "step": 3,
                        "action": "Review firewall rules"
                    },
                    {
                        "step": 4,
                        "action": "Check for connection leaks in application logs"
                    },
                    {
                        "step": 5,
                        "action": "Restart connection pool if needed"
                    }
                ]
            },
            "memory_leak": {
                "title": "Memory Leak Investigation Runbook",
                "steps": [
                    {
                        "step": 1,
                        "action": "Capture heap dump",
                        "command": "kubectl exec <pod> -- jmap -dump:live,format=b,file=/tmp/heap.hprof 1"
                    },
                    {
                        "step": 2,
                        "action": "Analyze with MAT or similar tool"
                    },
                    {
                        "step": 3,
                        "action": "Check GC logs for patterns"
                    },
                    {
                        "step": 4,
                        "action": "Review recent code changes"
                    },
                    {
                        "step": 5,
                        "action": "Deploy fix or rollback"
                    }
                ]
            }
        }
        
        runbook = runbooks.get(issue_type)
        if runbook:
            return {"status": "success", "runbook": runbook}
        
        # Search for related incidents
        similar = await self.search_similar(issue_type, limit=3)
        
        return {
            "status": "not_found",
            "message": f"No specific runbook for '{issue_type}'",
            "related_incidents": similar.get("results", [])
        }
    
    def _get_incident_by_id(self, incident_id: str) -> Optional[IncidentDocument]:
        """Get incident by ID from sample data."""
        for incident in self.SAMPLE_INCIDENTS:
            if incident.incident_id == incident_id:
                return incident
        return None
    
    def _simple_search(
        self,
        query: str,
        limit: int,
        filter_service: Optional[str]
    ) -> Dict[str, Any]:
        """Simple keyword-based search fallback."""
        query_lower = query.lower()
        results = []
        
        for incident in self.SAMPLE_INCIDENTS:
            if filter_service and incident.affected_service != filter_service:
                continue
            
            text = incident.to_text().lower()
            if query_lower in text:
                # Simple scoring based on occurrence count
                score = text.count(query_lower) / len(text)
                results.append({
                    **incident.to_dict(),
                    "similarity_score": min(score * 10, 1.0)
                })
        
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        return {
            "status": "success",
            "query": query,
            "results": results[:limit],
            "count": len(results[:limit]),
            "method": "keyword_search"
        }


# Singleton instance
_knowledge_base: Optional[IncidentKnowledgeBase] = None


def get_knowledge_base() -> IncidentKnowledgeBase:
    """Get or create knowledge base."""
    global _knowledge_base
    
    if _knowledge_base is None:
        _knowledge_base = IncidentKnowledgeBase()
    
    return _knowledge_base
```

---

## 3. Key Takeaways

1. **RAG Architecture**: Embedding + Vector DB + Context Retrieval
2. **ChromaDB**: Lightweight vector store for semantic search
3. **Sample Data**: Pre-populated with realistic incidents
4. **Runbooks**: Structured troubleshooting guides
5. **Fallback**: Keyword search when ChromaDB unavailable

## Next Session Preview
- Session 26: Complete MCP Server Integration
