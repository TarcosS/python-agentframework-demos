// Resource-group scoped module for AI Services account, deployments, project, and RBAC.
// Uses raw resource declarations (not AVM module) because allowProjectManagement
// is required for Foundry but not available in AVM cognitive-services/account v0.7.1.
// See: https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure

param accountName string
param location string
param tags object = {}
param chatDeploymentName string
param chatModelName string
param chatModelVersion string
param chatDeploymentCapacity int
param embeddingDeploymentName string
param embeddingModelName string
param embeddingModelVersion string
param embeddingDeploymentCapacity int
param principalId string = ''
param principalType string = 'User'
param projectName string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: accountName
    disableLocalAuth: true
    allowProjectManagement: true
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: chatDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: chatDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: chatModelName
      version: chatModelVersion
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: embeddingDeploymentName
  dependsOn: [chatDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: embeddingDeploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embeddingModelName
      version: embeddingModelVersion
    }
  }
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  scope: account
  name: guid(account.id, principalId, 'Cognitive Services OpenAI User')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: principalId
    principalType: principalType
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: projectName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {}
  dependsOn: [chatDeployment, embeddingDeployment]
}

output endpoint string = 'https://${account.properties.customSubDomainName}.openai.azure.com'
output projectEndpoint string = 'https://${account.properties.customSubDomainName}.services.ai.azure.com/api/projects/${projectName}'
