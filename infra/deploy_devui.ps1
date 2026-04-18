Write-Host "=== Deploying DevUI to Container Apps ==="

$ACR_NAME = azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>$null
if (-not $ACR_NAME) {
    Write-Host "AZURE_CONTAINER_REGISTRY_NAME not set, skipping DevUI deployment"
    exit 0
}

$ACR_ENDPOINT = azd env get-value AZURE_CONTAINER_REGISTRY_ENDPOINT 2>$null
$APP_NAME = azd env get-value SERVICE_DEVUI_NAME 2>$null
$RESOURCE_GROUP = azd env get-value AZURE_RESOURCE_GROUP 2>$null

Write-Host "Logging into ACR ($ACR_NAME)..."
az acr login --name $ACR_NAME

Write-Host "Building DevUI image locally..."
docker build --platform linux/amd64 -t "${ACR_ENDPOINT}/devui:latest" -f Dockerfile.devui .

Write-Host "Pushing image to ACR..."
docker push "${ACR_ENDPOINT}/devui:latest"

Write-Host "Updating Container App ($APP_NAME) with the new image..."
az containerapp update `
    --name $APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --image "${ACR_ENDPOINT}/devui:latest"

$DEVUI_URL = azd env get-value DEVUI_URL 2>$null
Write-Host "DevUI deployed at: $DEVUI_URL"
