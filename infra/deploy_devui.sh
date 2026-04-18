#!/bin/sh
set -e

echo "=== Deploying DevUI to App Service ==="

ACR_NAME=$(azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>/dev/null || echo "")
if [ -z "$ACR_NAME" ]; then
    echo "AZURE_CONTAINER_REGISTRY_NAME not set, skipping DevUI deployment"
    exit 0
fi

ACR_ENDPOINT=$(azd env get-value AZURE_CONTAINER_REGISTRY_ENDPOINT 2>/dev/null || echo "")
APP_NAME=$(azd env get-value SERVICE_DEVUI_NAME 2>/dev/null || echo "")
RESOURCE_GROUP=$(azd env get-value AZURE_RESOURCE_GROUP 2>/dev/null || echo "")

echo "Building DevUI image on ACR ($ACR_NAME)..."
az acr build --registry "$ACR_NAME" --image devui:latest --file Dockerfile.devui .

echo "Configuring Web App ($APP_NAME) to use the new image..."
az webapp config container set \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --container-image-name "${ACR_ENDPOINT}/devui:latest" \
    --container-registry-url "https://${ACR_ENDPOINT}"

echo "Restarting Web App..."
az webapp restart --name "$APP_NAME" --resource-group "$RESOURCE_GROUP"

DEVUI_URL=$(azd env get-value DEVUI_URL 2>/dev/null || echo "")
echo "DevUI deployed at: $DEVUI_URL"
