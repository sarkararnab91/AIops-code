# AIOps Training - Quick Start Guide

Get up and running with the AIOps training environment in 30 minutes.

## Prerequisites

- **Azure Subscription** (free tier works for most components)
- **Python 3.11+** with `uv` package manager
- **Docker Desktop** (for local development)
- **Azure CLI** installed and authenticated
- **kubectl** for Kubernetes interaction
- **VS Code** with Python extension

## Step 1: Clone and Setup (5 minutes)

```bash
# Navigate to training directory
cd training-plan

# Create Python virtual environment
uv venv
source .venv/bin/activate  # Unix/macOS

# Install base dependencies
uv pip install -r requirements.txt
```

## Step 2: Azure Infrastructure (10 minutes)

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription "your-subscription-id"

# Create resource group
az group create --name rg-aiops-demo --location eastus

# Deploy infrastructure
cd infrastructure
az deployment group create \
  --resource-group rg-aiops-demo \
  --template-file main.bicep \
  --parameters environment=dev

# Get AKS credentials
az aks get-credentials --resource-group rg-aiops-demo --name aks-aiops-demo-dev
```

## Step 3: Build and Deploy Services (10 minutes)

```bash
# Get ACR login server
ACR_NAME=$(az acr list -g rg-aiops-demo --query "[0].name" -o tsv)
az acr login --name $ACR_NAME

# Build and push all services
cd ../ecommerce-app

for service in catalog-service order-service cart-service user-service payment-service inventory-service notification-service; do
  docker build -t $ACR_NAME.azurecr.io/$service:v1 ./services/$service
  docker push $ACR_NAME.azurecr.io/$service:v1
done

# Deploy to AKS
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmaps/
kubectl apply -f k8s/deployments/
kubectl apply -f k8s/services/
```

## Step 4: Setup MCP Server (5 minutes)

```bash
cd mcp-server

# Create virtual environment
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt

# Create .env file
cat > .env << EOF
AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
AZURE_RESOURCE_GROUP=rg-aiops-demo
LOG_LEVEL=INFO
EOF

# Test the server
uv run python -m src.server
```

## Step 5: Configure Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aiops": {
      "command": "uv",
      "args": ["run", "python", "-m", "src.server"],
      "cwd": "/path/to/training-plan/ecommerce-app/mcp-server"
    }
  }
}
```

Restart Claude Desktop.

## Verify Setup

### Check Services

```bash
kubectl get pods -n ecommerce
# All pods should be Running

kubectl get svc -n ecommerce
# Services should have ClusterIP assigned
```

### Test MCP in Claude

Ask Claude:
> "What is the health status of all services?"

Claude should use the MCP tools to query Azure Monitor.

### Test ML Service

```bash
cd ml-service
uv run python -m src.main &

# Test prediction endpoint
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "order-service",
    "cpu_percent": 85,
    "memory_percent": 70,
    "request_rate": 100,
    "error_rate": 0.08,
    "latency_p50": 100,
    "latency_p95": 500,
    "latency_p99": 1500
  }'
```

## Next Steps

1. **Start Training**: Begin with [Week 1, Session 1](docs/week-01/01-introduction.md)
2. **Explore Demos**: Run the demo scripts in each service directory
3. **Inject Chaos**: Use chaos scripts to test detection capabilities
4. **Build RAG**: Populate the knowledge base with incident data

## Troubleshooting

### Pods Not Starting

```bash
kubectl describe pod <pod-name> -n ecommerce
kubectl logs <pod-name> -n ecommerce
```

### Azure Authentication Issues

```bash
az login --use-device-code
az account show
```

### MCP Server Not Connecting

1. Check Claude Desktop config path
2. Verify Python path is correct
3. Check `.env` file exists
4. Restart Claude Desktop

## Cost Management

To minimize costs when not training:

```bash
# Stop AKS cluster
az aks stop --resource-group rg-aiops-demo --name aks-aiops-demo-dev

# Resume when needed
az aks start --resource-group rg-aiops-demo --name aks-aiops-demo-dev
```

## Support

- Review session documentation in `docs/`
- Check README files in each component directory
- Use Claude with MCP for troubleshooting assistance
