# AIOps MCP Server

Model Context Protocol (MCP) server for AI-assisted IT Operations.

## Features

- **Azure Monitor Integration**: Real-time metrics, logs, and alerts from Azure
- **ServiceNow Simulation**: Realistic ITSM functionality with incident management
- **Splunk Simulation**: Log search and error pattern analysis
- **RAG Knowledge Base**: Semantic search over historical incidents using ChromaDB
- **Remediation Engine**: Suggested and automated remediation actions

## Setup

### Prerequisites

- Python 3.11+
- uv package manager
- Azure subscription (for real Azure Monitor integration)
- Claude Desktop or any MCP-compatible client

### Installation

```bash
# Navigate to MCP server directory
cd ecommerce-app/mcp-server

# Create virtual environment with uv
uv venv

# Activate virtual environment
source .venv/bin/activate  # Unix/macOS
# or
.venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -r requirements.txt
```

### Configuration

Create a `.env` file in the mcp-server directory:

```bash
# Azure Configuration (optional - falls back to simulation)
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_RESOURCE_GROUP=rg-aiops-demo
AZURE_LOG_ANALYTICS_WORKSPACE_ID=your-workspace-id

# ChromaDB Configuration
CHROMA_PERSIST_DIR=./data/chromadb

# Logging
LOG_LEVEL=INFO
```

### Running the Server

```bash
# Start the MCP server
uv run python -m src.server
```

### Claude Desktop Integration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "aiops": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.server"],
      "cwd": "/path/to/ecommerce-app/mcp-server",
      "env": {
        "AZURE_SUBSCRIPTION_ID": "your-subscription-id",
        "AZURE_RESOURCE_GROUP": "rg-aiops-demo"
      }
    }
  }
}
```

## Available Tools

### Azure Monitor Tools

| Tool | Description |
|------|-------------|
| `get_service_health` | Get health status of a specific service |
| `get_all_services_status` | Get summary of all services' health |
| `query_logs` | Query application logs |
| `get_active_alerts` | Get active alerts |
| `get_service_dependencies` | Get service dependency map |

### ServiceNow Tools

| Tool | Description |
|------|-------------|
| `get_incident` | Get incident details |
| `search_incidents` | Search for incidents |
| `create_incident` | Create a new incident |
| `update_incident` | Update an existing incident |

### Splunk/Log Analysis Tools

| Tool | Description |
|------|-------------|
| `analyze_error_patterns` | Analyze error patterns in logs |
| `get_log_timeline` | Get log timeline for visualization |

### RAG Knowledge Base Tools

| Tool | Description |
|------|-------------|
| `search_similar_incidents` | Semantic search for similar past incidents |
| `get_resolution_suggestions` | Get resolution suggestions from historical data |
| `get_runbook` | Get runbook for a specific issue type |

### Remediation Tools

| Tool | Description |
|------|-------------|
| `suggest_remediation` | Suggest remediation actions |
| `execute_remediation` | Execute remediation (with dry-run support) |
| `analyze_root_cause` | Perform root cause analysis |

## Example Conversations

### Investigating an Incident

```
User: "The order-service is showing high latency. Can you investigate?"

Claude (using MCP):
1. Calls get_service_health("order-service") - Finds high CPU and latency
2. Calls query_logs("order-service", severity="error") - Finds timeout errors
3. Calls get_service_dependencies("order-service") - Checks downstream services
4. Calls search_similar_incidents("order-service high latency") - Finds similar past incidents
5. Calls suggest_remediation("high_latency", "order-service") - Gets remediation options

Response: "I found that order-service is experiencing high CPU (87%) and P99 latency 
of 3.2 seconds. This appears similar to incident INC0001001 from last month which 
was caused by database connection pool exhaustion. I recommend scaling up and 
checking the connection pool configuration."
```

### Creating an Incident

```
User: "Create a P2 incident for the payment service SSL certificate expiring soon"

Claude (using MCP):
1. Calls create_incident(
     short_description="SSL certificate expiring for payment-service",
     service_name="payment-service",
     priority="P2",
     category="security"
   )

Response: "I've created incident INC0001011 for the payment-service SSL certificate 
issue with P2 priority. Would you like me to look up the runbook for certificate renewal?"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         MCP Server                               │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Azure     │  │ ServiceNow  │  │   Splunk    │             │
│  │  Monitor    │  │  Simulator  │  │  Simulator  │             │
│  │   Tools     │  │             │  │             │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          │                                      │
│  ┌─────────────┐  ┌─────────────┐                              │
│  │    RAG      │  │ Remediation │                              │
│  │  Knowledge  │  │   Engine    │                              │
│  │    Base     │  │             │                              │
│  └──────┬──────┘  └──────┬──────┘                              │
│         │                │                                      │
│         └────────┬───────┘                                      │
│                  │                                              │
│         ┌────────┴────────┐                                     │
│         │   MCP Protocol  │                                     │
│         │    (stdio)      │                                     │
│         └────────┬────────┘                                     │
└──────────────────┼──────────────────────────────────────────────┘
                   │
                   ▼
           ┌──────────────┐
           │ Claude       │
           │ Desktop      │
           └──────────────┘
```

## Development

### Running Tests

```bash
uv run pytest tests/ -v
```

### Adding New Tools

1. Create a new tool class in `src/tools/`
2. Add to `__init__.py` exports
3. Register tool in `server.py` `list_tools()`
4. Implement handler in `call_tool()`

## License

MIT
