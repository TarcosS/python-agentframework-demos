"""Standalone DevUI server entry point for Azure Container Apps deployment.

Starts the Agent Framework DevUI with the analysis workflow,
configured for remote access with Bearer token authentication.

Environment variables:
    DEVUI_AUTH_TOKEN  — Required. Bearer token for API/UI access.
    DEVUI_PORT       — Optional. Server port (default: 8080).

All standard Azure OpenAI env vars are loaded from the container's
environment (set via Bicep/Container App configuration).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from demo.agent_roles import build_analysis_workflow
from demo.demo_config import create_client, setup_observability


def main() -> None:
    from agent_framework.devui import serve

    setup_observability()
    client, _ = create_client()
    workflow = build_analysis_workflow(client)

    port = int(os.getenv("DEVUI_PORT", "8080"))

    serve(
        entities=[workflow],
        host="0.0.0.0",
        port=port,
        auto_open=False,
        auth_enabled=True,
        auth_token=os.environ["DEVUI_AUTH_TOKEN"],
    )


if __name__ == "__main__":
    main()
