// Application Insights Module - APM for microservices
// Integrated with Log Analytics workspace

@description('Application Insights resource name')
param name string

@description('Location for Application Insights')
param location string

@description('Resource tags')
param tags object

@description('Log Analytics workspace ID')
param logAnalyticsWorkspaceId string

// ============================================================
// APPLICATION INSIGHTS
// ============================================================

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: name
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    
    // Link to Log Analytics workspace
    WorkspaceResourceId: logAnalyticsWorkspaceId
    
    // Ingestion mode
    IngestionMode: 'LogAnalytics'
    
    // Sampling (reduce data for cost savings)
    SamplingPercentage: 100  // 100% for training, reduce in production
    
    // Retention (inherited from Log Analytics)
    RetentionInDays: 30
    
    // Disable IP masking for debugging (enable in production)
    DisableIpMasking: true
    
    // Disable local authentication (use Azure AD in production)
    DisableLocalAuth: false
    
    // Public network access
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ============================================================
// SMART DETECTION RULES
// ============================================================

// Slow page load time detection
resource slowPageLoadRule 'Microsoft.Insights/components/ProactiveDetectionConfigs@2018-05-01-preview' = {
  parent: appInsights
  name: 'slowpageloadtime'
  properties: {
    RuleDefinitions: {
      Name: 'slowpageloadtime'
      DisplayName: 'Slow page load time'
      Description: 'Smart Detection rules notify you of performance anomaly issues.'
      HelpUrl: 'https://docs.microsoft.com/en-us/azure/application-insights/app-insights-proactive-performance-diagnostics'
      IsHidden: false
      IsEnabledByDefault: true
      IsInPreview: false
      SupportsEmailNotifications: true
    }
    Enabled: true
    SendEmailsToSubscriptionOwners: true
    CustomEmails: []
  }
}

// Slow server response time detection
resource slowServerResponseRule 'Microsoft.Insights/components/ProactiveDetectionConfigs@2018-05-01-preview' = {
  parent: appInsights
  name: 'slowserverresponsetime'
  properties: {
    RuleDefinitions: {
      Name: 'slowserverresponsetime'
      DisplayName: 'Slow server response time'
      Description: 'Smart Detection rules notify you of performance anomaly issues.'
      HelpUrl: 'https://docs.microsoft.com/en-us/azure/application-insights/app-insights-proactive-performance-diagnostics'
      IsHidden: false
      IsEnabledByDefault: true
      IsInPreview: false
      SupportsEmailNotifications: true
    }
    Enabled: true
    SendEmailsToSubscriptionOwners: true
    CustomEmails: []
  }
}

// Degradation in dependency duration
resource degradationInDependencyDurationRule 'Microsoft.Insights/components/ProactiveDetectionConfigs@2018-05-01-preview' = {
  parent: appInsights
  name: 'degradationindependencyduration'
  properties: {
    RuleDefinitions: {
      Name: 'degradationindependencyduration'
      DisplayName: 'Degradation in dependency duration'
      Description: 'Smart Detection rules notify you of performance anomaly issues.'
      HelpUrl: 'https://docs.microsoft.com/en-us/azure/application-insights/app-insights-proactive-performance-diagnostics'
      IsHidden: false
      IsEnabledByDefault: true
      IsInPreview: false
      SupportsEmailNotifications: true
    }
    Enabled: true
    SendEmailsToSubscriptionOwners: true
    CustomEmails: []
  }
}

// ============================================================
// OUTPUTS
// ============================================================

output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output instrumentationKey string = appInsights.properties.InstrumentationKey
output connectionString string = appInsights.properties.ConnectionString
