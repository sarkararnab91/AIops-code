# Session 2: AKS Deployment with Scale-to-Zero

## Session Details
- **Duration**: 1 hour
- **Week**: 1, Day 2 
- **Prerequisites**: Session 1 completed, Resource group created
- **Deliverable**: Running AKS cluster with scale-to-zero autoscaler

---

##  Learning Objectives

By the end of this session, you will:
1. Understand Azure Kubernetes Service (AKS) architecture
2. Deploy a cost-optimized AKS cluster
3. Configure cluster autoscaler with scale-to-zero
4. Access the cluster and verify connectivity

---

##  Concepts

### Why Kubernetes for Microservices?

Kubernetes provides:
- **Container orchestration**: Manage multiple containers as a single application
- **Self-healing**: Automatic restart of failed containers
- **Scaling**: Horizontal pod autoscaling based on metrics
- **Service discovery**: Built-in DNS and load balancing
- **Rolling updates**: Zero-downtime deployments

### AKS Architecture for Training

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AKS CLUSTER                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        CONTROL PLANE (Managed by Azure)                 │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │ │
│  │  │  API Server  │  │  Scheduler   │  │   etcd       │                 │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        NODE POOL (User-managed)                         │ │
│  │                                                                          │ │
│  │  ┌─────────────────────┐  ┌─────────────────────┐                      │ │
│  │  │     Node 1          │  │     Node 2          │   ← Scale-to-Zero   │ │
│  │  │  ┌─────┐ ┌─────┐   │  │  ┌─────┐ ┌─────┐   │     enabled!         │ │
│  │  │  │ Pod │ │ Pod │   │  │  │ Pod │ │ Pod │   │                      │ │
│  │  │  └─────┘ └─────┘   │  │  └─────┘ └─────┘   │                      │ │
│  │  └─────────────────────┘  └─────────────────────┘                      │ │
│  │                                                                          │ │
│  │  Cluster Autoscaler: min=0, max=3, scale-down-delay=10m                │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Scale-to-Zero: Key Cost Saver

The cluster autoscaler can scale node pools to zero when no workloads need them:

| Time | Nodes | Cost/Hour | Notes |
|------|-------|-----------|-------|
| 9 AM - 6 PM | 2 | ~$0.20 | Training hours |
| 6 PM - 9 AM | 0 | $0.00 | Auto-scaled to zero |
| Weekends | 0 | $0.00 | No workloads scheduled |

**Monthly savings**: ~60% compared to always-on cluster

---

##  Hands-On Exercise

### Step 1: Register Required Providers

**Bash:**
```bash
# Register required Azure providers
az provider register --namespace Microsoft.ContainerService
az provider register --namespace Microsoft.OperationsManagement
az provider register --namespace Microsoft.OperationalInsights

# Check registration status
az provider show -n Microsoft.ContainerService --query "registrationState"
```

**PowerShell:**
```powershell
# Register required Azure providers
az provider register --namespace Microsoft.ContainerService
az provider register --namespace Microsoft.OperationsManagement
az provider register --namespace Microsoft.OperationalInsights

# Check registration status
az provider show -n Microsoft.ContainerService --query "registrationState"
```

### Step 2: Create AKS Cluster with Bicep

Create the Bicep template file:

**Bash:**
```bash
# Create infrastructure directory
mkdir -p ecommerce-app/infrastructure/bicep
```

**PowerShell:**
```powershell
# Create infrastructure directory
New-Item -ItemType Directory -Force -Path ecommerce-app/infrastructure/bicep
```

Create `ecommerce-app/infrastructure/bicep/aks.bicep`:

```bicep
// AKS Cluster with Scale-to-Zero Configuration
// Optimized for training with minimal costs

@description('The name of the AKS cluster')
param clusterName string = 'aiops-aks'

@description('The location for the AKS cluster')
param location string = resourceGroup().location

@description('The DNS prefix for the AKS cluster')
param dnsPrefix string = 'aiops'

@description('The VM size for the default node pool')
param nodeVMSize string = 'Standard_B2s'  // Cost-optimized: 2 vCPU, 4GB RAM

@description('Minimum node count (0 for scale-to-zero)')
@minValue(0)
@maxValue(10)
param minNodeCount int = 0

@description('Maximum node count')
@minValue(1)
@maxValue(10)
param maxNodeCount int = 3

@description('Enable auto-shutdown tag')
param autoShutdown bool = true

@description('Environment tag')
param environment string = 'training'

// Common tags for cost tracking
var commonTags = {
  Project: 'aiops-training'
  Environment: environment
  AutoShutdown: string(autoShutdown)
  CostCenter: 'aiops-lab'
  ManagedBy: 'bicep'
}

// Log Analytics Workspace for monitoring
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${clusterName}-logs'
  location: location
  tags: commonTags
  properties: {
    sku: {
      name: 'PerGB2018'  // Pay-per-GB, free tier: 5GB/month
    }
    retentionInDays: 30
  }
}

// AKS Cluster
resource aksCluster 'Microsoft.ContainerService/managedClusters@2024-01-01' = {
  name: clusterName
  location: location
  tags: commonTags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dnsPrefix: dnsPrefix
    kubernetesVersion: '1.28'
    
    // Node Pools configuration
    agentPoolProfiles: [
      // System Pool (Critical services, min 1)
      {
        name: 'system'
        count: 1
        vmSize: nodeVMSize
        osType: 'Linux'
        mode: 'System'
        enableAutoScaling: true
        minCount: 1      // System pool cannot be 0
        maxCount: 2
        type: 'VirtualMachineScaleSets'
        availabilityZones: []
      }
      // Workload Pool (User apps, scale-to-zero)
      {
        name: 'workload'
        count: 0
        vmSize: nodeVMSize
        osType: 'Linux'
        mode: 'User'     // User pool can scale to 0
        enableAutoScaling: true
        minCount: 0      // Scale to zero enabled!
        maxCount: maxNodeCount
        scaleDownMode: 'Delete'
        type: 'VirtualMachineScaleSets'
        availabilityZones: []
      }
    ]
    
    // Network configuration
    networkProfile: {
      networkPlugin: 'azure'
      loadBalancerSku: 'standard'
      outboundType: 'loadBalancer'
    }
    
    // Enable monitoring addon
    addonProfiles: {
      omsagent: {
        enabled: true
        config: {
          logAnalyticsWorkspaceResourceID: logAnalytics.id
        }
      }
    }
    
    // Auto-upgrade for security patches
    autoUpgradeProfile: {
      upgradeChannel: 'patch'
    }
  }
}

// Output values
output clusterName string = aksCluster.name
output clusterFqdn string = aksCluster.properties.fqdn
output logAnalyticsWorkspaceId string = logAnalytics.id
```

### Step 3: Deploy AKS Cluster

**Bash:**
```bash
# Set variables
RESOURCE_GROUP="aiops-training-rg"

# Deploy the AKS cluster
az deployment group create \
  --resource-group $RESOURCE_GROUP \
  --template-file ecommerce-app/infrastructure/bicep/modules/aks.bicep \
  --parameters @ecommerce-app/infrastructure/bicep/parameters/aks.parameters.json

# This takes about 5-10 minutes
```

**PowerShell:**
```powershell
# Set variables
$RESOURCE_GROUP = "aiops-training-rg"

# Deploy the AKS cluster
az deployment group create `
  --resource-group $RESOURCE_GROUP `
  --template-file ecommerce-app/infrastructure/bicep/modules/aks.bicep `
  --parameters @ecommerce-app/infrastructure/bicep/parameters/aks.parameters.json

# This takes about 5-10 minutes
```

### Step 4: Connect to AKS Cluster

**Bash:**
```bash
# Set variable
RESOURCE_GROUP="aiops-training-rg"

# Get cluster credentials
az aks get-credentials \
  --resource-group $RESOURCE_GROUP \
  --name aiops-aks \
  --overwrite-existing

# Verify connection
kubectl get nodes

# Check cluster info
kubectl cluster-info

# View namespaces
kubectl get namespaces
```

**PowerShell:**
```powershell
#install kubelogin tool 
az aks install-cli

# Set variable
$RESOURCE_GROUP = "aiops-training-rg"

# Get cluster credentials
az aks get-credentials `
  --resource-group $RESOURCE_GROUP `
  --name aiops-aks `
  --overwrite-existing

# Verify connection
kubectl get nodes

# Check cluster info
kubectl cluster-info

# View namespaces
kubectl get namespaces
```

### Step 5: Verify Autoscaler Configuration

**Bash:**
```bash
# Set variable
RESOURCE_GROUP="aiops-training-rg"

# Check node pool configuration
az aks nodepool show \
  --resource-group $RESOURCE_GROUP \
  --cluster-name aiops-aks \
  --name system \
  --query "{name:name, minCount:minCount, maxCount:maxCount, enableAutoScaling:enableAutoScaling}" \
  --output table

# View cluster autoscaler logs (once pods are running)
kubectl -n kube-system logs -l component=cluster-autoscaler --tail=50
```

**PowerShell:**
```powershell
# Set variable
$RESOURCE_GROUP = "aiops-training-rg"

# Check node pool configuration
az aks nodepool show `
  --resource-group $RESOURCE_GROUP `
  --cluster-name aiops-aks `
  --name system `
  --query "{name:name, minCount:minCount, maxCount:maxCount, enableAutoScaling:enableAutoScaling}" `
  --output table

# View cluster autoscaler logs (once pods are running)
kubectl -n kube-system logs -l component=cluster-autoscaler --tail=50
```

### Step 6: Test Scale-to-Zero (Optional)

**Bash:**
```bash
# Scale down workloads to trigger scale-to-zero
# (In a real scenario, this happens automatically when no pods are scheduled)

# Force scale down by cordoning and draining the node
kubectl get nodes
# kubectl cordon <node-name>
# kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

# Wait 10 minutes for autoscaler to remove the node
# The cluster will scale back up when workloads are deployed
```

**PowerShell:**
```powershell
# Scale down workloads to trigger scale-to-zero
# (In a real scenario, this happens automatically when no pods are scheduled)

# Force scale down by cordoning and draining the node
kubectl get nodes
# kubectl cordon <node-name>
# kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

# Wait 10 minutes for autoscaler to remove the node
# The cluster will scale back up when workloads are deployed
```
System Pool: stays at 1 node (Cost: ~$0.10/hr)
User Pool: scales 0-3 nodes (Cost: $0.00/hr when idle)
Running the command to create the user pool:

az aks nodepool add --resource-group aiops-training-rg --cluster-name aiops-aks --name userpool --mode User --min-count 0 --max-count 3 --enable-cluster-autoscaler --node-vm-size Standard_B2s

az aks nodepool list --resource-group aiops-training-rg --cluster-name aiops-aks --output table
---

##  Verification Checklist

Before moving to the next session, ensure you have:

- [ ] AKS cluster `aiops-aks` deployed successfully
- [ ] Log Analytics workspace created for monitoring
- [ ] kubectl connected to the cluster
- [ ] Autoscaling enabled 
- [ ] Tags applied correctly to all resources

---

##  Cost Optimization Tips

1. **Scale-to-Zero**: The cluster will automatically scale down when idle
2. **B-series VMs**: Use burstable VMs for training workloads
3. **Single Availability Zone**: We skip zones to reduce costs
4. **30-day log retention**: Minimum retention for cost savings
5. **Manual scale-down**: You can manually scale to 0 nodes after sessions

**Bash:**
```bash
# Manually scale node pool to 0 (optional - for maximum savings)
az aks nodepool scale \
  --resource-group $RESOURCE_GROUP \
  --cluster-name aiops-aks \
  --name system \
  --node-count 0

# Scale back up before next session
az aks nodepool scale \
  --resource-group $RESOURCE_GROUP \
  --cluster-name aiops-aks \
  --name system \
  --node-count 1
```

**PowerShell:**
```powershell
# Manually scale node pool to 0 (optional - for maximum savings)
az aks nodepool scale `
  --resource-group $RESOURCE_GROUP `
  --cluster-name aiops-aks `
  --name system `
  --node-count 0

# Scale back up before next session
az aks nodepool scale `
  --resource-group $RESOURCE_GROUP `
  --cluster-name aiops-aks `
  --name system `
  --node-count 1
```

---

## 📖 Key Takeaways

1. **AKS provides managed Kubernetes** - Azure handles the control plane
2. **Scale-to-zero saves significant costs** - Only pay when workloads run
3. **Cluster autoscaler manages node count** - Automatic based on demand
4. **B-series VMs are cost-effective** - Ideal for variable workloads

---

## 🔜 Next Session Preview

**Session 3: Data Services Setup**
- Deploy Cosmos DB with serverless mode
- Set up Redis Cache (Basic C0)
- Configure Service Bus for messaging

---

## 📚 Additional Resources

- [AKS Documentation](https://docs.microsoft.com/en-us/azure/aks/)
- [Cluster Autoscaler](https://docs.microsoft.com/en-us/azure/aks/cluster-autoscaler)
- [AKS Cost Optimization](https://docs.microsoft.com/en-us/azure/aks/best-practices-cost)
- [Kubernetes Basics](https://kubernetes.io/docs/tutorials/kubernetes-basics/)
