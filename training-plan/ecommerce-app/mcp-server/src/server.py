"""
AIOps MCP Server - Main Server Implementation
Model Context Protocol server for AI-assisted IT Operations
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from tools.azure_monitor import AzureMonitorTools
from tools.servicenow_sim import ServiceNowSimulator
from tools.splunk_sim import SplunkSimulator
from tools.rag_knowledge import RAGKnowledgeBase
from tools.remediation import RemediationEngine

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MCP Server
server = Server("aiops-mcp-server")

# Initialize tool instances (lazy loading)
_azure_monitor: AzureMonitorTools | None = None
_servicenow: ServiceNowSimulator | None = None
_splunk: SplunkSimulator | None = None
_rag: RAGKnowledgeBase | None = None
_remediation: RemediationEngine | None = None


def get_azure_monitor() -> AzureMonitorTools:
    global _azure_monitor
    if _azure_monitor is None:
        _azure_monitor = AzureMonitorTools()
    return _azure_monitor


def get_servicenow() -> ServiceNowSimulator:
    global _servicenow
    if _servicenow is None:
        _servicenow = ServiceNowSimulator()
    return _servicenow


def get_splunk() -> SplunkSimulator:
    global _splunk
    if _splunk is None:
        _splunk = SplunkSimulator()
    return _splunk


def get_rag() -> RAGKnowledgeBase:
    global _rag
    if _rag is None:
        _rag = RAGKnowledgeBase()
    return _rag


def get_remediation() -> RemediationEngine:
    global _remediation
    if _remediation is None:
        _remediation = RemediationEngine()
    return _remediation


# ============================================================================
# Tool Definitions
# ============================================================================

@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available AIOps tools."""
    return [
        # Azure Monitor Tools
        Tool(
            name="get_service_health",
            description="Get health status of a specific service including CPU, memory, error rate, and latency",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service (e.g., catalog-service, order-service)"
                    },
                    "time_range": {
                        "type": "string",
                        "description": "Time range for metrics (e.g., PT1H, PT6H, P1D)",
                        "default": "PT1H"
                    }
                },
                "required": ["service_name"]
            }
        ),
        Tool(
            name="get_all_services_status",
            description="Get a summary of all services' health status",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_details": {
                        "type": "boolean",
                        "description": "Include detailed metrics for each service",
                        "default": False
                    }
                }
            }
        ),
        Tool(
            name="query_logs",
            description="Query application logs using KQL-like syntax",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Service to query logs from"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["error", "warning", "info", "debug"],
                        "description": "Log severity level filter"
                    },
                    "time_range": {
                        "type": "string",
                        "description": "Time range (e.g., PT1H, PT6H)",
                        "default": "PT1H"
                    },
                    "search_text": {
                        "type": "string",
                        "description": "Text to search for in log messages"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of logs to return",
                        "default": 50
                    }
                },
                "required": ["service_name"]
            }
        ),
        Tool(
            name="get_active_alerts",
            description="Get all active alerts from Azure Monitor",
            inputSchema={
                "type": "object",
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Filter by alert severity"
                    },
                    "service_name": {
                        "type": "string",
                        "description": "Filter by service name"
                    }
                }
            }
        ),
        Tool(
            name="get_service_dependencies",
            description="Get the dependency map for a service",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Service to get dependencies for"
                    }
                },
                "required": ["service_name"]
            }
        ),
        
        # ServiceNow Tools
        Tool(
            name="get_incident",
            description="Get details of a specific incident from ServiceNow",
            inputSchema={
                "type": "object",
                "properties": {
                    "incident_id": {
                        "type": "string",
                        "description": "Incident ID (e.g., INC0001234)"
                    }
                },
                "required": ["incident_id"]
            }
        ),
        Tool(
            name="search_incidents",
            description="Search for incidents matching criteria",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Filter by affected service"
                    },
                    "state": {
                        "type": "string",
                        "enum": ["new", "in_progress", "resolved", "closed"],
                        "description": "Filter by incident state"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["P1", "P2", "P3", "P4"],
                        "description": "Filter by priority"
                    },
                    "created_after": {
                        "type": "string",
                        "description": "Filter incidents created after this date (ISO format)"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20
                    }
                }
            }
        ),
        Tool(
            name="create_incident",
            description="Create a new incident in ServiceNow",
            inputSchema={
                "type": "object",
                "properties": {
                    "short_description": {
                        "type": "string",
                        "description": "Brief description of the incident"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description"
                    },
                    "service_name": {
                        "type": "string",
                        "description": "Affected service"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["P1", "P2", "P3", "P4"],
                        "default": "P3"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["performance", "availability", "security", "configuration"],
                        "default": "availability"
                    }
                },
                "required": ["short_description", "service_name"]
            }
        ),
        Tool(
            name="update_incident",
            description="Update an existing incident",
            inputSchema={
                "type": "object",
                "properties": {
                    "incident_id": {
                        "type": "string",
                        "description": "Incident ID to update"
                    },
                    "state": {
                        "type": "string",
                        "enum": ["new", "in_progress", "resolved", "closed"]
                    },
                    "work_notes": {
                        "type": "string",
                        "description": "Notes about work performed"
                    },
                    "resolution_notes": {
                        "type": "string",
                        "description": "Resolution details (required when resolving)"
                    }
                },
                "required": ["incident_id"]
            }
        ),
        
        # Splunk/Log Analysis Tools
        Tool(
            name="analyze_error_patterns",
            description="Analyze error patterns in logs to identify common issues",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Service to analyze"
                    },
                    "time_range": {
                        "type": "string",
                        "default": "PT1H"
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top patterns to return",
                        "default": 10
                    }
                },
                "required": ["service_name"]
            }
        ),
        Tool(
            name="get_log_timeline",
            description="Get a timeline of log events for visualization",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string"
                    },
                    "time_range": {
                        "type": "string",
                        "default": "PT1H"
                    },
                    "interval": {
                        "type": "string",
                        "description": "Aggregation interval (e.g., 1m, 5m, 1h)",
                        "default": "5m"
                    }
                },
                "required": ["service_name"]
            }
        ),
        
        # RAG Knowledge Base Tools
        Tool(
            name="search_similar_incidents",
            description="Search for similar past incidents using semantic search",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Description of the current issue"
                    },
                    "service_name": {
                        "type": "string",
                        "description": "Affected service"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of similar incidents to return",
                        "default": 5
                    }
                },
                "required": ["description"]
            }
        ),
        Tool(
            name="get_resolution_suggestions",
            description="Get suggested resolutions based on historical data",
            inputSchema={
                "type": "object",
                "properties": {
                    "incident_description": {
                        "type": "string",
                        "description": "Description of the incident"
                    },
                    "service_name": {
                        "type": "string"
                    },
                    "error_messages": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Relevant error messages"
                    }
                },
                "required": ["incident_description"]
            }
        ),
        Tool(
            name="get_runbook",
            description="Get runbook for a specific issue type",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "description": "Type of issue (e.g., high_cpu, memory_leak, connection_timeout)"
                    },
                    "service_name": {
                        "type": "string"
                    }
                },
                "required": ["issue_type"]
            }
        ),
        
        # Remediation Tools
        Tool(
            name="suggest_remediation",
            description="Suggest remediation actions based on the incident context",
            inputSchema={
                "type": "object",
                "properties": {
                    "incident_type": {
                        "type": "string",
                        "description": "Type of incident"
                    },
                    "service_name": {
                        "type": "string"
                    },
                    "current_state": {
                        "type": "object",
                        "description": "Current service metrics"
                    }
                },
                "required": ["incident_type", "service_name"]
            }
        ),
        Tool(
            name="execute_remediation",
            description="Execute a remediation action (requires approval for destructive actions)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["restart_pod", "scale_up", "scale_down", "clear_cache", "rollback"],
                        "description": "Remediation action to execute"
                    },
                    "service_name": {
                        "type": "string"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Action-specific parameters"
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, only simulate the action",
                        "default": True
                    }
                },
                "required": ["action", "service_name"]
            }
        ),
        
        # Root Cause Analysis
        Tool(
            name="analyze_root_cause",
            description="Perform root cause analysis for an incident",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Primary affected service"
                    },
                    "symptoms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of observed symptoms"
                    },
                    "time_range": {
                        "type": "string",
                        "default": "PT1H"
                    }
                },
                "required": ["service_name", "symptoms"]
            }
        )
    ]


# ============================================================================
# Tool Implementations
# ============================================================================

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    
    try:
        result = await _execute_tool(name, arguments)
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2, default=str)
        )]
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(
            type="text",
            text=json.dumps({
                "error": str(e),
                "tool": name,
                "status": "failed"
            }, indent=2)
        )]


async def _execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute the appropriate tool based on name."""
    
    # Azure Monitor Tools
    if name == "get_service_health":
        azure = get_azure_monitor()
        return await azure.get_service_health(
            service_name=arguments["service_name"],
            time_range=arguments.get("time_range", "PT1H")
        )
    
    elif name == "get_all_services_status":
        azure = get_azure_monitor()
        return await azure.get_all_services_status(
            include_details=arguments.get("include_details", False)
        )
    
    elif name == "query_logs":
        azure = get_azure_monitor()
        return await azure.query_logs(
            service_name=arguments["service_name"],
            severity=arguments.get("severity"),
            time_range=arguments.get("time_range", "PT1H"),
            search_text=arguments.get("search_text"),
            limit=arguments.get("limit", 50)
        )
    
    elif name == "get_active_alerts":
        azure = get_azure_monitor()
        return await azure.get_active_alerts(
            severity=arguments.get("severity"),
            service_name=arguments.get("service_name")
        )
    
    elif name == "get_service_dependencies":
        azure = get_azure_monitor()
        return await azure.get_service_dependencies(
            service_name=arguments["service_name"]
        )
    
    # ServiceNow Tools
    elif name == "get_incident":
        snow = get_servicenow()
        return await snow.get_incident(arguments["incident_id"])
    
    elif name == "search_incidents":
        snow = get_servicenow()
        return await snow.search_incidents(**arguments)
    
    elif name == "create_incident":
        snow = get_servicenow()
        return await snow.create_incident(**arguments)
    
    elif name == "update_incident":
        snow = get_servicenow()
        return await snow.update_incident(**arguments)
    
    # Splunk Tools
    elif name == "analyze_error_patterns":
        splunk = get_splunk()
        return await splunk.analyze_error_patterns(
            service_name=arguments["service_name"],
            time_range=arguments.get("time_range", "PT1H"),
            top_n=arguments.get("top_n", 10)
        )
    
    elif name == "get_log_timeline":
        splunk = get_splunk()
        return await splunk.get_log_timeline(
            service_name=arguments["service_name"],
            time_range=arguments.get("time_range", "PT1H"),
            interval=arguments.get("interval", "5m")
        )
    
    # RAG Tools
    elif name == "search_similar_incidents":
        rag = get_rag()
        return await rag.search_similar_incidents(
            description=arguments["description"],
            service_name=arguments.get("service_name"),
            top_k=arguments.get("top_k", 5)
        )
    
    elif name == "get_resolution_suggestions":
        rag = get_rag()
        return await rag.get_resolution_suggestions(
            incident_description=arguments["incident_description"],
            service_name=arguments.get("service_name"),
            error_messages=arguments.get("error_messages", [])
        )
    
    elif name == "get_runbook":
        rag = get_rag()
        return await rag.get_runbook(
            issue_type=arguments["issue_type"],
            service_name=arguments.get("service_name")
        )
    
    # Remediation Tools
    elif name == "suggest_remediation":
        remediation = get_remediation()
        return await remediation.suggest_remediation(
            incident_type=arguments["incident_type"],
            service_name=arguments["service_name"],
            current_state=arguments.get("current_state", {})
        )
    
    elif name == "execute_remediation":
        remediation = get_remediation()
        return await remediation.execute_remediation(
            action=arguments["action"],
            service_name=arguments["service_name"],
            parameters=arguments.get("parameters", {}),
            dry_run=arguments.get("dry_run", True)
        )
    
    # Root Cause Analysis
    elif name == "analyze_root_cause":
        # Combine multiple tools for RCA
        azure = get_azure_monitor()
        rag = get_rag()
        
        service_name = arguments["service_name"]
        symptoms = arguments["symptoms"]
        time_range = arguments.get("time_range", "PT1H")
        
        # Get service health
        health = await azure.get_service_health(service_name, time_range)
        
        # Get dependencies
        deps = await azure.get_service_dependencies(service_name)
        
        # Search similar past incidents
        similar = await rag.search_similar_incidents(
            description=" ".join(symptoms),
            service_name=service_name
        )
        
        # Analyze the data
        analysis = _perform_rca(health, deps, similar, symptoms)
        
        return {
            "service": service_name,
            "symptoms": symptoms,
            "analysis": analysis,
            "service_health": health,
            "affected_dependencies": deps.get("dependencies", []),
            "similar_incidents": similar.get("incidents", [])[:3],
            "confidence": analysis.get("confidence", 0.0)
        }
    
    else:
        raise ValueError(f"Unknown tool: {name}")


def _perform_rca(
    health: dict,
    deps: dict,
    similar: dict,
    symptoms: list[str]
) -> dict[str, Any]:
    """Perform root cause analysis based on collected data."""
    
    potential_causes = []
    confidence = 0.0
    
    # Check health metrics for issues
    metrics = health.get("metrics", {})
    
    if metrics.get("cpu_percent", 0) > 80:
        potential_causes.append({
            "cause": "High CPU utilization",
            "evidence": f"CPU at {metrics['cpu_percent']}%",
            "likelihood": 0.8
        })
    
    if metrics.get("memory_percent", 0) > 85:
        potential_causes.append({
            "cause": "Memory pressure",
            "evidence": f"Memory at {metrics['memory_percent']}%",
            "likelihood": 0.75
        })
    
    if metrics.get("error_rate", 0) > 0.05:
        potential_causes.append({
            "cause": "High error rate",
            "evidence": f"Error rate at {metrics['error_rate']*100:.1f}%",
            "likelihood": 0.7
        })
    
    if metrics.get("latency_p99", 0) > 2000:
        potential_causes.append({
            "cause": "Latency degradation",
            "evidence": f"P99 latency at {metrics['latency_p99']}ms",
            "likelihood": 0.65
        })
    
    # Check dependencies
    for dep in deps.get("dependencies", []):
        if dep.get("status") == "degraded":
            potential_causes.append({
                "cause": f"Dependency issue: {dep['name']}",
                "evidence": f"{dep['name']} is degraded",
                "likelihood": 0.7
            })
    
    # Learn from similar incidents
    for incident in similar.get("incidents", [])[:3]:
        if incident.get("similarity", 0) > 0.8:
            potential_causes.append({
                "cause": f"Similar to past incident: {incident.get('id')}",
                "evidence": incident.get("resolution", "N/A"),
                "likelihood": incident.get("similarity", 0)
            })
    
    # Sort by likelihood
    potential_causes.sort(key=lambda x: x["likelihood"], reverse=True)
    
    # Calculate overall confidence
    if potential_causes:
        confidence = min(0.95, sum(c["likelihood"] for c in potential_causes[:3]) / 3)
    
    return {
        "potential_causes": potential_causes[:5],
        "confidence": confidence,
        "recommendation": potential_causes[0]["cause"] if potential_causes else "Unable to determine root cause",
        "next_steps": _get_next_steps(potential_causes)
    }


def _get_next_steps(causes: list[dict]) -> list[str]:
    """Get recommended next steps based on causes."""
    steps = []
    
    if not causes:
        return ["Gather more data", "Check recent deployments", "Review system logs"]
    
    top_cause = causes[0]["cause"].lower()
    
    if "cpu" in top_cause:
        steps = [
            "Profile the application for CPU-intensive operations",
            "Check for infinite loops or runaway processes",
            "Consider scaling horizontally"
        ]
    elif "memory" in top_cause:
        steps = [
            "Analyze heap dumps for memory leaks",
            "Review recent code changes for memory issues",
            "Consider increasing pod memory limits"
        ]
    elif "error" in top_cause:
        steps = [
            "Review error logs for stack traces",
            "Check external service dependencies",
            "Verify configuration changes"
        ]
    elif "latency" in top_cause:
        steps = [
            "Check database query performance",
            "Review network connectivity",
            "Analyze distributed traces"
        ]
    elif "dependency" in top_cause:
        steps = [
            "Check status of dependent services",
            "Verify network connectivity",
            "Review circuit breaker status"
        ]
    else:
        steps = [
            "Review recent deployments",
            "Check configuration changes",
            "Analyze system logs"
        ]
    
    return steps


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Run the MCP server."""
    logger.info("Starting AIOps MCP Server...")
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
