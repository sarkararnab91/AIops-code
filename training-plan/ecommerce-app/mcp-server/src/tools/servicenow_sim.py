"""
ServiceNow Simulator for MCP Server
Simulates realistic ServiceNow ITSM functionality
"""

import asyncio
import random
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional


class ServiceNowSimulator:
    """Simulates ServiceNow incident management."""
    
    def __init__(self):
        # In-memory incident storage
        self.incidents: dict[str, dict] = {}
        self.incident_counter = 1000
        
        # Pre-populate with historical incidents
        self._seed_incidents()
    
    def _seed_incidents(self):
        """Seed with historical incident data."""
        
        templates = [
            {
                "short_description": "High latency in order processing",
                "service": "order-service",
                "category": "performance",
                "resolution": "Identified database connection pool exhaustion. Increased pool size from 10 to 25 and added connection timeout.",
                "priority": "P2"
            },
            {
                "short_description": "Payment gateway timeout errors",
                "service": "payment-service",
                "category": "availability",
                "resolution": "External payment provider had an outage. Implemented circuit breaker and added retry logic with exponential backoff.",
                "priority": "P1"
            },
            {
                "short_description": "Memory leak in catalog service",
                "service": "catalog-service",
                "category": "performance",
                "resolution": "Found unbounded cache growth in product search. Implemented LRU cache with 10000 item limit.",
                "priority": "P2"
            },
            {
                "short_description": "Cart service pod crash loop",
                "service": "cart-service",
                "category": "availability",
                "resolution": "OOM kill due to memory limits. Increased memory limit from 512Mi to 1Gi and optimized session storage.",
                "priority": "P1"
            },
            {
                "short_description": "Slow API response times during peak hours",
                "service": "api-gateway",
                "category": "performance",
                "resolution": "Added HPA for auto-scaling. Configured minimum 3 replicas during business hours.",
                "priority": "P3"
            },
            {
                "short_description": "Inventory sync failures with external system",
                "service": "inventory-service",
                "category": "integration",
                "resolution": "SSL certificate expired on external inventory API. Updated certificates and added monitoring for expiry.",
                "priority": "P2"
            },
            {
                "short_description": "User authentication failures spike",
                "service": "user-service",
                "category": "security",
                "resolution": "Redis session store was overloaded. Implemented connection pooling and added cache warming on startup.",
                "priority": "P1"
            },
            {
                "short_description": "Notification delivery delays",
                "service": "notification-service",
                "category": "performance",
                "resolution": "Service Bus queue was backing up due to slow consumer. Increased concurrent message handlers from 1 to 5.",
                "priority": "P3"
            },
            {
                "short_description": "Database connection timeout during deployment",
                "service": "order-service",
                "category": "configuration",
                "resolution": "Rolling deployment was overwhelming the database. Implemented blue-green deployment strategy.",
                "priority": "P2"
            },
            {
                "short_description": "High CPU usage causing request timeouts",
                "service": "catalog-service",
                "category": "performance",
                "resolution": "Inefficient regex in search query parsing. Optimized regex and added query caching.",
                "priority": "P2"
            }
        ]
        
        # Create incidents over the past 30 days
        for i, template in enumerate(templates):
            incident_id = f"INC{self.incident_counter + i:07d}"
            created_at = datetime.utcnow() - timedelta(days=random.randint(1, 30))
            
            self.incidents[incident_id] = {
                "id": incident_id,
                "number": incident_id,
                "short_description": template["short_description"],
                "description": f"Detailed investigation of {template['short_description'].lower()}. Multiple users reported issues.",
                "service_name": template["service"],
                "category": template["category"],
                "priority": template["priority"],
                "state": "closed",
                "created_at": created_at.isoformat(),
                "resolved_at": (created_at + timedelta(hours=random.randint(1, 8))).isoformat(),
                "closed_at": (created_at + timedelta(hours=random.randint(9, 24))).isoformat(),
                "resolution_notes": template["resolution"],
                "work_notes": [
                    {"timestamp": created_at.isoformat(), "note": "Incident created from monitoring alert"},
                    {"timestamp": (created_at + timedelta(minutes=15)).isoformat(), "note": "Initial investigation started"},
                    {"timestamp": (created_at + timedelta(hours=1)).isoformat(), "note": "Root cause identified"},
                    {"timestamp": (created_at + timedelta(hours=2)).isoformat(), "note": "Fix deployed to production"}
                ],
                "assigned_to": f"oncall-team-{random.randint(1, 5)}",
                "impact": random.choice(["low", "medium", "high"]),
                "urgency": random.choice(["low", "medium", "high"])
            }
        
        self.incident_counter += len(templates)
    
    async def get_incident(self, incident_id: str) -> dict[str, Any]:
        """Get details of a specific incident."""
        
        if incident_id not in self.incidents:
            return {
                "error": f"Incident {incident_id} not found",
                "status": "not_found"
            }
        
        return {
            "incident": self.incidents[incident_id],
            "status": "success"
        }
    
    async def search_incidents(
        self,
        service_name: Optional[str] = None,
        state: Optional[str] = None,
        priority: Optional[str] = None,
        created_after: Optional[str] = None,
        limit: int = 20
    ) -> dict[str, Any]:
        """Search for incidents matching criteria."""
        
        results = []
        
        for incident in self.incidents.values():
            # Apply filters
            if service_name and incident["service_name"] != service_name:
                continue
            if state and incident["state"] != state:
                continue
            if priority and incident["priority"] != priority:
                continue
            if created_after:
                try:
                    filter_date = datetime.fromisoformat(created_after.replace("Z", "+00:00"))
                    incident_date = datetime.fromisoformat(incident["created_at"])
                    if incident_date < filter_date:
                        continue
                except ValueError:
                    pass
            
            results.append(incident)
        
        # Sort by created_at descending
        results.sort(key=lambda x: x["created_at"], reverse=True)
        
        return {
            "total_count": len(results),
            "returned_count": min(len(results), limit),
            "incidents": results[:limit],
            "filters": {
                "service_name": service_name,
                "state": state,
                "priority": priority,
                "created_after": created_after
            }
        }
    
    async def create_incident(
        self,
        short_description: str,
        service_name: str,
        description: Optional[str] = None,
        priority: str = "P3",
        category: str = "availability"
    ) -> dict[str, Any]:
        """Create a new incident."""
        
        self.incident_counter += 1
        incident_id = f"INC{self.incident_counter:07d}"
        created_at = datetime.utcnow()
        
        incident = {
            "id": incident_id,
            "number": incident_id,
            "short_description": short_description,
            "description": description or short_description,
            "service_name": service_name,
            "category": category,
            "priority": priority,
            "state": "new",
            "created_at": created_at.isoformat(),
            "resolved_at": None,
            "closed_at": None,
            "resolution_notes": None,
            "work_notes": [
                {"timestamp": created_at.isoformat(), "note": "Incident created"}
            ],
            "assigned_to": None,
            "impact": self._priority_to_impact(priority),
            "urgency": self._priority_to_urgency(priority)
        }
        
        self.incidents[incident_id] = incident
        
        return {
            "incident": incident,
            "status": "created",
            "message": f"Incident {incident_id} created successfully"
        }
    
    def _priority_to_impact(self, priority: str) -> str:
        """Map priority to impact."""
        mapping = {"P1": "high", "P2": "high", "P3": "medium", "P4": "low"}
        return mapping.get(priority, "medium")
    
    def _priority_to_urgency(self, priority: str) -> str:
        """Map priority to urgency."""
        mapping = {"P1": "high", "P2": "medium", "P3": "medium", "P4": "low"}
        return mapping.get(priority, "medium")
    
    async def update_incident(
        self,
        incident_id: str,
        state: Optional[str] = None,
        work_notes: Optional[str] = None,
        resolution_notes: Optional[str] = None
    ) -> dict[str, Any]:
        """Update an existing incident."""
        
        if incident_id not in self.incidents:
            return {
                "error": f"Incident {incident_id} not found",
                "status": "not_found"
            }
        
        incident = self.incidents[incident_id]
        now = datetime.utcnow()
        
        # Update state
        if state:
            incident["state"] = state
            if state == "resolved":
                incident["resolved_at"] = now.isoformat()
            elif state == "closed":
                if not incident["resolved_at"]:
                    incident["resolved_at"] = now.isoformat()
                incident["closed_at"] = now.isoformat()
        
        # Add work notes
        if work_notes:
            incident["work_notes"].append({
                "timestamp": now.isoformat(),
                "note": work_notes
            })
        
        # Set resolution notes
        if resolution_notes:
            incident["resolution_notes"] = resolution_notes
            incident["work_notes"].append({
                "timestamp": now.isoformat(),
                "note": f"Resolution: {resolution_notes}"
            })
        
        return {
            "incident": incident,
            "status": "updated",
            "message": f"Incident {incident_id} updated successfully"
        }
    
    async def add_work_note(
        self,
        incident_id: str,
        note: str
    ) -> dict[str, Any]:
        """Add a work note to an incident."""
        
        if incident_id not in self.incidents:
            return {
                "error": f"Incident {incident_id} not found",
                "status": "not_found"
            }
        
        now = datetime.utcnow()
        self.incidents[incident_id]["work_notes"].append({
            "timestamp": now.isoformat(),
            "note": note
        })
        
        return {
            "status": "success",
            "message": f"Work note added to {incident_id}"
        }
    
    async def get_incident_timeline(
        self,
        incident_id: str
    ) -> dict[str, Any]:
        """Get timeline of incident activities."""
        
        if incident_id not in self.incidents:
            return {
                "error": f"Incident {incident_id} not found",
                "status": "not_found"
            }
        
        incident = self.incidents[incident_id]
        
        timeline = []
        
        # Add creation
        timeline.append({
            "timestamp": incident["created_at"],
            "event": "created",
            "description": "Incident created"
        })
        
        # Add work notes
        for note in incident["work_notes"]:
            timeline.append({
                "timestamp": note["timestamp"],
                "event": "work_note",
                "description": note["note"]
            })
        
        # Add resolution
        if incident["resolved_at"]:
            timeline.append({
                "timestamp": incident["resolved_at"],
                "event": "resolved",
                "description": "Incident resolved"
            })
        
        # Add closure
        if incident["closed_at"]:
            timeline.append({
                "timestamp": incident["closed_at"],
                "event": "closed",
                "description": "Incident closed"
            })
        
        # Sort by timestamp
        timeline.sort(key=lambda x: x["timestamp"])
        
        return {
            "incident_id": incident_id,
            "timeline": timeline
        }
    
    async def get_service_incidents_summary(
        self,
        service_name: str,
        days: int = 30
    ) -> dict[str, Any]:
        """Get incident summary for a service."""
        
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        service_incidents = [
            inc for inc in self.incidents.values()
            if inc["service_name"] == service_name
            and datetime.fromisoformat(inc["created_at"]) > cutoff
        ]
        
        # Calculate metrics
        total = len(service_incidents)
        by_priority = {}
        by_category = {}
        mttr_hours = []
        
        for inc in service_incidents:
            # Count by priority
            p = inc["priority"]
            by_priority[p] = by_priority.get(p, 0) + 1
            
            # Count by category
            c = inc["category"]
            by_category[c] = by_category.get(c, 0) + 1
            
            # Calculate MTTR
            if inc["resolved_at"]:
                created = datetime.fromisoformat(inc["created_at"])
                resolved = datetime.fromisoformat(inc["resolved_at"])
                mttr_hours.append((resolved - created).total_seconds() / 3600)
        
        avg_mttr = sum(mttr_hours) / len(mttr_hours) if mttr_hours else 0
        
        return {
            "service": service_name,
            "period_days": days,
            "total_incidents": total,
            "by_priority": by_priority,
            "by_category": by_category,
            "average_mttr_hours": round(avg_mttr, 2),
            "recent_incidents": sorted(
                service_incidents,
                key=lambda x: x["created_at"],
                reverse=True
            )[:5]
        }
