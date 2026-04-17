"""Shared configuration for the orchestrator demo.

Provides factory functions for the OpenAI chat client, optional observability
setup (Azure Application Insights), and evaluation model configuration.
Follows the same patterns used throughout the examples/ directory but
extracted into a reusable module.
"""

import logging
import os

from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import AzureDeveloperCliCredential, DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from rich.logging import RichHandler

load_dotenv(override=True)

# ── Logging ────────────────────────────────────────────────────────────────

log_handler = RichHandler(show_path=False, rich_tracebacks=True, show_level=False)
logging.basicConfig(level=logging.WARNING, handlers=[log_handler], force=True, format="%(message)s")
logger = logging.getLogger("demo")
logger.setLevel(logging.INFO)


# ── Client factory ─────────────────────────────────────────────────────────


def create_client() -> tuple[OpenAIChatClient, DefaultAzureCredential | None]:
    """Create an OpenAI chat client based on API_HOST environment variable.

    Returns (client, credential). The credential is non-None only when using
    Azure and must be closed at the end of the process.
    """
    api_host = os.getenv("API_HOST", "azure")
    credential = None

    if api_host == "azure":
        # Use AzureDeveloperCliCredential (azd auth) when AZURE_TENANT_ID is set,
        # to avoid tenant mismatch if `az login` points to a different tenant.
        tenant_id = os.getenv("AZURE_TENANT_ID")
        if tenant_id:
            credential = AzureDeveloperCliCredential(tenant_id=tenant_id)
        else:
            credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
        client = OpenAIChatClient(
            base_url=f"{os.environ['AZURE_OPENAI_ENDPOINT']}/openai/v1/",
            api_key=token_provider,
            model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
        )
    else:
        client = OpenAIChatClient(
            api_key=os.environ["OPENAI_API_KEY"],
            model=os.environ.get("OPENAI_MODEL", "gpt-5.4"),
        )

    return client, credential


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

    if api_host == "azure":
        from azure.ai.evaluation import AzureOpenAIModelConfiguration

        return AzureOpenAIModelConfiguration(
            type="azure_openai",
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            azure_deployment=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"],
        )
    else:
        from azure.ai.evaluation import OpenAIModelConfiguration

        return OpenAIModelConfiguration(
            type="openai",
            api_key=os.environ["OPENAI_API_KEY"],
            model=os.environ.get("OPENAI_MODEL", "gpt-5.4"),
        )
