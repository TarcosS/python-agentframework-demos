"""Shared configuration for the orchestrator demo.

Provides factory functions for the chat client, optional observability
setup (Azure Application Insights), and evaluation model configuration.
Supports three providers via API_HOST: "azure" (default), "foundry", "openai".
"""

import logging
import os
from typing import Any

from azure.identity.aio import AzureDeveloperCliCredential, DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from rich.logging import RichHandler

load_dotenv(override=True)

# ── Logging ────────────────────────────────────────────────────────────────

log_handler = RichHandler(show_path=False, rich_tracebacks=True, show_level=False)
logging.basicConfig(level=logging.WARNING, handlers=[log_handler], force=True, format="%(message)s")
logger = logging.getLogger("demo")
logger.setLevel(logging.INFO)


# ── Credential helper ──────────────────────────────────────────────────────


def _create_credential() -> DefaultAzureCredential | AzureDeveloperCliCredential:
    """Pick the right Azure credential based on AZURE_TENANT_ID."""
    tenant_id = os.getenv("AZURE_TENANT_ID")
    if tenant_id:
        return AzureDeveloperCliCredential(tenant_id=tenant_id)
    return DefaultAzureCredential()


# ── Client factory ─────────────────────────────────────────────────────────


def create_client() -> tuple[Any, Any]:
    """Create a chat client based on API_HOST environment variable.

    Supports "azure" (default), "foundry", and "openai".
    Returns (client, credential). Credential must be closed at end of process.
    """
    api_host = os.getenv("API_HOST", "azure")

    if api_host == "foundry":
        from agent_framework_foundry import FoundryChatClient

        credential = _create_credential()
        client = FoundryChatClient(
            project_endpoint=os.environ["AZURE_AI_PROJECT"],
            credential=credential,
            model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
        )
        return client, credential

    if api_host == "azure":
        from agent_framework.openai import OpenAIChatClient

        credential = _create_credential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
        client = OpenAIChatClient(
            base_url=f"{os.environ['AZURE_OPENAI_ENDPOINT']}/openai/v1/",
            api_key=token_provider,
            model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
        )
        return client, credential

    # openai
    from agent_framework.openai import OpenAIChatClient

    client = OpenAIChatClient(
        api_key=os.environ["OPENAI_API_KEY"],
        model=os.environ.get("OPENAI_MODEL", "gpt-5.4"),
    )
    return client, None


# ── Observability ──────────────────────────────────────────────────────────


def setup_observability() -> None:
    """Enable OpenTelemetry export to Azure Application Insights if configured.

    No-op when APPLICATIONINSIGHTS_CONNECTION_STRING is not set.
    Pattern source: examples/agent_otel_appinsights.py
    """
    conn_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_string:
        logger.info("Observability: APPLICATIONINSIGHTS_CONNECTION_STRING not set — skipping")
        return

    try:
        from agent_framework.observability import create_resource, enable_instrumentation
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(
            connection_string=conn_string,
            resource=create_resource(),
            enable_live_metrics=True,
        )
        enable_instrumentation(enable_sensitive_data=True)
        logger.info("Observability: Azure Application Insights export enabled")
    except Exception as exc:
        logger.warning("Observability: failed to configure Azure Monitor (%s) — continuing without telemetry", exc)


# ── Evaluation config ──────────────────────────────────────────────────────


def create_eval_model_config():
    """Create evaluation model configuration for Azure AI Evaluation.

    Pattern source: examples/agent_evaluation.py
    """
    api_host = os.getenv("API_HOST", "azure")

    if api_host in ("azure", "foundry"):
        from azure.ai.evaluation import AzureOpenAIModelConfiguration

        return AzureOpenAIModelConfiguration(
            type="azure_openai",
            azure_endpoint=os.getenv("AZURE_AI_PROJECT") or os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_deployment=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
        )
    else:
        from azure.ai.evaluation import OpenAIModelConfiguration

        return OpenAIModelConfiguration(
            type="openai",
            api_key=os.environ["OPENAI_API_KEY"],
            model=os.environ.get("OPENAI_MODEL", "gpt-5.4"),
        )
