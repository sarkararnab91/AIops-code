# AIOps Training Program: From Traditional IT Operations to AgentOps

## 🎯 Course Overview

An **8-week, 40-hour** hands-on training program demonstrating the evolution from traditional IT monitoring to ML-based AIOps to intelligent AgentOps. Participants build a real-world e-commerce microservices application on Azure and progressively enhance its operational intelligence.

### Learning Progression

```
Week 1-2                    Week 3-4                    Week 5-7                    Week 8
┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│   Traditional   │   →    │    ML-Based     │   →    │    AgentOps     │   →    │    Capstone     │
│   Monitoring    │        │     AIOps       │        │   with MCP      │        │      Demo       │
├─────────────────┤        ├─────────────────┤        ├─────────────────┤        ├─────────────────┤
│ • Azure Setup   │        │ • Failure Sim   │        │ • MCP Server    │        │ • Cascading     │
│ • Microservices │        │ • Anomaly Det.  │        │ • 15 AI Tools   │        │   Failure       │
│ • App Insights  │        │ • Forecasting   │        │ • ServiceNow    │        │ • Value         │
│ • Log Analytics │        │ • Correlation   │        │ • Splunk Sim    │        │   Progression   │
│ • Dashboards    │        │ • ML API        │        │ • RAG System    │        │ • Live Demo     │
└─────────────────┘        └─────────────────┘        └─────────────────┘        └─────────────────┘

Detection Time:  5+ min    →    2 min           →    1 min           →    <1 min (predictive)
MTTR:            45 min    →    25 min          →    8 min           →    Automated
```

---

## 🛒 Demo Application: Perfume & Dessert E-Commerce Store

A realistic 3-tier microservices architecture deployed on Azure:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND                                        │
│                         Vue.js Application                                   │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           API GATEWAY                                        │
│                    Azure API Management / Ingress                            │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
    ┌────────────┬───────────────┼───────────────┬────────────┬───────────────┐
    ▼            ▼               ▼               ▼            ▼               ▼
┌────────┐  ┌────────┐      ┌────────┐      ┌────────┐  ┌────────┐      ┌────────┐
│Catalog │  │  Cart  │      │Payment │      │ Order  │  │  User  │      │Inventory│
│Service │  │Service │      │Service │      │Service │  │Service │      │Service │
│(Python)│  │(Python)│      │(Python)│      │(Python)│  │(Python)│      │(Python)│
└───┬────┘  └───┬────┘      └───┬────┘      └───┬────┘  └───┬────┘      └───┬────┘
    │           │               │               │           │               │
    ▼           ▼               ▼               ▼           ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            DATA LAYER                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Cosmos DB   │  │    Redis     │  │  Service Bus │  │ Blob Storage │    │
│  │ (Serverless) │  │  (Basic C0)  │  │   (Basic)    │  │  (Cool Tier) │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Product Categories
- **Perfumes**: Luxury fragrances, colognes, and scented products
- **Desserts**: Gourmet cakes, pastries, chocolates, and confections

---

## 📊 Azure Infrastructure (Cost-Optimized)

| Service | Configuration | Est. Monthly Cost |
|---------|--------------|-------------------|
| Azure Kubernetes Service (AKS) | Scale-to-zero node pool | $50-100 |
| Cosmos DB | Serverless mode | $10-30 |
| Redis Cache | Basic C0 (250MB) | $16 |
| Service Bus | Basic tier | $10 |
| Blob Storage | Cool tier | $5 |
| Azure Monitor | Free tier (5GB/month) | $0 |
| Log Analytics | Free tier (5GB/month) | $0 |
| Azure OpenAI | Pay-per-token | $10-50 |
| **Total** | With auto-shutdown | **~$100-280/month** |

### Cost Optimization Features
- ✅ Auto-shutdown scripts (7 PM daily)
- ✅ Resource tagging for easy cleanup
- ✅ One-command teardown script
- ✅ Serverless-first architecture
- ✅ Scale-to-zero AKS node pools

---

## 🗓️ Course Schedule: 8 Weeks, 5 Days/Week, 1 Hour/Day

### Weeks 1-2: Infrastructure + Application + Traditional Monitoring (10 sessions)

| Session | Day | Topic | Hands-On Deliverable |
|---------|-----|-------|---------------------|
| 1 | Mon | Course Overview & Azure Setup | Resource group with tags, Azure CLI configured |
| 2 | Tue | AKS Deployment with Scale-to-Zero | Running AKS cluster with autoscaler |
| 3 | Wed | Data Services Setup | Cosmos DB, Redis, Service Bus deployed |
| 4 | Thu | Microservices Part 1 | Catalog, Inventory, User services running |
| 5 | Fri | Microservices Part 2 | Cart, Payment, Order, Notification services |
| 6 | Mon | Vue.js Frontend & API Gateway | Complete e-commerce UI functional |
| 7 | Tue | Application Insights Deep Dive | Full telemetry instrumentation |
| 8 | Wed | Log Analytics & KQL Mastery | KQL query library, saved queries |
| 9 | Thu | Alerting & Dashboards | Metric alerts, Azure Workbooks |
| 10 | Fri | Distributed Tracing | End-to-end request correlation |

### Weeks 3-4: Failure Scenarios + Traditional AIOps with ML (10 sessions)

| Session | Day | Topic | Hands-On Deliverable |
|---------|-----|-------|---------------------|
| 11 | Mon | Chaos Engineering Framework | Failure injection toolkit |
| 12 | Tue | Simulating Real-World Failures | Memory leaks, timeouts, crashes |
| 13 | Wed | ML Fundamentals for IT Ops | Anomaly detection concepts |
| 14 | Thu | Isolation Forest Implementation | Multivariate anomaly detector |
| 15 | Fri | Prophet for Capacity Planning | Time-series forecasting model |
| 16 | Mon | Azure Monitor → ML Pipeline | Data extraction and preprocessing |
| 17 | Tue | Correlation & Root Cause Analysis | ML-based event correlation |
| 18 | Wed | Building the ML API Service | FastAPI ML prediction endpoints |
| 19 | Thu | Predictive Alerting System | Proactive alert generation |
| 20 | Fri | ML vs Traditional Monitoring Demo | Side-by-side failure comparison |

### Weeks 5-6-7: MCP Server + RAG System (15 sessions)

| Session | Day | Topic | Hands-On Deliverable |
|---------|-----|-------|---------------------|
| 21 | Mon | MCP Protocol Deep Dive | Understanding Model Context Protocol |
| 22 | Tue | MCP Server Scaffolding | FastAPI + MCP server base |
| 23 | Wed | Azure Monitor Tools (5 tools) | Metrics, logs, alerts, health, traces |
| 24 | Thu | ServiceNow Simulator Part 1 | Incident CRUD operations |
| 25 | Fri | ServiceNow Simulator Part 2 | SLA tracking, escalation workflows |
| 26 | Mon | Splunk Simulator Part 1 | Log ingestion, basic search |
| 27 | Tue | Splunk Simulator Part 2 | SPL aggregation queries |
| 28 | Wed | RAG Architecture Design | Embedding strategies, chunking |
| 29 | Thu | Knowledge Base Setup | Load 500+ ticket dataset |
| 30 | Fri | ChromaDB Implementation | Vector store, similarity search |
| 31 | Mon | Azure AI Search Migration | Production-grade RAG |
| 32 | Tue | Resolution Recommendation Engine | Similar ticket matching |
| 33 | Wed | Runbook Retrieval System | Context-aware runbook selection |
| 34 | Thu | Azure OpenAI Integration | Tool calling, chat completions |
| 35 | Fri | Agent Workflow Orchestration | Multi-tool incident workflows |

### Week 8: Chaos Engineering + Capstone (5 sessions)

| Session | Day | Topic | Hands-On Deliverable |
|---------|-----|-------|---------------------|
| 36 | Mon | Advanced Chaos Scenarios | Cascading failure scripts |
| 37 | Tue | Capstone Setup | Configure "Black Friday Meltdown" |
| 38 | Wed | Capstone Demo Part 1 | Traditional monitoring experience |
| 39 | Thu | Capstone Demo Part 2 | ML AIOps vs AgentOps comparison |
| 40 | Fri | Course Wrap-up & Teardown | Final review, resource cleanup |

---

## 🤖 MCP Server: 15 AI Tools for IT Operations

### Azure Monitor Tools (5)
| Tool | Description |
|------|-------------|
| `azure_monitor_query_metrics` | Query Azure Monitor metrics for any resource |
| `azure_log_analytics_query` | Execute KQL queries against Log Analytics |
| `azure_alerts_list` | List active alerts by severity and time range |
| `azure_resource_health_check` | Check health status of Azure resources |
| `azure_container_apps_logs` | Retrieve container logs and events |

### ServiceNow Simulator Tools (4)
| Tool | Description |
|------|-------------|
| `servicenow_create_incident` | Create incident with SLA tracking |
| `servicenow_update_incident` | Update incident, add work notes |
| `servicenow_search_incidents` | Search historical incidents |
| `servicenow_get_kb_articles` | Search knowledge base articles |

### Splunk Simulator Tools (3)
| Tool | Description |
|------|-------------|
| `splunk_search_logs` | Execute SPL queries with aggregations |
| `splunk_get_error_patterns` | Analyze error patterns over time |
| `splunk_trace_transaction` | Distributed transaction tracing |

### RAG Knowledge Tools (3)
| Tool | Description |
|------|-------------|
| `rag_search_resolutions` | Find similar past incident resolutions |
| `rag_get_runbook` | Retrieve relevant runbook procedures |
| `ai_analyze_incident` | AI-powered incident analysis |

---

## 🎭 Capstone: "The Black Friday Meltdown"

A collaborative live demo demonstrating the value progression through a cascading failure scenario:

### Failure Chain
```
T+0 min:  Traffic spike 10x → Product service CPU 95%
T+2 min:  Connection pool exhaustion → Cache miss rate spikes  
T+5 min:  Order service timeouts → Dead letter queue fills
T+8 min:  Cosmos DB throttling (429) → Retry storms
T+10 min: Full system degradation → Customer-facing outage
```

### Value Progression

| Approach | Detection | Root Cause ID | Resolution | Experience |
|----------|-----------|---------------|------------|------------|
| **Traditional** | T+5 min | T+25 min | T+45 min | 15+ alerts, manual investigation |
| **ML AIOps** | T+2 min | T+10 min | T+25 min | Early warning, correlated issues |
| **AgentOps** | T+1 min | T+3 min | T+8 min | Predictive, RAG-powered, auto-remediation |

---

## 📋 Prerequisites

### For Participants
- **Python**: Intermediate level (FastAPI, async/await, pandas)
- **Azure**: Basic knowledge (resource groups, portal navigation, CLI)
- **Git**: Basic version control operations

### Required Tools
- VS Code with Python extension
- Azure CLI installed and configured
- Python 3.10+
- Node.js 18+ (for frontend)
- Azure subscription with credits

---

## 🚀 Quick Start

```bash
# Clone the training repository
cd /path/to/aiops-training

# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Set up Python environment with uv
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
uv pip install -r requirements.txt

# Or use uv sync with pyproject.toml (recommended)
uv sync

# Configure Azure
az login
az account set --subscription "Your-Subscription-Name"

# Deploy infrastructure (Week 1)
cd ecommerce-app/infrastructure/bicep
az deployment group create \
  --resource-group aiops-training-rg \
  --template-file main.bicep \
  --parameters environment=training

# Start the training!
# Follow docs/week-01/01-course-overview.md
```

---

## 📁 Repository Structure

```
aiops-training/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── docs/                              # 40 session guides
│   ├── week-01/                       # Sessions 1-5
│   ├── week-02/                       # Sessions 6-10
│   ├── week-03/                       # Sessions 11-15
│   ├── week-04/                       # Sessions 16-20
│   ├── week-05/                       # Sessions 21-25
│   ├── week-06/                       # Sessions 26-30
│   ├── week-07/                       # Sessions 31-35
│   └── week-08/                       # Sessions 36-40
├── ecommerce-app/
│   ├── infrastructure/bicep/          # Azure Bicep templates
│   ├── services/                       # 7 FastAPI microservices
│   │   ├── catalog-service/
│   │   ├── cart-service/
│   │   ├── payment-service/
│   │   ├── order-service/
│   │   ├── user-service/
│   │   ├── inventory-service/
│   │   └── notification-service/
│   └── frontend/                       # Vue.js application
├── ml-service/                         # ML anomaly detection & forecasting
├── mcp-server/
│   ├── tools/                          # 15 MCP tools
│   ├── connectors/                     # Azure API connectors
│   ├── simulators/                     # ServiceNow & Splunk
│   └── agents/                         # AI incident agents
├── rag-system/
│   ├── data/
│   │   ├── tickets/                    # 500+ historical tickets
│   │   ├── runbooks/                   # Remediation procedures
│   │   └── knowledge_base/             # KB articles
│   └── app/                            # RAG pipeline code
├── chaos-engineering/
│   └── scenarios/                      # Failure injection scripts
├── exercises/                          # Hands-on labs with solutions
└── scripts/
    ├── setup/                          # Environment setup
    ├── shutdown-training.py            # Auto-shutdown script
    └── teardown-training-lab.sh        # Resource cleanup
```

---

## 📞 Support

For questions or issues during the training:
1. Check the session guide in `docs/week-XX/`
2. Review the exercise solutions in `exercises/`
3. Consult the troubleshooting section in each guide

---

## 📜 License

This training material is proprietary and intended for authorized training sessions only.

---

**Happy Learning! 🚀**

*Transform your IT operations with the power of AI.*
