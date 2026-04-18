// Azure App Service infrastructure for DevUI deployment.
// Includes: Container Registry, App Service Plan, and Web App for Containers.

param location string
param tags object = {}
param prefix string

// DevUI auth token — stored as an App Setting
@secure()
param devuiAuthToken string

// Azure OpenAI config passed as app settings
param azureOpenAiEndpoint string
param azureOpenAiChatDeployment string
param azureOpenAiChatModel string
param azureOpenAiEmbeddingDeployment string
param azureOpenAiEmbeddingModel string
param azureTenantId string
param appInsightsConnectionString string
param azureAiProject string

// ── Container Registry ────────────────────────────────────────────────────

var acrName = replace('${prefix}acr', '-', '')

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: length(acrName) > 50 ? substring(acrName, 0, 50) : acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
    publicNetworkAccess: 'Enabled'
  }
}

// ── App Service Plan (Linux) ──────────────────────────────────────────────

resource appServicePlan 'Microsoft.Web/serverfarms@2022-09-01' = {
  name: '${prefix}-asp'
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true
  }
}

// ── Web App for Containers ────────────────────────────────────────────────

var acrLoginServer = acr.properties.loginServer
var acrCredentials = acr.listCredentials()

resource webApp 'Microsoft.Web/sites@2022-09-01' = {
  name: '${prefix}-devui'
  location: location
  tags: union(tags, { 'azd-service-name': 'devui' })
  kind: 'app,linux,container'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      // Placeholder image until azd deploy pushes the real one
      linuxFxVersion: 'DOCKER|mcr.microsoft.com/appsvc/staticsite:latest'
      alwaysOn: false
      appSettings: [
        { name: 'DOCKER_REGISTRY_SERVER_URL', value: 'https://${acrLoginServer}' }
        { name: 'DOCKER_REGISTRY_SERVER_USERNAME', value: acrCredentials.username }
        { name: 'DOCKER_REGISTRY_SERVER_PASSWORD', value: acrCredentials.passwords[0].value }
        { name: 'WEBSITES_PORT', value: '8080' }
        { name: 'API_HOST', value: 'azure' }
        { name: 'AZURE_TENANT_ID', value: azureTenantId }
        { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
        { name: 'AZURE_OPENAI_VERSION', value: '2024-10-21' }
        { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: azureOpenAiChatDeployment }
        { name: 'AZURE_OPENAI_CHAT_MODEL', value: azureOpenAiChatModel }
        { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: azureOpenAiEmbeddingDeployment }
        { name: 'AZURE_OPENAI_EMBEDDING_MODEL', value: azureOpenAiEmbeddingModel }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
        { name: 'AZURE_AI_PROJECT', value: azureAiProject }
        { name: 'DEVUI_AUTH_TOKEN', value: devuiAuthToken }
        { name: 'DEVUI_PORT', value: '8080' }
      ]
    }
  }
}

output acrName string = acr.name
output acrLoginServer string = acrLoginServer
output appName string = webApp.name
output devuiUrl string = 'https://${webApp.properties.defaultHostName}'
