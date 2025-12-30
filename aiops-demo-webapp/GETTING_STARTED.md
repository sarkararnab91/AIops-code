# Getting Started with AIOps Training

This guide will help you set up the complete AIOps training environment.

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Python | 3.11+ | All services and scripts |
| uv | Latest | Python package management |
| Docker Desktop | Latest | Local development |
| Azure CLI | 2.50+ | Azure resource management |
| kubectl | 1.28+ | Kubernetes management |
| VS Code | Latest | Development environment |

### Azure Resources

You'll need an Azure subscription. A free account works for development.

### Optional

- Claude Desktop (for MCP integration)
- GitHub Copilot (enhanced coding assistance)

## Step-by-Step Setup

### 1. Install Prerequisites

**macOS:**
```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install required tools
brew install python@3.11 uv azure-cli kubectl

# Install Docker Desktop from https://docker.com

# Install VS Code from https://code.visualstudio.com
```

**Windows (PowerShell):**
```powershell
# Install Scoop if not installed
irm get.scoop.sh | iex

# Install required tools
scoop install python azure-cli kubectl uv

# Install Docker Desktop from https://docker.com
```

### 2. Clone and Setup Project

```bash
# Navigate to project directory
cd training-plan

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate  # Windows

# Install base dependencies
uv pip install -r requirements.txt
```

### 3. Azure Setup

```bash
# Login to Azure
az login

# List subscriptions
az account list --output table

# Set your subscription
az account set --subscription "Your-Subscription-Name-or-ID"

# Verify
az account show
```

### 4. Deploy Infrastructure

```bash
cd infrastructure

# Create resource group
az group create \
  --name rg-aiops-demo \
  --location eastus

# Deploy all resources
az deployment group create \
  --resource-group rg-aiops-demo \
  --template-file main.bicep \
  --parameters environment=dev

# Wait for deployment (5-10 minutes)
```

### 5. Configure Kubernetes

```bash
# Get AKS credentials
az aks get-credentials \
  --resource-group rg-aiops-demo \
  --name aks-aiops-demo-dev

# Verify connection
kubectl get nodes
```

### 6. Build and Deploy Services

```bash
cd ../ecommerce-app

# Get ACR login server
ACR_NAME=$(az acr list -g rg-aiops-demo --query "[0].name" -o tsv)

# Login to ACR
az acr login --name $ACR_NAME

# Build and push each service
for service in catalog order cart user payment inventory notification; do
  echo "Building $service-service..."
  docker build -t $ACR_NAME.azurecr.io/$service-service:v1 \
    ./services/$service-service
  docker push $ACR_NAME.azurecr.io/$service-service:v1
done

# Deploy to Kubernetes
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/deployments/
kubectl apply -f k8s/services/

# Check status
kubectl get pods -n ecommerce
```

### 7. Setup MCP Server

```bash
cd mcp-server

# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Create configuration
cat > .env << EOF
AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
AZURE_RESOURCE_GROUP=rg-aiops-demo
AZURE_LOG_ANALYTICS_WORKSPACE_ID=$(az monitor log-analytics workspace show \
  -g rg-aiops-demo -n law-aiops-demo-dev \
  --query customerId -o tsv 2>/dev/null || echo "")
LOG_LEVEL=INFO
EOF

# Test the server
uv run python -m src.server
```

### 8. Configure Claude Desktop (Optional)

Create/edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aiops": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.server"],
      "cwd": "/full/path/to/training-plan/ecommerce-app/mcp-server"
    }
  }
}
```

Restart Claude Desktop to apply changes.

## Verify Installation

### Check Azure Resources

```bash
az resource list -g rg-aiops-demo --output table
```

### Check Kubernetes

```bash
kubectl get all -n ecommerce
```

### Test MCP Tools

In Claude Desktop, ask:
> "What's the health status of all services?"

Claude should use the MCP tools to provide service health information.

### Test ML Service

```bash
cd ml-service
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# Start ML service
uv run uvicorn src.main:app --port 8000 &

# Test endpoint
curl -X GET http://localhost:8000/health
```

## Directory Structure

After setup, you should have:

```
training-plan/
├── .venv/                   # Python virtual environment
├── docs/                    # Session documentation
│   ├── week-01/            # Week 1 (Sessions 1-5)
│   ├── week-02/            # Week 2 (Sessions 6-10)
│   ├── week-03/            # Week 3 (Sessions 11-15)
│   ├── week-04/            # Week 4 (Sessions 16-20)
│   ├── week-05/            # Week 5 (Sessions 21-25)
│   └── week-06/            # Week 6 (Sessions 26-30)
├── ecommerce-app/          # Application code
│   ├── services/           # 7 microservices
│   ├── mcp-server/         # MCP server
│   ├── ml-service/         # ML anomaly detection
│   ├── chaos/              # Chaos engineering
│   └── k8s/                # Kubernetes manifests
├── infrastructure/         # Bicep templates
└── shared/                 # Shared Python modules
```

## Troubleshooting

### Azure Deployment Fails

```bash
# Check deployment status
az deployment group list -g rg-aiops-demo --output table

# View detailed errors
az deployment group show -g rg-aiops-demo -n main --query properties.error
```

### Pods Not Starting

```bash
# Describe pod for events
kubectl describe pod <pod-name> -n ecommerce

# Check logs
kubectl logs <pod-name> -n ecommerce

# Check if secrets exist
kubectl get secrets -n ecommerce
```

### ACR Authentication Issues

```bash
# Ensure AKS can pull from ACR
az aks update -n aks-aiops-demo-dev -g rg-aiops-demo \
  --attach-acr $(az acr show -n $ACR_NAME --query id -o tsv)
```

### MCP Server Not Connecting

1. Verify the path in Claude Desktop config is absolute and correct
2. Check that Python virtual environment has all dependencies
3. Ensure `.env` file exists with correct values
4. Restart Claude Desktop completely

## Cost Management

### Stop Resources When Not Using

```bash
# Stop AKS (no compute charges)
az aks stop -g rg-aiops-demo -n aks-aiops-demo-dev

# Resume later
az aks start -g rg-aiops-demo -n aks-aiops-demo-dev
```

### Check Current Costs

```bash
az consumption usage list -o table
```

### Delete Everything When Done

```bash
az group delete -g rg-aiops-demo --yes --no-wait
```

## Next Steps

1. **Start Training**: [Week 1, Session 1](docs/week-01/01-introduction.md)
2. **Quick Reference**: [QUICKSTART.md](QUICKSTART.md)
3. **Full Documentation**: [docs/](docs/)
