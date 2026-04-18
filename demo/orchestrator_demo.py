"""Multi-Agent Orchestration Best Practices Demo.

Demonstrates how to orchestrate multiple agents in a real-world Technical
Request Triage scenario using Microsoft Agent Framework patterns.

Pipeline stages:
    1. Classification  — switch-case routing     (workflow_switch_case.py)
    2. Planning        — supervisor with sub-agent tool  (agent_supervisor.py)
    3. Parallel Analysis — fan-out/fan-in + LLM synthesis (workflow_aggregator_summary.py)
    4. Handoff Review  — HandoffBuilder with rules (workflow_handoffbuilder_rules.py)
    5. HITL Approval   — tool approval gate       (workflow_hitl_tool_approval.py)
    + Observability    — OTel / App Insights      (agent_otel_appinsights.py)
    + Evaluation       — Azure AI Evaluation      (agent_evaluation.py)

Run:
    uv run python demo/orchestrator_demo.py
    uv run python demo/orchestrator_demo.py --eval     (include evaluation)
    uv run python demo/orchestrator_demo.py --devui    (DevUI for analysis workflow)
"""

import asyncio
import json
import os
import sys

# Ensure the repo root is on sys.path so `demo.*` imports resolve
# when running as a script (uv run python demo/orchestrator_demo.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_framework import Content
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from demo.agent_roles import (
    build_analysis_workflow,
    build_approval_workflow,
    build_classification_workflow,
    build_full_pipeline,
    build_full_pipeline_detailed,
    build_handoff_review,
    create_planner,
    create_approval_agent,
    create_classifier,
    create_cost_agent,
    create_integration_agent,
    create_reliability_agent,
    create_security_agent,
    run_handoff_review,
)
from demo.demo_config import create_client, create_eval_model_config, logger, setup_observability

console = Console()

# ── Sample requests for demonstration ──────────────────────────────────────

SAMPLE_REQUESTS = {
    "architecture": (
        "We want to split our main web application into smaller, independent "
        "services. The app currently runs as a single deployment and we'd like "
        "to evaluate the best way to break it apart, what risks are involved, "
        "and how to migrate without downtime."
    ),
    "incident": (
        "Our login service went down for about 30 minutes this morning. Users "
        "couldn't sign in and some API calls returned errors. We need to "
        "understand what happened, how to prevent it, and what we should "
        "improve in our monitoring."
    ),
    "feature": (
        "We'd like to add a notification system to our platform so users can "
        "receive alerts via email and in-app. We need to evaluate the best "
        "approach, estimate the effort, and identify any risks."
    ),
}


# ═══════════════════════════════════════════════════════════════════════════
# STAGE RUNNERS
# ═══════════════════════════════════════════════════════════════════════════


async def stage_classify(client, request: str) -> str:
    """Stage 1: Classify the incoming request using switch-case routing."""
    console.print("\n[bold blue]═══ Stage 1: CLASSIFICATION ═══[/bold blue]")
    console.print("  Pattern: workflow_switch_case.py (structured output + switch-case routing)\n")

    workflow = build_classification_workflow(client)
    events = await workflow.run(request)
    outputs = events.get_outputs()

    if not outputs:
        logger.warning("Classification produced no output — using raw request")
        return request

    enriched = outputs[-1]
    enriched_str = enriched.text if hasattr(enriched, "text") else str(enriched)
    console.print(Panel(enriched_str, title="Classified & Enriched Request", border_style="blue"))
    return enriched_str


async def stage_plan(client, enriched_request: str) -> str:
    """Stage 2: Create analysis plan using supervisor pattern."""
    console.print("\n[bold green]═══ Stage 2: PLANNING ═══[/bold green]")
    console.print("  Pattern: agent_supervisor.py (supervisor + sub-agent as tool)\n")

    planner = create_planner(client)
    response = await planner.run(enriched_request)

    console.print(Panel(response.text, title="Analysis Plan", border_style="green"))
    return response.text


async def stage_analyze(client, plan: str) -> str:
    """Stage 3: Run parallel expert analysis with fan-out/fan-in."""
    console.print("\n[bold yellow]═══ Stage 3: PARALLEL ANALYSIS ═══[/bold yellow]")
    console.print("  Pattern: workflow_aggregator_summary.py (fan-out → 4 specialists → fan-in LLM synthesis)\n")

    workflow = build_analysis_workflow(client)
    events = await workflow.run(plan)
    outputs = events.get_outputs()

    if not outputs:
        logger.warning("Analysis produced no output — using plan as fallback")
        return plan

    synthesis = outputs[-1]
    synthesis_str = synthesis.text if hasattr(synthesis, "text") else str(synthesis)
    console.print(Panel(synthesis_str, title="Synthesized Executive Brief", border_style="yellow"))
    return synthesis_str


async def stage_review(client, synthesis: str) -> str:
    """Stage 4: Handoff-based review chain."""
    console.print("\n[bold magenta]═══ Stage 4: HANDOFF REVIEW ═══[/bold magenta]")
    console.print("  Pattern: workflow_handoffbuilder_rules.py (HandoffBuilder + routing rules)\n")

    # Retry with backoff to handle Azure OpenAI rate limits
    for attempt in range(3):
        try:
            reviewed = await run_handoff_review(client, synthesis)
            console.print(Panel(reviewed, title="Reviewed Analysis", border_style="magenta"))
            return reviewed
        except Exception as exc:
            if "Too Many Requests" in str(exc) and attempt < 2:
                wait = 10 * (attempt + 1)
                console.print(f"  [dim]Rate limited — retrying in {wait}s (attempt {attempt + 2}/3)...[/dim]")
                await asyncio.sleep(wait)
            else:
                raise

    return synthesis  # fallback (unreachable)


async def stage_approve(client, reviewed: str) -> str:
    """Stage 5: HITL approval gate for publishing recommendations."""
    console.print("\n[bold red]═══ Stage 5: HITL APPROVAL ═══[/bold red]")
    console.print("  Pattern: workflow_hitl_tool_approval.py (tool approval_mode + event loop)\n")

    workflow = build_approval_workflow(client)
    events = await workflow.run(reviewed)
    request_info_events = events.get_request_info_events()

    while request_info_events:
        responses: dict[str, Content] = {}
        for request_info_event in request_info_events:
            data = request_info_event.data
            if not isinstance(data, Content) or data.type != "function_approval_request":
                continue
            if data.function_call is None:
                continue

            arguments = json.dumps(data.function_call.parse_arguments(), indent=2)
            console.print(f"  🔒 [bold]Approval requested for:[/bold] {data.function_call.name}")
            console.print(f"  Arguments:\n{arguments}")

            approval = input("  Approve? (y/n): ").strip().lower()
            approved = approval == "y"
            console.print(f"  {'✅ Approved' if approved else '❌ Rejected'}\n")
            responses[request_info_event.request_id] = data.to_function_approval_response(approved=approved)

        events = await workflow.run(responses=responses)
        request_info_events = events.get_request_info_events()

    outputs = events.get_outputs()
    final = outputs[-1] if outputs else reviewed
    final_str = final.text if hasattr(final, "text") else str(final)

    console.print(Panel(final_str, title="Approval Result", border_style="red"))
    return final_str


# ── Optional: Evaluation ──────────────────────────────────────────────────


async def run_evaluation(request: str, final_output: str) -> None:
    """Run Azure AI Evaluation on the final output.

    Pattern source: examples/agent_evaluation.py
    """
    console.print("\n[bold cyan]═══ EVALUATION ═══[/bold cyan]")
    console.print("  Pattern: agent_evaluation.py (Azure AI Evaluation evaluators)\n")

    try:
        from azure.ai.evaluation import (
            IntentResolutionEvaluator,
            ResponseCompletenessEvaluator,
            TaskAdherenceEvaluator,
        )
    except ImportError:
        console.print("  [dim]azure-ai-evaluation not available — skipping evaluation[/dim]")
        return

    eval_model_config = create_eval_model_config()
    evaluator_kwargs = {"model_config": eval_model_config, "is_reasoning_model": True}

    eval_query = [
        {"role": "system", "content": "You are a technical analysis orchestrator."},
        {"role": "user", "content": [{"type": "text", "text": request}]},
    ]
    eval_response = [{"role": "assistant", "content": [{"type": "text", "text": final_output}]}]

    intent_evaluator = IntentResolutionEvaluator(**evaluator_kwargs)
    completeness_evaluator = ResponseCompletenessEvaluator(**evaluator_kwargs)
    adherence_evaluator = TaskAdherenceEvaluator(**evaluator_kwargs)

    ground_truth = (
        "A comprehensive technical analysis covering security implications, "
        "reliability/SLA impact, cost analysis, and integration considerations, "
        "with prioritized recommendations and an executive summary."
    )

    intent_result = intent_evaluator(query=eval_query, response=eval_response)
    completeness_result = completeness_evaluator(response=final_output, ground_truth=ground_truth)
    adherence_result = adherence_evaluator(query=eval_query, response=eval_response)

    table = Table(title="Evaluation Results", show_lines=True)
    table.add_column("Evaluator", style="cyan", width=28)
    table.add_column("Score", style="bold", justify="center", width=8)
    table.add_column("Result", justify="center", width=8)

    for name, result, key in [
        ("IntentResolution", intent_result, "intent_resolution"),
        ("ResponseCompleteness", completeness_result, "response_completeness"),
        ("TaskAdherence", adherence_result, "task_adherence"),
    ]:
        score = str(result.get(key, "N/A"))
        pass_fail = result.get(f"{key}_result", "N/A")
        result_str = "[green]pass[/green]" if pass_fail == "pass" else f"[red]{pass_fail}[/red]"
        table.add_row(name, score, result_str)

    console.print(table)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════


async def main() -> None:
    """Run the full multi-agent orchestration pipeline."""
    client, credential = create_client()
    setup_observability()

    # Select sample request (default: architecture review)
    request_type = "architecture"
    for arg in sys.argv[1:]:
        if arg in SAMPLE_REQUESTS:
            request_type = arg
    request = SAMPLE_REQUESTS[request_type]

    console.print(
        Panel(
            f"[bold]Request type:[/bold] {request_type}\n\n{request}",
            title="🚀 Multi-Agent Orchestration Demo",
            border_style="bold white",
        )
    )

    # ── Stage 1: Classification ──
    enriched = await stage_classify(client, request)

    # ── Stage 2: Planning ──
    plan = await stage_plan(client, enriched)

    # ── Stage 3: Parallel Analysis ──
    synthesis = await stage_analyze(client, plan)

    # Brief pause to avoid Azure OpenAI rate limits between heavy stages
    await asyncio.sleep(5)

    # ── Stage 4: Handoff Review ──
    reviewed = await stage_review(client, synthesis)

    # ── Stage 5: HITL Approval ──
    final = await stage_approve(client, reviewed)

    # ── Final Output ──
    console.print("\n[bold white on blue] ═══ FINAL APPROVED REPORT ═══ [/bold white on blue]\n")
    console.print(final)

    # ── Optional: Evaluation ──
    if "--eval" in sys.argv:
        await run_evaluation(request, final)

    if credential:
        await credential.close()

    console.print("\n[dim]Demo complete.[/dim]")


if __name__ == "__main__":
    if "--devui" in sys.argv:
        from agent_framework.devui import serve

        from demo.demo_config import create_client

        client, _ = create_client()
        serve(entities=[
            build_full_pipeline_detailed(client),    # Full pipeline with all internal nodes visible
            build_classification_workflow(client),   # Stage 1: switch-case routing
            create_planner(client),                  # Stage 2: supervisor + sub-agent tool
            create_classifier(client),               # Specialist agent: classification
            create_cost_agent(client),              # Specialist agent: cost analysis
            create_reliability_agent(client),        # Specialist agent: reliability analysis
            create_security_agent(client),           # Specialist agent: security analysis
            create_integration_agent(client),        # Specialist agent: integration analysis
            build_analysis_workflow(client),          # Stage 3: fan-out/fan-in 4 specialists
            build_handoff_review(client),             # Stage 4: reviewer → editor → final_reviewer
            build_approval_workflow(client),          # Stage 5: HITL tool approval gate
        ], port=8200, auto_open=True, instrumentation_enabled=True)
    else:
        asyncio.run(main())
