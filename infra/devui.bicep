// Azure Container Apps infrastructure for DevUI deployment.
// Includes: Container Registry, Container Apps Environment, and Container App.

param location string
param tags object = {}
param prefix string

// DevUI auth token — stored as a secret
@secure()
param devuiAuthToken string

// Azure OpenAI config passed as env vars
param azureOpenAiEndpoint string
param azureOpenAiChatDeployment string
param azureOpenAiChatModel string
param azureOpenAiEmbeddingDeployment string
param azureOpenAiEmbeddingModel string
param appInsightsConnectionString string
param azureAiProject string

// Cognitive Services account name for RBAC
param cognitiveAccountName string

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

// ── Container Apps Environment ────────────────────────────────────────────

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${prefix}-cae'
  location: location
  tags: tags
  properties: {}
}

// ── Container App ─────────────────────────────────────────────────────────

var acrLoginServer = acr.properties.loginServer
var acrCredentials = acr.listCredentials()

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: '${prefix}-devui'
  location: location
  tags: union(tags, { 'azd-service-name': 'devui' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
      }
      registries: [
        {
          server: acrLoginServer
          username: acrCredentials.username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password', value: acrCredentials.passwords[0].value }
        { name: 'devui-auth-token', value: devuiAuthToken }
      ]
    }
    template: {
      containers: [
        {
          name: 'devui'
          image: 'mcr.microsoft.com/appsvc/staticsite:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'API_HOST', value: 'azure' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_VERSION', value: '2024-10-21' }
            { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: azureOpenAiChatDeployment }
            { name: 'AZURE_OPENAI_CHAT_MODEL', value: azureOpenAiChatModel }
            { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: azureOpenAiEmbeddingDeployment }
            { name: 'AZURE_OPENAI_EMBEDDING_MODEL', value: azureOpenAiEmbeddingModel }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'AZURE_AI_PROJECT', value: azureAiProject }
            { name: 'DEVUI_AUTH_TOKEN', secretRef: 'devui-auth-token' }
            { name: 'DEVUI_PORT', value: '8080' }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
}

// ── RBAC — grant Container App access to AI Services ──────────────────────

resource cognitiveAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: cognitiveAccountName
}

resource devuiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: cognitiveAccount
  name: guid(cognitiveAccount.id, containerApp.id, 'Cognitive Services OpenAI User')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output acrName string = acr.name
output acrLoginServer string = acrLoginServer
output appName string = containerApp.name
output devuiUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
