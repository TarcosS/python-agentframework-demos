Write-Host "=== Deploying DevUI to App Service ==="

$ACR_NAME = azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>$null
if (-not $ACR_NAME) {
    Write-Host "AZURE_CONTAINER_REGISTRY_NAME not set, skipping DevUI deployment"
    exit 0
}

$ACR_ENDPOINT = azd env get-value AZURE_CONTAINER_REGISTRY_ENDPOINT 2>$null
$APP_NAME = azd env get-value SERVICE_DEVUI_NAME 2>$null
$RESOURCE_GROUP = azd env get-value AZURE_RESOURCE_GROUP 2>$null

Write-Host "Building DevUI image on ACR ($ACR_NAME)..."
az acr build --registry $ACR_NAME --image devui:latest --file Dockerfile.devui .

Write-Host "Configuring Web App ($APP_NAME) to use the new image..."
az webapp config container set `
    --name $APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --container-image-name "${ACR_ENDPOINT}/devui:latest" `
    --container-registry-url "https://${ACR_ENDPOINT}"

Write-Host "Restarting Web App..."
az webapp restart --name $APP_NAME --resource-group $RESOURCE_GROUP

$DEVUI_URL = azd env get-value DEVUI_URL 2>$null
Write-Host "DevUI deployed at: $DEVUI_URL"
