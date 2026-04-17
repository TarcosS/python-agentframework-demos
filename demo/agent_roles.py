"""Agent definitions, executors, tools, and Pydantic models for the orchestrator demo.

Organizes all reusable components by pipeline stage:
  Stage 1 — Classification (workflow_switch_case.py pattern)
  Stage 2 — Planning (agent_supervisor.py pattern)
  Stage 3 — Parallel analysis (workflow_aggregator_summary.py pattern)
  Stage 4 — Handoff review (workflow_handoffbuilder_rules.py pattern)
  Stage 5 — HITL approval (workflow_hitl_tool_approval.py pattern)
"""

from __future__ import annotations

from typing import Any, Literal

from agent_framework import (
    Agent,
    AgentExecutorResponse,
    AgentResponseUpdate,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    executor,
    handler,
    tool,
)
from agent_framework.openai import OpenAIChatClient
from agent_framework.orchestrations import HandoffBuilder
from pydantic import BaseModel
from typing_extensions import Never

# ═══════════════════════════════════════════════════════════════════════════
# STAGE 1: CLASSIFICATION — Pattern: workflow_switch_case.py
# ═══════════════════════════════════════════════════════════════════════════


class ClassifyResult(BaseModel):
    """Structured classification of an incoming technical request."""

    category: Literal["ArchitectureReview", "IncidentAnalysis", "FeatureRequest"]
    priority: Literal["critical", "high", "medium", "low"]
    original_request: str
    reasoning: str


def create_classifier(client: OpenAIChatClient) -> Agent:
    """Classifier agent with structured output (response_format)."""
    return Agent(
        client=client,
        name="Classifier",
        instructions=(
            "You are a technical request classifier for an engineering organization. "
            "Classify the incoming request into exactly one category:\n"
            "- ArchitectureReview: design reviews, migration plans, system architecture changes\n"
            "- IncidentAnalysis: outages, performance issues, security incidents, post-mortems\n"
            "- FeatureRequest: new capabilities, enhancements, integrations\n\n"
            "Also assign a priority: critical, high, medium, or low.\n"
            "Return a JSON object with category, priority, original_request, and reasoning."
        ),
        default_options={"response_format": ClassifyResult},
    )


@executor(id="extract_category")
async def extract_category(response: AgentExecutorResponse, ctx: WorkflowContext[ClassifyResult]) -> None:
    """Parse the classifier's structured JSON output and send it downstream."""
    result = ClassifyResult.model_validate_json(response.agent_response.text)
    await ctx.send_message(result)


def is_architecture(msg: Any) -> bool:
    return isinstance(msg, ClassifyResult) and msg.category == "ArchitectureReview"


def is_incident(msg: Any) -> bool:
    return isinstance(msg, ClassifyResult) and msg.category == "IncidentAnalysis"


@executor(id="enrich_architecture")
async def enrich_architecture(result: ClassifyResult, ctx: WorkflowContext[Never, str]) -> None:
    """Enrich an architecture review request with domain context."""
    enriched = (
        f"[Category: Architecture Review | Priority: {result.priority}]\n\n"
        f"Request: {result.original_request}\n\n"
        "Analysis focus areas: design patterns, scalability, security boundaries, "
        "data flow, service decomposition, API contracts, deployment topology."
    )
    await ctx.yield_output(enriched)


@executor(id="enrich_incident")
async def enrich_incident(result: ClassifyResult, ctx: WorkflowContext[Never, str]) -> None:
    """Enrich an incident analysis request with domain context."""
    enriched = (
        f"[Category: Incident Analysis | Priority: {result.priority}]\n\n"
        f"Request: {result.original_request}\n\n"
        "Analysis focus areas: root cause identification, blast radius, "
        "recovery procedures, timeline reconstruction, prevention measures."
    )
    await ctx.yield_output(enriched)


@executor(id="enrich_feature")
async def enrich_feature(result: ClassifyResult, ctx: WorkflowContext[Never, str]) -> None:
    """Enrich a feature request with domain context."""
    enriched = (
        f"[Category: Feature Request | Priority: {result.priority}]\n\n"
        f"Request: {result.original_request}\n\n"
        "Analysis focus areas: feasibility, effort estimation, dependencies, "
        "user impact, backward compatibility, rollout strategy."
    )
    await ctx.yield_output(enriched)


def build_classification_workflow(client: OpenAIChatClient):
    """Build the classification workflow with switch-case routing.

    Pattern source: examples/workflow_switch_case.py
    """
    from agent_framework import Case, Default

    classifier = create_classifier(client)

    return (
        WorkflowBuilder(name="classification", start_executor=classifier)
        .add_edge(classifier, extract_category)
        .add_switch_case_edge_group(
            extract_category,
            [
                Case(condition=is_architecture, target=enrich_architecture),
                Case(condition=is_incident, target=enrich_incident),
                Default(target=enrich_feature),
            ],
        )
        .build()
    )


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 2: PLANNING — Pattern: agent_supervisor.py
# ═══════════════════════════════════════════════════════════════════════════


def create_planner(client: OpenAIChatClient) -> Agent:
    """Supervisor/planner agent that breaks down requests using sub-agent tools.

    Pattern source: examples/agent_supervisor.py
    The planner wraps a complexity-assessor sub-agent as a tool, demonstrating
    hierarchical delegation via the supervisor pattern.
    """
    complexity_assessor = Agent(
        client=client,
        name="ComplexityAssessor",
        instructions=(
            "You assess the technical complexity of engineering requests. "
            "Evaluate effort, risk, number of affected systems, and team coordination needs. "
            "Provide a brief complexity assessment in 2-3 sentences."
        ),
    )

    @tool
    async def assess_complexity(request_summary: str) -> str:
        """Assess the technical complexity of a request by delegating to a specialist."""
        result = await complexity_assessor.run(request_summary)
        return result.text

    return Agent(
        client=client,
        name="Planner",
        instructions=(
            "You are a technical analysis planner. Given a classified request, "
            "create an analysis plan that specialist agents can execute.\n\n"
            "1. Use the assess_complexity tool to understand the scope.\n"
            "2. Then produce a concise analysis plan with:\n"
            "   - Key questions each specialist should answer\n"
            "   - Specific areas of concern\n"
            "   - Expected deliverables\n\n"
            "Format the plan so it can be sent to Security, Reliability, Cost, "
            "and Integration specialists for parallel analysis."
        ),
        tools=[assess_complexity],
    )


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 3: PARALLEL ANALYSIS — Pattern: workflow_aggregator_summary.py
# ═══════════════════════════════════════════════════════════════════════════


class DispatchPrompt(Executor):
    """Broadcast the same prompt downstream so fan-out edges can distribute it.

    Pattern source: examples/workflow_aggregator_summary.py
    """

    @handler
    async def dispatch(self, prompt: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(prompt)


class SynthesizerExecutor(Executor):
    """Fan-in aggregator that synthesizes expert outputs via a wrapped Agent.

    Pattern source: examples/workflow_aggregator_summary.py
    """

    agent: Agent

    def __init__(self, client: OpenAIChatClient, id: str = "Synthesizer"):
        super().__init__(id=id)
        self.agent = Agent(
            client=client,
            name=id,
            instructions=(
                "You receive analysis from four domain specialists: "
                "Security, Reliability, Cost, and Integration. "
                "Synthesize their findings into a structured executive brief with:\n"
                "1. Executive Summary (3 sentences)\n"
                "2. Key Findings by domain\n"
                "3. Critical Risks (ranked by severity)\n"
                "4. Recommended Actions (prioritized)\n\n"
                "Be concise and actionable. A VP of Engineering should be able to "
                "make decisions based on this brief."
            ),
        )

    @handler
    async def run(self, results: list[AgentExecutorResponse], ctx: WorkflowContext[Never, str]) -> None:
        """Format branch outputs and feed them to the synthesizer Agent."""
        sections = []
        for result in results:
            sections.append(f"[{result.executor_id}]\n{result.agent_response.text}")
        combined = "\n\n---\n\n".join(sections)
        response = await self.agent.run(combined)
        await ctx.yield_output(response.text)


def create_security_agent(client: OpenAIChatClient) -> Agent:
    return Agent(
        client=client,
        name="SecurityAgent",
        instructions=(
            "You are a security specialist. Analyze the request for:\n"
            "- Authentication and authorization implications\n"
            "- Data protection and encryption requirements\n"
            "- Attack surface changes\n"
            "- Compliance considerations (SOC2, GDPR)\n"
            "Provide a concise analysis with specific recommendations."
        ),
    )


def create_reliability_agent(client: OpenAIChatClient) -> Agent:
    return Agent(
        client=client,
        name="ReliabilityAgent",
        instructions=(
            "You are a reliability/SRE specialist. Analyze the request for:\n"
            "- Availability and SLA impact\n"
            "- Failure modes and blast radius\n"
            "- Monitoring and alerting needs\n"
            "- Rollback and recovery procedures\n"
            "Provide a concise analysis with specific recommendations."
        ),
    )


def create_cost_agent(client: OpenAIChatClient) -> Agent:
    return Agent(
        client=client,
        name="CostAgent",
        instructions=(
            "You are a cloud cost and resource specialist. Analyze the request for:\n"
            "- Infrastructure cost implications\n"
            "- Resource scaling requirements\n"
            "- Cost optimization opportunities\n"
            "- Build vs buy trade-offs\n"
            "Provide a concise analysis with specific recommendations."
        ),
    )


def create_integration_agent(client: OpenAIChatClient) -> Agent:
    return Agent(
        client=client,
        name="IntegrationAgent",
        instructions=(
            "You are a systems integration specialist. Analyze the request for:\n"
            "- API contract and versioning impacts\n"
            "- Upstream/downstream dependency changes\n"
            "- Data migration and schema evolution\n"
            "- Cross-team coordination requirements\n"
            "Provide a concise analysis with specific recommendations."
        ),
    )


def build_analysis_workflow(client: OpenAIChatClient):
    """Build the parallel analysis workflow with fan-out/fan-in and LLM aggregation.

    Pattern source: examples/workflow_aggregator_summary.py
    """
    dispatcher = DispatchPrompt(id="dispatcher")
    security = create_security_agent(client)
    reliability = create_reliability_agent(client)
    cost = create_cost_agent(client)
    integration = create_integration_agent(client)
    synthesizer = SynthesizerExecutor(client=client)

    return (
        WorkflowBuilder(
            name="parallel_analysis",
            description="Fan-out to 4 specialists, fan-in with LLM synthesis.",
            start_executor=dispatcher,
            output_executors=[synthesizer],
        )
        .add_fan_out_edges(dispatcher, [security, reliability, cost, integration])
        .add_fan_in_edges([security, reliability, cost, integration], synthesizer)
        .build()
    )


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 4: HANDOFF REVIEW — Pattern: workflow_handoffbuilder_rules.py
# ═══════════════════════════════════════════════════════════════════════════


def build_handoff_review(client: OpenAIChatClient):
    """Build the handoff-based review chain with explicit routing rules.

    Pattern source: examples/workflow_handoffbuilder_rules.py

    Review flow:
        reviewer → editor (if revisions needed)
        editor   → reviewer (re-check after edits)
        reviewer → final_reviewer (when satisfied)
        final_reviewer → (terminates with "REVIEWED:" prefix)
    """
    reviewer = Agent(
        client=client,
        name="reviewer",
        instructions=(
            "You are a senior technical reviewer. You receive an executive analysis brief. "
            "Check it for:\n"
            "- Completeness: are all four domains (security, reliability, cost, integration) covered?\n"
            "- Accuracy: are the recommendations actionable and realistic?\n"
            "- Clarity: is the language clear and concise?\n\n"
            "If the brief needs revisions, hand off to editor with specific feedback.\n"
            "If the brief is good, hand off to final_reviewer.\n"
            "Do NOT add the 'REVIEWED:' prefix — only final_reviewer does that."
        ),
    )

    editor_agent = Agent(
        client=client,
        name="editor",
        instructions=(
            "You are a technical editor. You receive a brief and reviewer feedback. "
            "Revise the brief to address the feedback while preserving the original analysis. "
            "Keep the same structure (Executive Summary, Key Findings, Critical Risks, "
            "Recommended Actions). When done, hand off back to reviewer for re-check."
        ),
    )

    final_reviewer = Agent(
        client=client,
        name="final_reviewer",
        instructions=(
            "You are the final reviewer. You receive a brief that has passed technical review. "
            "Do a final check for tone, formatting, and executive readability. "
            "Once satisfied, output the final brief prefixed with 'REVIEWED:' on the first line. "
            "Say 'Goodbye!' at the end to close the review."
        ),
    )

    return (
        HandoffBuilder(
            name="analysis_review",
            participants=[reviewer, editor_agent, final_reviewer],
            termination_condition=lambda conversation: (
                len(conversation) > 0 and "goodbye" in conversation[-1].text.lower()
            ),
        )
        .with_start_agent(reviewer)
        .add_handoff(reviewer, [editor_agent, final_reviewer])
        .add_handoff(editor_agent, [reviewer])
        .add_handoff(final_reviewer, [])
        .with_autonomous_mode()
        .build()
    )


async def run_handoff_review(client: OpenAIChatClient, synthesis: str) -> str:
    """Run the handoff review chain and return the reviewed output.

    Pattern source: examples/workflow_handoffbuilder_rules.py (streaming events)
    """
    from rich.console import Console

    console = Console()
    workflow = build_handoff_review(client)
    reviewed_text = ""
    current_agent = None

    async for event in workflow.run(synthesis, stream=True):
        if event.type == "handoff_sent":
            console.print(f"\n  🔀 [bold yellow]Handoff:[/bold yellow] {event.data.source} → {event.data.target}")

        elif event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            if event.executor_id != current_agent:
                current_agent = event.executor_id
                console.print(f"\n  🤖 [bold cyan]{current_agent}[/bold cyan]")
            console.print(f"  {event.data.text}", end="")
            reviewed_text += event.data.text

    # Extract the final reviewed content (after "REVIEWED:" prefix if present)
    if "REVIEWED:" in reviewed_text:
        reviewed_text = reviewed_text.split("REVIEWED:", 1)[1].strip()

    return reviewed_text or synthesis


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 5: HITL APPROVAL — Pattern: workflow_hitl_tool_approval.py
# ═══════════════════════════════════════════════════════════════════════════


@tool(approval_mode="always_require")
async def publish_recommendations(
    summary: str,
    priority: str,
    action_items: str,
) -> str:
    """Publish the final recommendations report to stakeholders.

    This tool requires human approval before execution, demonstrating
    the governance gate pattern.
    """
    return (
        f"✅ Recommendations published successfully.\n"
        f"Priority: {priority}\n"
        f"Summary: {summary[:200]}...\n"
        f"Action items: {action_items[:200]}..."
    )


@tool(approval_mode="never_require")
def get_distribution_list() -> list[dict[str, str]]:
    """Get the stakeholder distribution list for the recommendations report."""
    return [
        {"name": "VP Engineering", "email": "vp-eng@contoso.com"},
        {"name": "Security Lead", "email": "security@contoso.com"},
        {"name": "SRE Team", "email": "sre@contoso.com"},
        {"name": "Architecture Board", "email": "arch-board@contoso.com"},
    ]


def create_approval_agent(client: OpenAIChatClient) -> Agent:
    return Agent(
        client=client,
        name="ApprovalAgent",
        instructions=(
            "You are responsible for publishing analysis recommendations. "
            "Given the reviewed analysis brief:\n"
            "1. Look up the distribution list using get_distribution_list.\n"
            "2. Prepare a publication summary, priority level, and key action items.\n"
            "3. Use publish_recommendations to send the report (this requires human approval).\n"
            "4. After publishing, confirm the distribution and provide a brief status update."
        ),
        tools=[publish_recommendations, get_distribution_list],
    )


class PrepareForApproval(Executor):
    """Preprocessor that sets up approval context.

    Pattern source: examples/workflow_hitl_tool_approval.py (EmailPreprocessor)
    """

    @handler
    async def prepare(self, report: str, ctx: WorkflowContext[str]) -> None:
        context = (
            "The following analysis has been reviewed and is ready for publication. "
            "Please prepare it for stakeholder distribution.\n\n"
            f"{report}"
        )
        await ctx.send_message(context)


@executor(id="conclude_workflow")
async def conclude_workflow(
    response: AgentExecutorResponse,
    ctx: WorkflowContext[Never, str],
) -> None:
    """Yield the final approved response as output."""
    await ctx.yield_output(response.agent_response.text)


def build_approval_workflow(client: OpenAIChatClient):
    """Build the HITL approval workflow with tool-level approval gates.

    Pattern source: examples/workflow_hitl_tool_approval.py
    """
    preprocessor = PrepareForApproval(id="prepare_approval")
    approval_agent = create_approval_agent(client)

    return (
        WorkflowBuilder(
            name="hitl_approval",
            start_executor=preprocessor,
            output_executors=[conclude_workflow],
        )
        .add_edge(preprocessor, approval_agent)
        .add_edge(approval_agent, conclude_workflow)
        .build()
    )
