# Session 23: ServiceNow Simulation for MCP

## Learning Objectives
- Build a realistic ServiceNow simulation
- Implement incident lifecycle management
- Create CMDB integration
- Enable change management workflows

## Duration: 1 hour

---

## 1. ServiceNow Simulator

### ServiceNow Simulation Implementation

```python
# File: training-plan/mcp-server/src/aiops_mcp/tools/servicenow.py
"""
ServiceNow simulation for MCP server.
Simulates incident, problem, and change management workflows.
"""

import random
import string
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import json


class IncidentState(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentSeverity(str, Enum):
    CRITICAL = "1-critical"
    HIGH = "2-high"
    MEDIUM = "3-medium"
    LOW = "4-low"


class ChangeState(str, Enum):
    NEW = "new"
    ASSESS = "assess"
    AUTHORIZE = "authorize"
    SCHEDULED = "scheduled"
    IMPLEMENT = "implement"
    REVIEW = "review"
    CLOSED = "closed"


@dataclass
class Incident:
    """ServiceNow Incident record."""
    number: str
    short_description: str
    description: str
    severity: IncidentSeverity
    state: IncidentState
    assigned_to: Optional[str]
    assignment_group: str
    affected_service: str
    category: str
    subcategory: str
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    work_notes: List[str] = field(default_factory=list)
    related_incidents: List[str] = field(default_factory=list)
    parent_incident: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "short_description": self.short_description,
            "description": self.description,
            "severity": self.severity.value,
            "state": self.state.value,
            "assigned_to": self.assigned_to,
            "assignment_group": self.assignment_group,
            "affected_service": self.affected_service,
            "category": self.category,
            "subcategory": self.subcategory,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_notes": self.resolution_notes,
            "work_notes": self.work_notes,
            "related_incidents": self.related_incidents,
            "parent_incident": self.parent_incident
        }


@dataclass
class CMDBItem:
    """Configuration Management Database Item."""
    sys_id: str
    name: str
    class_name: str  # e.g., 'cmdb_ci_app_server', 'cmdb_ci_database'
    environment: str  # 'production', 'staging', 'development'
    status: str  # 'operational', 'non-operational', 'under_maintenance'
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass 
class ChangeRequest:
    """ServiceNow Change Request."""
    number: str
    short_description: str
    description: str
    type: str  # 'standard', 'normal', 'emergency'
    state: ChangeState
    risk: str  # 'high', 'medium', 'low'
    impact: str
    planned_start: datetime
    planned_end: datetime
    affected_cis: List[str]
    created_at: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "short_description": self.short_description,
            "description": self.description,
            "type": self.type,
            "state": self.state.value,
            "risk": self.risk,
            "impact": self.impact,
            "planned_start": self.planned_start.isoformat(),
            "planned_end": self.planned_end.isoformat(),
            "affected_cis": self.affected_cis,
            "created_at": self.created_at.isoformat()
        }


class ServiceNowSimulator:
    """
    Simulates ServiceNow ITSM functionality.
    """
    
    def __init__(self):
        self.incidents: Dict[str, Incident] = {}
        self.changes: Dict[str, ChangeRequest] = {}
        self.cmdb: Dict[str, CMDBItem] = {}
        self.incident_counter = 1000
        self.change_counter = 1000
        
        # Initialize sample CMDB
        self._init_cmdb()
        
        # Initialize sample historical incidents
        self._init_historical_incidents()
    
    def _init_cmdb(self):
        """Initialize CMDB with sample data."""
        services = [
            ("catalog-service", "cmdb_ci_app_server", ["database-primary"]),
            ("order-service", "cmdb_ci_app_server", ["database-primary", "redis-cache", "service-bus"]),
            ("cart-service", "cmdb_ci_app_server", ["redis-cache"]),
            ("payment-service", "cmdb_ci_app_server", ["payment-gateway"]),
            ("user-service", "cmdb_ci_app_server", ["database-primary", "redis-cache"]),
            ("notification-service", "cmdb_ci_app_server", ["service-bus", "email-gateway"]),
            ("inventory-service", "cmdb_ci_app_server", ["database-primary"]),
            ("database-primary", "cmdb_ci_database", []),
            ("redis-cache", "cmdb_ci_cache", []),
            ("service-bus", "cmdb_ci_messaging", []),
        ]
        
        for name, class_name, deps in services:
            sys_id = f"ci_{name.replace('-', '_')}"
            self.cmdb[sys_id] = CMDBItem(
                sys_id=sys_id,
                name=name,
                class_name=class_name,
                environment="production",
                status="operational",
                dependencies=deps,
                attributes={
                    "version": "1.0.0",
                    "owner": "platform-team",
                    "criticality": "high" if "database" in name else "medium"
                }
            )
    
    def _init_historical_incidents(self):
        """Initialize with historical incidents for RAG."""
        historical = [
            {
                "title": "Database connection pool exhausted",
                "description": "Order service experiencing connection timeouts",
                "severity": IncidentSeverity.CRITICAL,
                "service": "order-service",
                "resolution": "Increased max_pool_size from 20 to 50 and implemented connection pooling optimization"
            },
            {
                "title": "High latency in payment processing",
                "description": "Payment service p99 latency exceeded 5 seconds",
                "severity": IncidentSeverity.HIGH,
                "service": "payment-service",
                "resolution": "Identified slow database query, added index on transaction_date column"
            },
            {
                "title": "Memory leak in catalog service",
                "description": "Catalog service memory usage growing continuously",
                "severity": IncidentSeverity.HIGH,
                "service": "catalog-service",
                "resolution": "Fixed memory leak in image caching module, deployed hotfix"
            },
            {
                "title": "Redis cache connection failures",
                "description": "Intermittent connection failures to Redis cluster",
                "severity": IncidentSeverity.MEDIUM,
                "service": "cart-service",
                "resolution": "Network team fixed MTU mismatch, increased connection timeout"
            },
            {
                "title": "Service Bus message queue backlog",
                "description": "Notification service falling behind on message processing",
                "severity": IncidentSeverity.MEDIUM,
                "service": "notification-service",
                "resolution": "Scaled notification service to 5 replicas, optimized message batch processing"
            }
        ]
        
        for i, inc in enumerate(historical):
            created = datetime.now() - timedelta(days=random.randint(7, 90))
            resolved = created + timedelta(hours=random.randint(1, 48))
            
            incident = Incident(
                number=f"INC{1000 + i:07d}",
                short_description=inc["title"],
                description=inc["description"],
                severity=inc["severity"],
                state=IncidentState.CLOSED,
                assigned_to="ops-team",
                assignment_group="Platform Operations",
                affected_service=inc["service"],
                category="Service Disruption",
                subcategory="Performance",
                created_at=created,
                updated_at=resolved,
                resolved_at=resolved,
                resolution_notes=inc["resolution"]
            )
            self.incidents[incident.number] = incident
    
    def _generate_number(self, prefix: str) -> str:
        """Generate unique ticket number."""
        if prefix == "INC":
            self.incident_counter += 1
            return f"INC{self.incident_counter:07d}"
        elif prefix == "CHG":
            self.change_counter += 1
            return f"CHG{self.change_counter:07d}"
        return f"{prefix}{random.randint(100000, 999999)}"
    
    async def create_incident(
        self,
        title: str,
        description: str,
        severity: str,
        affected_service: str,
        category: str = "Service Disruption"
    ) -> Dict[str, Any]:
        """Create a new incident."""
        sev = IncidentSeverity(severity) if severity in [s.value for s in IncidentSeverity] else IncidentSeverity.MEDIUM
        
        incident = Incident(
            number=self._generate_number("INC"),
            short_description=title,
            description=description,
            severity=sev,
            state=IncidentState.NEW,
            assigned_to=None,
            assignment_group="Platform Operations",
            affected_service=affected_service,
            category=category,
            subcategory="General",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.incidents[incident.number] = incident
        
        return {
            "status": "created",
            "incident": incident.to_dict(),
            "message": f"Incident {incident.number} created successfully"
        }
    
    async def update_incident(
        self,
        number: str,
        state: Optional[str] = None,
        work_note: Optional[str] = None,
        resolution: Optional[str] = None,
        assigned_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an incident."""
        if number not in self.incidents:
            return {"status": "error", "message": f"Incident {number} not found"}
        
        incident = self.incidents[number]
        incident.updated_at = datetime.now()
        
        if state:
            incident.state = IncidentState(state)
            if incident.state == IncidentState.RESOLVED:
                incident.resolved_at = datetime.now()
        
        if work_note:
            incident.work_notes.append(f"[{datetime.now().isoformat()}] {work_note}")
        
        if resolution:
            incident.resolution_notes = resolution
        
        if assigned_to:
            incident.assigned_to = assigned_to
        
        return {
            "status": "updated",
            "incident": incident.to_dict()
        }
    
    async def get_incident(self, number: str) -> Dict[str, Any]:
        """Get incident details."""
        if number not in self.incidents:
            return {"status": "error", "message": f"Incident {number} not found"}
        
        return {
            "status": "success",
            "incident": self.incidents[number].to_dict()
        }
    
    async def search_incidents(
        self,
        query: Optional[str] = None,
        state: Optional[str] = None,
        service: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Search for incidents."""
        results = []
        
        for incident in self.incidents.values():
            # Filter by state
            if state and incident.state.value != state:
                continue
            
            # Filter by service
            if service and service.lower() not in incident.affected_service.lower():
                continue
            
            # Filter by severity
            if severity and incident.severity.value != severity:
                continue
            
            # Filter by query (search in description)
            if query:
                query_lower = query.lower()
                if (query_lower not in incident.short_description.lower() and
                    query_lower not in incident.description.lower()):
                    continue
            
            results.append(incident.to_dict())
        
        # Sort by created_at descending
        results.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {
            "status": "success",
            "count": len(results[:limit]),
            "total": len(results),
            "incidents": results[:limit]
        }
    
    async def get_cmdb_item(self, name: str) -> Dict[str, Any]:
        """Get CMDB item by name."""
        for item in self.cmdb.values():
            if item.name.lower() == name.lower():
                return {
                    "status": "success",
                    "item": {
                        "sys_id": item.sys_id,
                        "name": item.name,
                        "class": item.class_name,
                        "environment": item.environment,
                        "status": item.status,
                        "dependencies": item.dependencies,
                        "dependents": [
                            i.name for i in self.cmdb.values()
                            if item.name in i.dependencies
                        ],
                        "attributes": item.attributes
                    }
                }
        
        return {"status": "error", "message": f"CMDB item '{name}' not found"}
    
    async def get_service_dependencies(self, service_name: str) -> Dict[str, Any]:
        """Get all dependencies for a service."""
        for item in self.cmdb.values():
            if item.name.lower() == service_name.lower():
                # Get full dependency tree
                dependencies = []
                to_process = list(item.dependencies)
                processed = set()
                
                while to_process:
                    dep_name = to_process.pop(0)
                    if dep_name in processed:
                        continue
                    processed.add(dep_name)
                    
                    for dep_item in self.cmdb.values():
                        if dep_item.name == dep_name:
                            dependencies.append({
                                "name": dep_item.name,
                                "type": dep_item.class_name,
                                "status": dep_item.status
                            })
                            to_process.extend(dep_item.dependencies)
                
                return {
                    "status": "success",
                    "service": service_name,
                    "dependencies": dependencies
                }
        
        return {"status": "error", "message": f"Service '{service_name}' not found in CMDB"}


# Singleton instance
_servicenow_sim: Optional[ServiceNowSimulator] = None


def get_servicenow_simulator() -> ServiceNowSimulator:
    """Get or create ServiceNow simulator."""
    global _servicenow_sim
    
    if _servicenow_sim is None:
        _servicenow_sim = ServiceNowSimulator()
    
    return _servicenow_sim
```

---

## 2. Key Takeaways

1. **Realistic Simulation**: Model real ServiceNow data structures
2. **CMDB Integration**: Track service dependencies
3. **Incident Lifecycle**: Support full incident workflow
4. **Historical Data**: Enable RAG-based learning
5. **Search Capabilities**: Enable flexible incident queries

## Next Session Preview
- Session 24: Splunk Simulation for Log Analysis
