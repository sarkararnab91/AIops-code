#!/bin/bash
# Deploy E-Commerce AIOps Training Infrastructure
# Usage: ./deploy.sh <resource-group> <location>

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default values
RESOURCE_GROUP=${1:-"aiops-training-rg"}
LOCATION=${2:-"eastus"}
ENVIRONMENT="training"

echo -e "${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  AIOps Training Infrastructure Deployment  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI is not installed${NC}"
    echo "Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli"
    exit 1
fi

# Check if logged in
if ! az account show &> /dev/null; then
    echo -e "${YELLOW}Not logged in to Azure. Starting login...${NC}"
    az login
fi

# Display current subscription
SUBSCRIPTION=$(az account show --query name -o tsv)
echo -e "${YELLOW}Current subscription: ${SUBSCRIPTION}${NC}"
read -p "Continue with this subscription? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Run 'az account set --subscription <subscription-id>' to change subscription"
    exit 1
fi

# Create resource group if it doesn't exist
echo -e "\n${GREEN}Step 1: Creating resource group...${NC}"
az group create \
    --name $RESOURCE_GROUP \
    --location $LOCATION \
    --tags Project=aiops-training Environment=$ENVIRONMENT ManagedBy=bicep

# Generate SSH key if needed
SSH_KEY_PATH="$HOME/.ssh/aiops-training-aks"
if [ ! -f "$SSH_KEY_PATH" ]; then
    echo -e "\n${GREEN}Step 2: Generating SSH key for AKS...${NC}"
    ssh-keygen -t rsa -b 4096 -f $SSH_KEY_PATH -N "" -C "aiops-training-aks"
fi
SSH_PUBLIC_KEY=$(cat "${SSH_KEY_PATH}.pub")

# Deploy infrastructure
echo -e "\n${GREEN}Step 3: Deploying infrastructure (this may take 15-20 minutes)...${NC}"
DEPLOYMENT_OUTPUT=$(az deployment group create \
    --resource-group $RESOURCE_GROUP \
    --template-file main.bicep \
    --parameters \
        environment=$ENVIRONMENT \
        sshPublicKey="$SSH_PUBLIC_KEY" \
    --query properties.outputs \
    -o json)

# Extract outputs
AKS_CLUSTER_NAME=$(echo $DEPLOYMENT_OUTPUT | jq -r '.aksClusterName.value')
ACR_LOGIN_SERVER=$(echo $DEPLOYMENT_OUTPUT | jq -r '.containerRegistryLoginServer.value')
COSMOS_ENDPOINT=$(echo $DEPLOYMENT_OUTPUT | jq -r '.cosmosDbEndpoint.value')
REDIS_HOST=$(echo $DEPLOYMENT_OUTPUT | jq -r '.redisHostName.value')
APPINSIGHTS_CONNECTION=$(echo $DEPLOYMENT_OUTPUT | jq -r '.appInsightsConnectionString.value')

# Configure kubectl
echo -e "\n${GREEN}Step 4: Configuring kubectl...${NC}"
az aks get-credentials \
    --resource-group $RESOURCE_GROUP \
    --name $AKS_CLUSTER_NAME \
    --overwrite-existing

# Install KEDA if not already installed
echo -e "\n${GREEN}Step 5: Verifying KEDA installation...${NC}"
if kubectl get deployment keda-operator -n kube-system &> /dev/null; then
    echo "KEDA is already installed"
else
    echo "Installing KEDA..."
    helm repo add kedacore https://kedacore.github.io/charts
    helm repo update
    helm install keda kedacore/keda --namespace kube-system
fi

# Install NGINX Ingress Controller
echo -e "\n${GREEN}Step 6: Installing NGINX Ingress Controller...${NC}"
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx \
    --create-namespace \
    --set controller.replicaCount=1 \
    --set controller.nodeSelector."kubernetes\.io/os"=linux \
    --set defaultBackend.nodeSelector."kubernetes\.io/os"=linux

# Create Kubernetes secrets for services
echo -e "\n${GREEN}Step 7: Creating Kubernetes secrets...${NC}"
kubectl create namespace ecommerce --dry-run=client -o yaml | kubectl apply -f -

# Wait for ingress to get external IP
echo -e "\n${YELLOW}Waiting for ingress controller to get external IP...${NC}"
kubectl wait --namespace ingress-nginx \
    --for=condition=ready pod \
    --selector=app.kubernetes.io/component=controller \
    --timeout=120s

INGRESS_IP=$(kubectl get svc ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Print summary
echo -e "\n${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║       Deployment Complete!                 ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}"

echo -e "\n${YELLOW}Resource Details:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "Resource Group:    ${GREEN}$RESOURCE_GROUP${NC}"
echo -e "AKS Cluster:       ${GREEN}$AKS_CLUSTER_NAME${NC}"
echo -e "ACR Login Server:  ${GREEN}$ACR_LOGIN_SERVER${NC}"
echo -e "Ingress IP:        ${GREEN}$INGRESS_IP${NC}"
echo -e "Cosmos DB:         ${GREEN}$COSMOS_ENDPOINT${NC}"
echo -e "Redis Host:        ${GREEN}$REDIS_HOST${NC}"

echo -e "\n${YELLOW}Next Steps:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "1. Build and push Docker images to ACR:"
echo "   az acr login --name ${ACR_LOGIN_SERVER%%.*}"
echo ""
echo "2. Deploy microservices to AKS:"
echo "   kubectl apply -f ../kubernetes/"
echo ""
echo "3. Access the application:"
echo "   http://$INGRESS_IP"

echo -e "\n${YELLOW}Estimated Monthly Cost: \$100-280${NC}"
echo "Run 'az group delete -n $RESOURCE_GROUP' when done to stop charges"
