#!/bin/sh
set -e

echo "=== Deploying DevUI to Container Apps ==="

ACR_NAME=$(azd env get-value AZURE_CONTAINER_REGISTRY_NAME 2>/dev/null || echo "")
if [ -z "$ACR_NAME" ]; then
    echo "AZURE_CONTAINER_REGISTRY_NAME not set, skipping DevUI deployment"
    exit 0
fi

ACR_ENDPOINT=$(azd env get-value AZURE_CONTAINER_REGISTRY_ENDPOINT 2>/dev/null || echo "")
APP_NAME=$(azd env get-value SERVICE_DEVUI_NAME 2>/dev/null || echo "")
RESOURCE_GROUP=$(azd env get-value AZURE_RESOURCE_GROUP 2>/dev/null || echo "")

echo "Logging into ACR ($ACR_NAME)..."
az acr login --name "$ACR_NAME"

echo "Building DevUI image locally..."
docker build --platform linux/amd64 -t "${ACR_ENDPOINT}/devui:latest" -f Dockerfile.devui .

echo "Pushing image to ACR..."
docker push "${ACR_ENDPOINT}/devui:latest"

echo "Updating Container App ($APP_NAME) with the new image..."
az containerapp update \
    --name "$APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "${ACR_ENDPOINT}/devui:latest"

DEVUI_URL=$(azd env get-value DEVUI_URL 2>/dev/null || echo "")
echo "DevUI deployed at: $DEVUI_URL"
