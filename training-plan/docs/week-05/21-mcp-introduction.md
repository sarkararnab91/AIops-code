# Session 21: Introduction to Model Context Protocol (MCP)

## Learning Objectives
- Understand the MCP architecture and concepts
- Set up an MCP development environment
- Create your first MCP server
- Integrate with Claude Desktop

## Duration: 1 hour

---

## 1. What is Model Context Protocol (MCP)?

### Overview

MCP is an open protocol that enables AI assistants to securely connect to data sources and tools. It provides a standardized way for AI models to:

- Access real-time data from external systems
- Execute actions in external tools
- Maintain context across interactions

### Key Concepts

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   AI Client     │────▶│   MCP Server    │────▶│  External APIs  │
│ (Claude, etc.)  │◀────│ (Your Server)   │◀────│ (Azure, etc.)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
       │                        │
       │                        ├── Tools: Execute actions
       │                        ├── Resources: Provide data
       └────────────────────────└── Prompts: Suggest interactions
```

### MCP Components

1. **Tools**: Functions the AI can call (e.g., query logs, create incident)
2. **Resources**: Data sources the AI can read (e.g., metrics, configurations)
3. **Prompts**: Pre-defined prompt templates

---

## 2. Setting Up MCP Development Environment

### Project Structure

```
training-plan/
└── mcp-server/
    ├── pyproject.toml
    ├── src/
    │   └── aiops_mcp/
    │       ├── __init__.py
    │       ├── server.py
    │       ├── tools/
    │       │   ├── __init__.py
    │       │   ├── azure_monitor.py
    │       │   ├── servicenow.py
    │       │   ├── splunk.py
    │       │   └── rag.py
    │       ├── resources/
    │       │   ├── __init__.py
    │       │   └── metrics.py
    │       └── prompts/
    │           ├── __init__.py
    │           └── incident.py
    └── tests/
        └── test_server.py
```

### MCP Server Implementation

```python
# File: training-plan/mcp-server/src/aiops_mcp/server.py
"""
AIOps MCP Server - Main server implementation.
"""

import asyncio
import logging
from typing import Any, Sequence
from datetime import datetime

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    Prompt,
    PromptMessage,
    PromptArgument,
    GetPromptResult,
    CallToolResult,
)
import mcp.server.stdio

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create server instance
server = Server("aiops-mcp-server")


# Tool handlers
@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """List all available tools."""
    return [
        Tool(
            name="query_azure_monitor",
            description="Query Azure Monitor for metrics and logs. Use this to get real-time operational data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "KQL query to execute"
                    },
                    "timespan": {
                        "type": "string",
                        "description": "Time span (e.g., 'PT1H' for 1 hour, 'P1D' for 1 day)",
                        "default": "PT1H"
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Log Analytics workspace ID (optional, uses default if not provided)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_service_health",
            description="Get health status of a specific service including latency, error rate, and availability.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service (e.g., 'catalog-service', 'order-service')"
                    },
                    "timespan": {
                        "type": "string",
                        "description": "Time span to analyze",
                        "default": "PT1H"
                    }
                },
                "required": ["service_name"]
            }
        ),
        Tool(
            name="create_incident",
            description="Create a new incident in ServiceNow (simulated).",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Incident title"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed incident description"
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Incident severity"
                    },
                    "affected_service": {
                        "type": "string",
                        "description": "Name of the affected service"
                    }
                },
                "required": ["title", "description", "severity"]
            }
        ),
        Tool(
            name="search_similar_incidents",
            description="Search for similar past incidents using RAG.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Description of the current issue"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="detect_anomalies",
            description="Run anomaly detection on metrics for a service.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Service to analyze"
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Metrics to analyze (e.g., ['cpu', 'memory', 'latency'])"
                    },
                    "timespan": {
                        "type": "string",
                        "description": "Time span to analyze",
                        "default": "PT1H"
                    }
                },
                "required": ["service_name"]
            }
        ),
        Tool(
            name="get_root_cause",
            description="Perform root cause analysis for an incident.",
            inputSchema={
                "type": "object",
                "properties": {
                    "symptom_services": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Services showing symptoms"
                    },
                    "incident_time": {
                        "type": "string",
                        "description": "ISO timestamp of when the incident started"
                    }
                },
                "required": ["symptom_services"]
            }
        ),
        Tool(
            name="search_logs",
            description="Search logs in Splunk (simulated) for specific patterns.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "Splunk search query"
                    },
                    "earliest": {
                        "type": "string",
                        "description": "Earliest time (e.g., '-1h', '-24h')",
                        "default": "-1h"
                    },
                    "latest": {
                        "type": "string",
                        "description": "Latest time",
                        "default": "now"
                    }
                },
                "required": ["search_query"]
            }
        ),
        Tool(
            name="get_runbook",
            description="Get runbook for a specific issue type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_type": {
                        "type": "string",
                        "description": "Type of issue (e.g., 'high_latency', 'database_connection', 'memory_leak')"
                    }
                },
                "required": ["issue_type"]
            }
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict | None
) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
    """Handle tool execution."""
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    
    try:
        if name == "query_azure_monitor":
            result = await query_azure_monitor(arguments)
        elif name == "get_service_health":
            result = await get_service_health(arguments)
        elif name == "create_incident":
            result = await create_incident(arguments)
        elif name == "search_similar_incidents":
            result = await search_similar_incidents(arguments)
        elif name == "detect_anomalies":
            result = await detect_anomalies(arguments)
        elif name == "get_root_cause":
            result = await get_root_cause(arguments)
        elif name == "search_logs":
            result = await search_logs(arguments)
        elif name == "get_runbook":
            result = await get_runbook(arguments)
        else:
            result = f"Unknown tool: {name}"
        
        return [TextContent(type="text", text=str(result))]
    
    except Exception as e:
        logger.error(f"Error executing tool {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


# Tool implementations (stubs - will be implemented in subsequent sessions)
async def query_azure_monitor(args: dict) -> dict:
    """Query Azure Monitor."""
    # Will be implemented with real Azure Monitor integration
    return {
        "status": "success",
        "query": args.get("query"),
        "results": [
            {"timestamp": "2024-01-15T10:00:00Z", "value": 45.2},
            {"timestamp": "2024-01-15T10:05:00Z", "value": 52.1},
        ],
        "message": "Query executed successfully (simulated)"
    }


async def get_service_health(args: dict) -> dict:
    """Get service health."""
    service = args.get("service_name", "unknown")
    return {
        "service": service,
        "status": "healthy",
        "metrics": {
            "latency_p99_ms": 125,
            "error_rate": 0.02,
            "availability": 99.95,
            "requests_per_minute": 1250
        },
        "timestamp": datetime.now().isoformat()
    }


async def create_incident(args: dict) -> dict:
    """Create incident in ServiceNow."""
    return {
        "incident_id": f"INC{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "title": args.get("title"),
        "severity": args.get("severity"),
        "status": "created",
        "message": "Incident created successfully (simulated)"
    }


async def search_similar_incidents(args: dict) -> dict:
    """Search similar incidents using RAG."""
    return {
        "query": args.get("query"),
        "results": [
            {
                "incident_id": "INC20240110001",
                "title": "High latency in order service",
                "resolution": "Increased database connection pool size",
                "similarity": 0.89
            }
        ]
    }


async def detect_anomalies(args: dict) -> dict:
    """Detect anomalies."""
    return {
        "service": args.get("service_name"),
        "anomalies_detected": True,
        "anomalies": [
            {
                "metric": "cpu",
                "current_value": 92.5,
                "expected_range": [40, 70],
                "severity": "high"
            }
        ]
    }


async def get_root_cause(args: dict) -> dict:
    """Perform root cause analysis."""
    return {
        "symptom_services": args.get("symptom_services"),
        "root_cause": {
            "service": "database",
            "issue": "Connection pool exhaustion",
            "confidence": 0.87
        },
        "recommendation": "Increase max_pool_size in database configuration"
    }


async def search_logs(args: dict) -> dict:
    """Search logs in Splunk."""
    return {
        "query": args.get("search_query"),
        "results": [
            {
                "timestamp": "2024-01-15T10:30:00Z",
                "level": "ERROR",
                "message": "Connection timeout after 30000ms",
                "service": "order-service"
            }
        ],
        "total_count": 15
    }


async def get_runbook(args: dict) -> dict:
    """Get runbook for issue type."""
    runbooks = {
        "high_latency": {
            "title": "High Latency Troubleshooting",
            "steps": [
                "1. Check current CPU and memory utilization",
                "2. Review database connection pool status",
                "3. Check for recent deployments",
                "4. Analyze slow query logs",
                "5. Consider scaling if resource constrained"
            ]
        },
        "database_connection": {
            "title": "Database Connection Issues",
            "steps": [
                "1. Verify database server is reachable",
                "2. Check connection pool status",
                "3. Review firewall rules",
                "4. Check for connection leaks",
                "5. Restart connection pool if needed"
            ]
        }
    }
    
    issue_type = args.get("issue_type", "")
    return runbooks.get(issue_type, {"error": f"No runbook found for: {issue_type}"})


# Resource handlers
@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """List available resources."""
    return [
        Resource(
            uri="aiops://services/health",
            name="Service Health Dashboard",
            description="Current health status of all services",
            mimeType="application/json"
        ),
        Resource(
            uri="aiops://alerts/active",
            name="Active Alerts",
            description="Currently active alerts",
            mimeType="application/json"
        ),
        Resource(
            uri="aiops://incidents/recent",
            name="Recent Incidents",
            description="Recent incidents from the last 24 hours",
            mimeType="application/json"
        )
    ]


@server.read_resource()
async def handle_read_resource(uri: str) -> str:
    """Read a resource."""
    import json
    
    if uri == "aiops://services/health":
        return json.dumps({
            "services": [
                {"name": "catalog-service", "status": "healthy", "latency_p99": 45},
                {"name": "order-service", "status": "degraded", "latency_p99": 350},
                {"name": "payment-service", "status": "healthy", "latency_p99": 120}
            ]
        })
    elif uri == "aiops://alerts/active":
        return json.dumps({
            "alerts": [
                {"id": "ALT001", "severity": "high", "message": "High latency in order-service"}
            ]
        })
    elif uri == "aiops://incidents/recent":
        return json.dumps({
            "incidents": []
        })
    
    return json.dumps({"error": f"Unknown resource: {uri}"})


# Prompt handlers
@server.list_prompts()
async def handle_list_prompts() -> list[Prompt]:
    """List available prompts."""
    return [
        Prompt(
            name="investigate_incident",
            description="Investigate an incident by analyzing logs, metrics, and similar past incidents",
            arguments=[
                PromptArgument(
                    name="service_name",
                    description="The affected service",
                    required=True
                ),
                PromptArgument(
                    name="symptoms",
                    description="Description of the symptoms",
                    required=True
                )
            ]
        ),
        Prompt(
            name="daily_health_report",
            description="Generate a daily health report for all services",
            arguments=[]
        )
    ]


@server.get_prompt()
async def handle_get_prompt(
    name: str,
    arguments: dict[str, str] | None
) -> GetPromptResult:
    """Get a prompt."""
    if name == "investigate_incident":
        service = arguments.get("service_name", "unknown") if arguments else "unknown"
        symptoms = arguments.get("symptoms", "no symptoms provided") if arguments else "no symptoms provided"
        
        return GetPromptResult(
            description=f"Investigate incident for {service}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""Please investigate the following incident:

Service: {service}
Symptoms: {symptoms}

Please:
1. Query Azure Monitor for recent metrics and logs
2. Search for similar past incidents
3. Check the service health status
4. Perform root cause analysis
5. Suggest remediation steps based on runbooks

Provide a structured analysis with your findings and recommendations."""
                    )
                )
            ]
        )
    
    elif name == "daily_health_report":
        return GetPromptResult(
            description="Generate daily health report",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text="""Generate a daily health report for all services. Include:

1. Overall system health status
2. Per-service health metrics (latency, error rate, availability)
3. Active alerts and their status
4. Recent incidents and their resolutions
5. Recommendations for improvements

Format the report in a clear, executive-summary style."""
                    )
                )
            ]
        )
    
    raise ValueError(f"Unknown prompt: {name}")


async def main():
    """Run the MCP server."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="aiops-mcp-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 3. Running the MCP Server

### Configuration for Claude Desktop

```json
{
  "mcpServers": {
    "aiops": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/training-plan/mcp-server",
        "run",
        "aiops-mcp-server"
      ]
    }
  }
}
```

---

## 4. Key Takeaways

1. **MCP Architecture**: Client-Server model with tools, resources, prompts
2. **Tools**: Enable AI to execute actions (query, create, analyze)
3. **Resources**: Provide read access to data
4. **Prompts**: Pre-defined interaction templates
5. **Async Design**: All handlers are async for performance

## Next Session Preview
- Session 22: Implementing Azure Monitor Integration
