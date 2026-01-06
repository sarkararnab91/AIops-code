// AKS Module - Azure Kubernetes Service with KEDA for scale-to-zero
// Cost optimized for training environment

@description('AKS cluster name')
param name string

@description('Location for AKS cluster')
param location string

@description('Resource tags')
param tags object

@description('Admin username for AKS nodes')
param adminUsername string

@description('SSH public key for AKS nodes')
@secure()
param sshPublicKey string

@description('Azure AD tenant ID')
param aadTenantId string

@description('Log Analytics workspace ID for monitoring')
param logAnalyticsWorkspaceId string

@description('Container Registry ID for pull permissions')
param containerRegistryId string

// ============================================================
// AKS CLUSTER
// ============================================================

resource aksCluster 'Microsoft.ContainerService/managedClusters@2024-01-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    dnsPrefix: name
    kubernetesVersion: '1.32.9'
    
    // Agent pool configuration - minimal for training
    agentPoolProfiles: [
      {
        name: 'system'
        count: 1
        minCount: 1
        maxCount: 3
        vmSize: 'Standard_B2s'  // Burstable, cost-effective
        osType: 'Linux'
        osDiskSizeGB: 30
        osDiskType: 'Managed'
        type: 'VirtualMachineScaleSets'
        mode: 'System'
        enableAutoScaling: true
        availabilityZones: []  // No AZ for cost savings
        nodeTaints: [
          'CriticalAddonsOnly=true:NoSchedule'
        ]
        tags: tags
      }
      {
        name: 'workload'
        count: 0  // Start with 0 for scale-to-zero
        minCount: 0
        maxCount: 5
        vmSize: 'Standard_B2ms'  // 2 vCPU, 8GB RAM
        osType: 'Linux'
        osDiskSizeGB: 50
        osDiskType: 'Managed'
        type: 'VirtualMachineScaleSets'
        mode: 'User'
        enableAutoScaling: true
        availabilityZones: []
        scaleDownMode: 'Deallocate'  // Key for scale-to-zero
        tags: tags
      }
    ]
    
    // Linux profile
    linuxProfile: {
      adminUsername: adminUsername
      ssh: {
        publicKeys: [
          {
            keyData: sshPublicKey
          }
        ]
      }
    }
    
    // Network configuration
    networkProfile: {
      networkPlugin: 'azure'
      networkPolicy: 'azure'
      loadBalancerSku: 'standard'
      serviceCidr: '10.0.0.0/16'
      dnsServiceIP: '10.0.0.10'
    }
    
    // Azure AD integration
    aadProfile: {
      managed: true
      enableAzureRBAC: true
      tenantID: aadTenantId
    }
    
    // Add-ons
    addonProfiles: {
      // Azure Monitor for containers
      omsagent: {
        enabled: true
        config: {
          logAnalyticsWorkspaceResourceID: logAnalyticsWorkspaceId
        }
      }
      // HTTP Application Routing (for ingress)
      httpApplicationRouting: {
        enabled: false  // Use nginx ingress instead
      }
      // Azure Policy
      azurepolicy: {
        enabled: false  // Disable for training to reduce complexity
      }
    }

    // KEDA - Kubernetes Event-Driven Autoscaling
    workloadAutoScalerProfile: {
      keda: {
        enabled: true
      }
    }
    
    // Auto-upgrade channel
    autoUpgradeProfile: {
      upgradeChannel: 'stable'
    }
  }
  
  // SKU for free tier (at resource level, not in properties)
  sku: {
    name: 'Base'
    tier: 'Free'
  }
}

// Role assignment for ACR pull
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aksCluster.id, containerRegistryId, 'acrpull')
  scope: resourceGroup()
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')  // AcrPull
    principalId: aksCluster.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output clusterName string = aksCluster.name
output clusterFqdn string = aksCluster.properties.fqdn
output clusterResourceId string = aksCluster.id
output kubeletIdentityObjectId string = aksCluster.properties.identityProfile.kubeletidentity.objectId
// output oidcIssuerUrl string = aksCluster.properties.oidcIssuerProfile.issuerURL
